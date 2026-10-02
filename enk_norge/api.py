"""Enkle arbeidsflyter som bruker ERPNexts bilag og hovedbok."""

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256

import frappe
from frappe.utils import cint, getdate, today

from enk_norge.currency import get_currency_party_account, nok_amount, parse_currency_input
from enk_norge.setup import get_settings, invoice_naming_series


def _data(data):
	data = frappe.parse_json(data) if isinstance(data, str) else data
	if not isinstance(data, dict):
		frappe.throw("Ugyldige opplysninger.")
	return frappe._dict(data)


def _amount(value, label="Beløp", positive=True):
	try:
		value = Decimal(str(value))
		if not value.is_finite() or (positive and value <= 0):
			raise ValueError
		rounded = value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
		if value != rounded:
			raise ValueError
		return rounded
	except InvalidOperation, ValueError, TypeError:
		frappe.throw(f"{label} må være et gyldig positivt beløp.")


def _registered(settings, posting_date):
	return bool(
		settings.vat_registered
		and settings.vat_registration_date
		and getdate(posting_date) >= getdate(settings.vat_registration_date)
	)


def _fingerprint(data):
	return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _draft_existing(doctype, company, external_id, fingerprint):
	if not external_id:
		return None
	frappe.db.sql("select name from `tabCompany` where name=%s for update", company)
	name = frappe.db.get_value(
		doctype, {"company": company, "enk_external_id": external_id}, "name", for_update=True
	)
	if name:
		doc = frappe.get_doc(doctype, name, for_update=True)
		doc.check_permission("read")
		if doc.docstatus == 2:
			frappe.throw(
				"Hendelsen viser et annullert dokument. Bruk en ny hendelses-ID for en dokumentert erstatning."
			)
		if doc.enk_request_fingerprint != fingerprint:
			frappe.throw(
				"Hendelses-ID er allerede brukt med andre opplysninger. Kontroller kilden før du prøver igjen."
			)
		return dict(doctype=doctype, name=name, reused=True)


def _check_editable_draft(doctype, name, company):
	draft = frappe.get_doc(doctype, name, for_update=True)
	draft.check_permission("write")
	if draft.docstatus != 0 or draft.company != company:
		frappe.throw("Bare kladder i samme foretak kan redigeres.")
	if draft.get("enk_external_id"):
		frappe.throw("Kladden kommer fra timer, abonnement eller import. Slett den og lag den på nytt fra kilden.")
	return draft


def _save_draft(doc, values, draft_name=None):
	"""Lagre ny kladd, eller skriv opplysningene inn i en eksisterende kladd så nummeret beholdes."""
	if not draft_name:
		doc.insert()
		return doc
	draft = _check_editable_draft(doc.doctype, draft_name, doc.company)
	for field, value in values.items():
		if field not in ("doctype", "naming_series", "items"):
			draft.set(field, value)
	draft.set("items", [row.as_dict(no_default_fields=True) for row in doc.items])
	draft.set("taxes", [row.as_dict(no_default_fields=True) for row in doc.taxes])
	# ERPNext tar forfallsdatoen fra betalingsplanen. Tøm den så planen lages fra ny dato.
	draft.set("payment_schedule", [])
	draft.save()
	return draft


def _sale_lines(data):
	"""Fakturalinjer fra `items`, eller én linje fra beskrivelse, antall og pris."""
	rows = data.get("items")
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	if not rows:
		rows = [dict(description=data.description, quantity=data.get("quantity", 1), unit_price=data.unit_price)]
	if not isinstance(rows, list) or len(rows) > 100:
		frappe.throw("Ugyldige fakturalinjer.")
	lines = []
	for row in rows:
		row = frappe._dict(row)
		description = (row.description or "").strip()
		if not description:
			frappe.throw("Hver fakturalinje må ha en beskrivelse.")
		lines.append(
			dict(
				description=description,
				qty=_amount(row.get("quantity", row.get("qty", 1)), "Antall"),
				rate=_amount(row.get("unit_price", row.get("rate")), "Pris"),
			)
		)
	return lines


@frappe.whitelist(methods=["POST"])
def create_sale(data):
	data = _data(data)
	currency = parse_currency_input(data)
	settings = get_settings(data.company)
	frappe.has_permission("Sales Invoice", "create", throw=True)
	if existing := _draft_existing("Sales Invoice", data.company, data.external_id, _fingerprint(data)):
		return existing
	if data.get("draft") and data.external_id:
		frappe.throw("En kladd fra en ekstern kilde kan ikke redigeres.")
	posting = getdate(data.posting_date or today())
	customer = frappe.get_doc("Customer", data.customer)
	customer.check_permission("read")
	address = frappe.get_doc("Address", data.customer_address)
	address.check_permission("read")
	if not any(l.link_doctype == "Customer" and l.link_name == customer.name for l in address.links):
		frappe.throw("Fakturaadressen tilhører ikke valgt kunde.")
	if currency.currency != "NOK" and (address.country == "Norway" or customer.customer_type != "Company"):
		frappe.throw("Valutasalg støttes bare for fjernleverbare tjenester til utenlandsk bedrift.")
	treatment = data.tax_treatment or ("Domestic 25" if _registered(settings, posting) else "Not registered")
	if address.country != "Norway" and treatment != "Export services":
		frappe.throw("Utenlandssalg krever eksplisitt avgiftsbehandling.")
	if treatment == "Export services" and (
		address.country == "Norway" or customer.customer_type != "Company"
	):
		frappe.throw(
			"Denne flyten støtter fjernleverbare tjenester til utenlandske bedrifter. Andre tilfeller må avklares."
		)
	if treatment.startswith("Domestic") and not _registered(settings, posting):
		frappe.throw("Foretaket er ikke MVA-registrert på fakturadatoen.")
	if treatment == "Not registered" and _registered(settings, posting):
		frappe.throw("Foretaket er MVA-registrert. Velg riktig avgiftsbehandling.")
	if currency.currency != "NOK" and treatment != "Export services":
		frappe.throw("Valutasalg må føres som fjernleverbar tjeneste til utenlandsk bedrift.")
	if treatment not in (
		"Domestic 25",
		"Domestic 15",
		"Domestic 12",
		"Not registered",
		"Export services",
		"Exempt",
	):
		frappe.throw("Avgiftsbehandlingen støttes ikke for salg.")
	lines = _sale_lines(data)
	if not data.delivery_date:
		frappe.throw("Oppgi leveringsdato.")
	if treatment == "Exempt" and not (data.tax_reason or "").strip():
		frappe.throw("Oppgi regel og begrunnelse for at leveransen er unntatt fra MVA.")
	delivery_description = (data.description or "").strip() or "\n".join(line["description"] for line in lines)
	from enk_norge.deferrals import DeferralError, subscription_sale_values

	try:
		deferred_values = subscription_sale_values(data, settings, posting)
	except DeferralError as error:
		frappe.throw(str(error))
	values = dict(
			doctype="Sales Invoice",
			company=data.company,
			customer=customer.name,
			customer_address=address.name,
			posting_date=posting,
			due_date=data.due_date,
			set_posting_time=1,
			currency=currency.currency,
			conversion_rate=float(currency.conversion_rate),
			selling_price_list="ENK Selling",
			price_list_currency=currency.currency,
			plc_conversion_rate=1,
			debit_to=(get_currency_party_account(data.company, currency.currency, "receivable")
				if currency.currency != "NOK" else settings.receivable_account),
			enk_exchange_rate_source=currency.source,
			enk_exchange_rate_date=currency.rate_date,
			naming_series=invoice_naming_series(settings),
			enk_tax_treatment=treatment,
			enk_tax_reason=data.tax_reason,
			enk_external_id=data.external_id,
			enk_request_fingerprint=_fingerprint(data) if data.external_id else None,
			enk_delivery_date=data.delivery_date,
			enk_delivery_description=delivery_description,
			items=[
				dict(
					item_name=line["description"][:140],
					description=line["description"],
					qty=float(line["qty"]),
					uom="Nos",
					rate=float(line["rate"]),
					income_account=(
						settings.export_income_account
						if treatment == "Export services"
						else settings.exempt_income_account
						if treatment == "Exempt"
						else settings.income_account
					),
					cost_center=frappe.get_cached_value("Company", data.company, "cost_center"),
				)
				| (deferred_values or {})
				for line in lines
			],
		)
	doc = frappe.get_doc(values)
	if treatment.startswith("Domestic"):
		doc.append(
			"taxes",
			dict(
				charge_type="On Net Total",
				account_head=settings.output_vat_account,
				description="Merverdiavgift",
				rate=int(treatment.split()[1]),
			),
		)
	doc = _save_draft(doc, values, data.get("draft"))
	if deferred_values:
		from enk_norge.deferrals import attach_subscription_source

		attach_subscription_source(doc, data.subscription_source_file)
	return dict(doctype=doc.doctype, name=doc.name, reused=False)


@frappe.whitelist(methods=["POST"])
def create_purchase(data):
	data = _data(data)
	currency = parse_currency_input(data)
	settings = get_settings(data.company)
	frappe.has_permission("Purchase Invoice", "create", throw=True)
	if existing := _draft_existing("Purchase Invoice", data.company, data.external_id, _fingerprint(data)):
		return existing
	if data.get("draft") and data.external_id:
		frappe.throw("En kladd fra en ekstern kilde kan ikke redigeres.")
	supplier = frappe.get_doc("Supplier", data.supplier)
	supplier.check_permission("read")
	if not data.description or not data.bill_no or not data.bill_date:
		frappe.throw("Oppgi formål, leverandørens bilagsnummer og bilagsdato.")
	frappe.db.sql("select name from `tabCompany` where name=%s for update", data.company)
	if frappe.db.exists(
		"Purchase Invoice",
		{
			"company": data.company,
			"supplier": data.supplier,
			"bill_no": data.bill_no,
			"docstatus": ["!=", 2],
			"name": ["!=", data.get("draft") or ""],
		},
	):
		frappe.throw("Bilagsnummeret er allerede registrert for denne leverandøren.")
	category = data.category or "expense"
	if category not in ("software", "equipment", "expense", "fees", "asset"):
		frappe.throw("Velg en gyldig kostnadskategori.")
	posting = getdate(data.posting_date or data.bill_date)
	gross = _amount(data.gross_amount)
	rate = Decimal(str(data.get("vat_rate") or 0))
	if rate not in (Decimal(0), Decimal(12), Decimal(15), Decimal(25)):
		frappe.throw("Velg 0, 12, 15 eller 25 prosent norsk MVA.")
	fraction = Decimal(str(data.get("deductible_fraction", 1)))
	if not fraction.is_finite() or not 0 <= fraction <= 1:
		frappe.throw("Fradragsandelen må være mellom 0 og 1.")
	business_fraction = Decimal(str(data.get("business_fraction", 1)))
	if not business_fraction.is_finite() or not 0 < business_fraction <= 1:
		frappe.throw("Virksomhetsandelen må være over 0 og høyst 1.")
	if fraction > business_fraction:
		frappe.throw("MVA-fradragsandelen kan ikke være større enn virksomhetsandelen av kjøpet.")
	foreign = cint(data.get("foreign_service"))
	if currency.currency != "NOK" and not foreign:
		frappe.throw("Valutakjøp støttes bare for utenlandske tjenester med omvendt MVA.")
	try:
		tax_fraction = Decimal(str(data.get("tax_deductible_fraction", 1)))
		if not tax_fraction.is_finite() or not 0 <= tax_fraction <= 1:
			raise ValueError
	except InvalidOperation, ValueError:
		frappe.throw("Skattemessig fradragsandel må være mellom 0 og 1.")
	if tax_fraction < 1 and not (data.tax_adjustment_reason or "").strip():
		frappe.throw("Begrunn hvorfor næringskostnaden ikke gir fullt skattemessig fradrag.")
	if tax_fraction < 1 and (foreign or category == "asset"):
		frappe.throw(
			"Redusert skattefradrag for eiendel eller utenlandsk tjeneste krever særskilt årsjustering."
		)
	if _registered(settings, posting) and not rate and not foreign and not (data.tax_reason or "").strip():
		frappe.throw(
			"Forklar hvorfor kjøpet er uten MVA, for eksempel unntatt ytelse eller uregistrert leverandør."
		)
	if foreign and (not supplier.country or supplier.country == "Norway"):
		frappe.throw("Oppgi leverandørens utenlandske hjemland før du velger utenlandsk tjeneste.")
	if foreign and business_fraction != 1:
		frappe.throw("Utenlandske tjenester med privat andel krever særskilt avgiftsavklaring før bokføring.")
	if foreign and rate:
		frappe.throw(
			"Utenlandske tjenester føres uten norsk MVA på leverandørfakturaen. Sett MVA-sats til 0."
		)
	net = (gross / (1 + rate / 100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
	deductible = (
		((gross - net) * fraction).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
		if _registered(settings, posting)
		else Decimal(0)
	)
	private_amount = (gross * (1 - business_fraction)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
	expense = gross - private_amount - deductible
	if category in ("equipment", "asset"):
		if business_fraction != 1:
			frappe.throw("Utstyr med privat bruk må avklares før aktivering og avskrivning.")
		from enk_norge.norway_rules import AssetTreatment, assess_asset

		if not data.get("expected_life_months"):
			frappe.throw("Oppgi forventet brukstid for utstyret.")
		assessment = assess_asset(
			cost_basis=expense,
			expected_useful_life_months=cint(data.expected_life_months),
			physical_asset=True,
			declines_in_value=True,
			predominantly_income_producing=True,
			as_of=posting,
		)
		# Regelmotoren avgjør om utstyret skal aktiveres, så brukeren trenger bare ett utstyrsvalg.
		if assessment.treatment == AssetTreatment.ACTIVATE_AND_DEPRECIATE:
			category = "asset"
	values = dict(
			doctype="Purchase Invoice",
			company=data.company,
			supplier=data.supplier,
			posting_date=posting,
			set_posting_time=1,
			bill_no=data.bill_no,
			bill_date=data.bill_date,
			due_date=data.due_date or data.bill_date,
			currency=currency.currency,
			conversion_rate=float(currency.conversion_rate),
			credit_to=(get_currency_party_account(data.company, currency.currency, "payable")
				if currency.currency != "NOK" else settings.payable_account),
			enk_exchange_rate_source=currency.source,
			enk_exchange_rate_date=currency.rate_date,
			enk_external_id=data.external_id,
			enk_request_fingerprint=_fingerprint(data) if data.external_id else None,
			enk_tax_treatment="Foreign services"
			if foreign
			else ("Domestic " + str(int(rate)))
			if rate and _registered(settings, posting)
			else "No input VAT"
			if _registered(settings, posting)
			else "Not registered",
			enk_tax_reason=data.tax_reason,
			enk_business_fraction=float(business_fraction),
			enk_tax_deductible_fraction=float(tax_fraction),
			enk_tax_adjustment_reason=data.tax_adjustment_reason,
			enk_deductible_fraction=float(fraction),
			enk_vat_basis=float(nok_amount(net, currency.conversion_rate)),
			enk_expected_life_months=cint(data.get("expected_life_months")),
			items=[
				dict(
					item_name=data.description[:140],
					description=data.description,
					qty=1,
					uom="Nos",
					rate=float(expense),
					expense_account=settings.get(category + "_account"),
					cost_center=frappe.get_cached_value("Company", data.company, "cost_center"),
				)
			],
		)
	doc = frappe.get_doc(values)
	if private_amount:
		doc.append(
			"items",
			dict(
				item_name="Privat andel",
				description="Privat andel av kjøpet",
				qty=1,
				uom="Nos",
				rate=float(private_amount),
				expense_account=settings.withdrawal_account,
				cost_center=frappe.get_cached_value("Company", data.company, "cost_center"),
			),
		)
	if deductible:
		doc.append(
			"taxes",
			dict(
				charge_type="Actual",
				account_head=settings.input_vat_account,
				description="Fradragsberettiget MVA",
				tax_amount=float(deductible),
				category="Total",
				add_deduct_tax="Add",
			),
		)
	doc = _save_draft(doc, values, data.get("draft"))
	return dict(doctype=doc.doctype, name=doc.name, reused=False)


@frappe.whitelist(methods=["POST"])
def pay_purchase_privately(invoice, posting_date=None):
	doc = frappe.get_doc("Purchase Invoice", invoice)
	doc.check_permission("read")
	settings = get_settings(doc.company)
	frappe.has_permission("Journal Entry", "create", throw=True)
	frappe.db.get_value("Purchase Invoice", invoice, "name", for_update=True)
	doc.reload()
	key = _fingerprint(
		{
			"kind": "private_purchase",
			"company": doc.company,
			"invoice": doc.name,
		}
	)
	fingerprint = _fingerprint({"key": key, "posting_date": str(getdate(posting_date or today()))})
	if existing := frappe.db.get_value(
		"Journal Entry",
		{"enk_payment_key": key},
		["name", "enk_payment_fingerprint", "docstatus"],
		as_dict=True,
		for_update=True,
	):
		if existing.docstatus == 2:
			frappe.throw(
				"Privatbetalingen er annullert. Avklar korreksjonen før du oppretter en ny betaling."
			)
		if existing.enk_payment_fingerprint != fingerprint:
			frappe.throw(
				"Et privatbetalingsutkast finnes allerede med en annen dato. Kontroller det eksisterende bilaget."
			)
		frappe.get_doc("Journal Entry", existing.name).check_permission("read")
		return dict(doctype="Journal Entry", name=existing.name, reused=True)
	if doc.docstatus != 1 or doc.outstanding_amount <= 0 or doc.currency != "NOK":
		frappe.throw("Velg et bokført, ubetalt kjøp i NOK.")
	entry = frappe.get_doc(
		dict(
			doctype="Journal Entry",
			voucher_type="Journal Entry",
			company=doc.company,
			posting_date=posting_date or today(),
			user_remark="Kjøp betalt privat: " + doc.name,
			enk_payment_key=key,
			enk_payment_fingerprint=fingerprint,
			accounts=[
				dict(
					account=settings.payable_account,
					party_type="Supplier",
					party=doc.supplier,
					debit_in_account_currency=doc.outstanding_amount,
					reference_type="Purchase Invoice",
					reference_name=doc.name,
				),
				dict(account=settings.owner_account, credit_in_account_currency=doc.outstanding_amount),
			],
		)
	)
	entry.insert()
	from enk_norge.posting_contract import seal_draft

	entry.db_set("enk_posting_contract", seal_draft(entry))
	return dict(doctype=entry.doctype, name=entry.name)


@frappe.whitelist()
def dashboard(company):
	settings = get_settings(company)
	filters = {"company": company, "docstatus": 0}
	rows = frappe.db.sql(
		"""select a.root_type, g.account, sum(g.debit-g.credit) balance
		from `tabGL Entry` g join `tabAccount` a on a.name=g.account
		where g.company=%s and g.is_cancelled=0 and g.posting_date <= %s
		and g.voucher_type != 'Period Closing Voucher'
		group by a.root_type, g.account""",
		(company, today()),
		as_dict=True,
	)
	income = -sum(Decimal(str(row.balance)) for row in rows if row.root_type == "Income")
	expenses = sum(Decimal(str(row.balance)) for row in rows if row.root_type == "Expense")
	bank_balance = sum(
		Decimal(str(row.balance)) for row in rows if row.account == settings.bank_ledger_account
	)
	followup = frappe.get_list(
		"Sales Invoice",
		filters={"company": company, "docstatus": 1, "enk_vat_registration_pending": 1, "is_return": 0},
		fields=["name", "customer", "grand_total"],
		limit_page_length=0,
	)
	credited = {
		row.return_against: Decimal(str(row.amount))
		for row in frappe.db.sql(
			"""select return_against, sum(grand_total) amount from `tabSales Invoice`
			where company=%s and docstatus=1 and is_return=1 group by return_against""",
			company,
			as_dict=True,
		)
	}
	from enk_norge.norway_rules import vat_registration_threshold_crossings
	from enk_norge.validation import vat_turnover_events

	crossings = vat_registration_threshold_crossings(vat_turnover_events(company))
	return dict(
		vat_first_crossing=(dict(date=crossings[0].occurred_on.isoformat(), basis=str(crossings[0].registration_basis)) if crossings else None),
		company=company,
		vat_registered=bool(settings.vat_registered),
		income=str(income),
		expenses=str(expenses),
		result=str(income - expenses),
		bank_balance=str(bank_balance),
		bank_account_record=settings.bank_account_record,
		vat_followup=[
			row
			for row in followup
			if Decimal(str(row.grand_total)) + credited.get(row.name, Decimal(0)) > Decimal(".01")
		],
		draft_sales=frappe.get_list(
			"Sales Invoice", filters=filters, fields=["name", "customer", "grand_total"], limit_page_length=20
		),
		draft_purchases=frappe.get_list(
			"Purchase Invoice",
			filters=filters,
			fields=["name", "supplier", "grand_total"],
			limit_page_length=20,
		),
		unpaid_sales=frappe.get_list(
			"Sales Invoice",
			filters={"company": company, "docstatus": 1, "outstanding_amount": [">", 0]},
			fields=["name", "customer", "outstanding_amount", "due_date"],
			limit_page_length=20,
		),
	)


@frappe.whitelist(methods=["POST"])
def create_credit_note(doctype, name, posting_date, private_source_file=""):
	if doctype not in ("Sales Invoice", "Purchase Invoice"):
		frappe.throw("Velg en salgs- eller kjøpsfaktura.")
	# Samme original låses mens vi ser etter en eventuell tidligere full kreditnota.
	# Ellers kan to like API-kall lage hvert sitt utkast før noen av dem bokføres.
	frappe.db.get_value(doctype, name, "name", for_update=True)
	original = frappe.get_doc(doctype, name, for_update=True)
	original.check_permission("read")
	get_settings(original.company)
	frappe.has_permission(doctype, "create", throw=True)
	if original.docstatus != 1 or original.is_return:
		frappe.throw("Kreditnota krever en bokført originalfaktura.")
	date = getdate(posting_date)
	return_fields = ["name", "docstatus", "posting_date", "base_net_total"]
	if doctype == "Sales Invoice":
		return_fields.append("enk_deferral_reversal_journal_entry")
	returns = frappe.get_all(
		doctype,
		filters={
			"company": original.company,
			"return_against": original.name,
			"is_return": 1,
			"docstatus": ["<", 2],
		},
		fields=return_fields,
		limit_page_length=0,
	)
	if returns:
		full_amount = abs(Decimal(str(original.base_net_total or 0)))
		for existing in returns:
			if (
				existing.docstatus == 0
				and getdate(existing.posting_date) == date
				and abs(Decimal(str(existing.base_net_total or 0))) == full_amount
			):
				draft = frappe.get_doc(doctype, existing.name)
				draft.check_permission("read")
				result = dict(doctype=doctype, name=draft.name, reused=True)
				if doctype == "Sales Invoice" and draft.enk_deferral_reversal_journal_entry:
					result["deferral_reversal"] = dict(
						doctype="Journal Entry", name=draft.enk_deferral_reversal_journal_entry, reused=True
					)
				return result
		frappe.throw(
			"Originalfakturaen har allerede en kreditnota. Bruk den eksisterende kreditnotaen eller opprett en dokumentert delkreditering manuelt."
		)
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	doc = make_return_doc(doctype, name)
	doc.posting_date = date
	doc.set_posting_time = 1
	doc.enk_tax_treatment = original.enk_tax_treatment
	doc.enk_delivery_date = original.enk_delivery_date
	doc.enk_delivery_description = original.enk_delivery_description
	if doctype == "Purchase Invoice":
		doc.enk_vat_basis = -abs(original.enk_vat_basis)
		doc.enk_deductible_fraction = original.enk_deductible_fraction
	else:
		doc.naming_series = original.naming_series
	doc.insert()
	result = dict(doctype=doc.doctype, name=doc.name)
	if doctype == "Sales Invoice" and any(item.enable_deferred_revenue for item in original.items):
		for item in doc.items:
			item.enable_deferred_revenue = 0
		doc.save()
		from enk_norge.deferrals import create_credit_reversal_draft

		reversal = create_credit_reversal_draft(doc, private_source_file)
		if reversal:
			result["deferral_reversal"] = reversal
	return result
