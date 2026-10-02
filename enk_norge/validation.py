"""Kontroller som også gjelder når dokumenter opprettes utenfor ENK-siden."""

import re
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe.utils import cint, getdate


def validate_setup_values(data):
	from enk_norge.norway_rules import validate_bank_account, validate_org_number

	for key in (
		"organization_number",
		"bank_account",
		"start_date",
		"address_line",
		"postal_code",
		"city",
		"phone",
		"bank_name",
	):
		if not data.get(key):
			frappe.throw(f"Oppsettet mangler {key}.")
	if not validate_org_number(data.get("organization_number")):
		frappe.throw("Organisasjonsnummeret har feil format eller kontrollsiffer.")
	if not validate_bank_account(data.get("bank_account")):
		frappe.throw("Bankkontoen har feil format eller kontrollsiffer.")
	if getdate(data["start_date"]).year != 2026:
		frappe.throw("Regelsettet er foreløpig verifisert for regnskapsåret 2026.")
	if not re.fullmatch(r"\d{4}", data["postal_code"]):
		frappe.throw("Postnummeret må ha fire siffer.")
	if not cint(data.get("history_confirmed")):
		frappe.throw("Kontroller tidligere regnskap og fakturaer før du starter.")
	if cint(data.get("vat_registered")) and not data.get("vat_registration_date"):
		frappe.throw("Oppgi fra hvilken dato MVA-registreringen gjelder.")


def validate_transaction(doc, method=None):
	if not doc.get("company") or not frappe.db.exists("ENK Settings", doc.company):
		return
	from enk_norge.setup import get_settings

	settings = get_settings(doc.company)
	if not frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger"):
		frappe.throw("Uforanderlig hovedbok må være aktivert for ENK-bokføring.")
	posting = getdate(doc.posting_date)
	if posting < getdate(settings.start_date):
		frappe.throw("Datoen er før regnskapsstart i ENK-oppsettet.")
	if settings.frozen_through and posting <= getdate(settings.frozen_through):
		frappe.throw("Perioden er stengt i ENK-oppsettet. Dokumentet kan ikke bokføres eller endres.")
	from enk_norge.deferrals import is_supported_deferral_posting

	if posting.year != 2026 and not (_is_prior_year_settlement(doc) or is_supported_deferral_posting(doc)):
		frappe.throw("Norske regler for dette regnskapsåret er ikke verifisert ennå.")
	if doc.doctype == "Journal Entry":
		from enk_norge.banking import validate_currency_adjustment_operation

		validate_currency_adjustment_operation(doc)
		if method == "before_cancel":
			from enk_norge.deferrals import validate_deferral_cancellation

			validate_deferral_cancellation(doc)
		if method == "before_submit" and doc.voucher_type in ("Asset Disposal", "Depreciation Entry"):
			_validate_asset_disposal(doc, settings)
	if doc.doctype not in ("Sales Invoice", "Purchase Invoice"):
		if method == "before_submit":
			_validate_posting_source(doc, settings)
		return
	from enk_norge.currency import validate_currency_document

	validate_currency_document(doc)
	if doc.doctype == "Sales Invoice":
		from enk_norge.deferrals import validate_deferred_revenue_invoice

		validate_deferred_revenue_invoice(doc, method)
		_validate_native_asset_sale(doc)
		if not doc.get("enk_delivery_date") or not doc.get("enk_delivery_description"):
			frappe.throw("Oppgi leveringsdato og hva som er levert før fakturaen bokføres.")
		if not doc.get("customer_address"):
			frappe.throw("Kunden må ha en fakturaadresse.")
		if not doc.get("enk_tax_treatment"):
			frappe.throw("Velg norsk avgiftsbehandling før fakturaen bokføres.")
		from enk_norge.setup import is_invoice_number

		if not doc.is_return and not is_invoice_number(settings, doc.name):
			frappe.throw("Kladden har nummer fra en annen fakturaserie. Slett kladden og lag fakturaen på nytt.")
		registered = settings.vat_registered and posting >= getdate(settings.vat_registration_date)
		issuer_registered = registered
		if doc.is_return and doc.return_against:
			original = frappe.get_doc("Sales Invoice", doc.return_against)
			if (
				original.company != doc.company
				or original.customer != doc.customer
				or original.docstatus != 1
			):
				frappe.throw("Kreditnotaen må vise en bokført faktura for samme foretak og kunde.")
			if doc.enk_tax_treatment != original.enk_tax_treatment:
				frappe.throw("Kreditnotaen må reversere den opprinnelige avgiftsbehandlingen.")
			if original.enk_invoice_snapshot:
				registered = frappe.parse_json(original.enk_invoice_snapshot).get("vat_registered", False)
			_validate_returned_invoice_items(doc, original)
		_validate_sale_taxes(doc, settings, registered)
		if method == "before_submit" and not registered and not doc.is_return:
			_validate_vat_threshold(doc, settings)
		if method == "before_submit":
			doc.enk_invoice_snapshot = frappe.as_json(
				{
					key: settings.get(key)
					for key in (
						"organization_number",
						"bank_account",
						"address_line",
						"postal_code",
						"city",
						"phone",
					)
				}
				| {"vat_registered": bool(issuer_registered), "company_name": doc.company}
			)
		if not registered and any(Decimal(str(t.tax_amount or 0)) != 0 for t in doc.taxes):
			frappe.throw("Foretaket kan ikke fakturere med MVA før registreringen gjelder.")
	if doc.doctype == "Purchase Invoice":
		if doc.is_return and doc.return_against:
			original = frappe.get_doc("Purchase Invoice", doc.return_against)
			if (
				original.company != doc.company
				or original.supplier != doc.supplier
				or original.docstatus != 1
			):
				frappe.throw("Kreditnotaen må vise et bokført kjøp for samme foretak og leverandør.")
			_validate_returned_invoice_items(doc, original)
		registered = settings.vat_registered and posting >= getdate(settings.vat_registration_date)
		_validate_purchase_taxes(doc, settings, registered)
		if not registered and any(Decimal(str(t.tax_amount or 0)) != 0 for t in doc.taxes):
			frappe.throw("MVA er en del av kostnaden når foretaket ikke er MVA-registrert. Ikke før fradrag.")
		if doc.get("enk_tax_treatment") == "Foreign services" and doc.taxes:
			frappe.throw("Omvendt MVA på utenlandsk tjeneste føres separat fra leverandørens krav.")
		if not doc.bill_no or not doc.bill_date:
			frappe.throw("Oppgi leverandørens bilagsnummer og dato.")
		if not frappe.db.exists(
			"File", {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_private": 1}
		):
			frappe.throw("Legg ved originalbilaget som privat fil før kjøpet bokføres.")


def _validate_posting_source(doc, settings):
	from enk_norge.posting_contract import PostingContractError, validate_contract

	if doc.get("enk_posting_contract"):
		try:
			validate_contract(doc)
		except PostingContractError as error:
			frappe.throw(str(error))
		if doc.doctype == "Journal Entry":
			from enk_norge.settlement import validate_settlement_entry

			validate_settlement_entry(doc)
			if doc.get("enk_deferral_details"):
				from enk_norge.deferrals import validate_deferral_entry

				validate_deferral_entry(doc)
		return
	if not set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}:
		frappe.throw(
			"Bruk ENK-flyten for betaling og eiertransaksjoner. Fri journalføring krever regnskapsansvarlig."
		)
	if not (doc.get("enk_manual_reason") or "").strip():
		frappe.throw("Manuell føring krever en forklaring i «Grunnlag for manuell føring».")
	if not frappe.db.exists(
		"File", {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_private": 1}
	):
		frappe.throw("Legg ved et privat kildebilag før den manuelle føringen bokføres.")
	tax_accounts = {settings.input_vat_account, settings.output_vat_account, settings.reverse_vat_account}
	accounts = {row.account for row in (doc.get("accounts") or [])} | {
		row.account for row in (doc.get("deductions") or [])
	}
	accounts.update(row.account_head for row in (doc.get("taxes") or []))
	accounts.update(filter(None, (doc.get("paid_from"), doc.get("paid_to"))))
	if accounts & tax_accounts:
		frappe.throw(
			"Direkte avgiftsføring mangler norsk rapportgrunnlag. Bruk faktura eller ENK-flyten for omvendt MVA."
		)


def protect_delete(doc, method=None):
	if doc.doctype in ("ENK Year Report", "ENK VAT Return") and doc.get("status") == "Manually filed":
		frappe.throw("En innlevert rapport og leveringskvitteringen skal bevares.")
	if doc.get("company") and frappe.db.exists("ENK Settings", doc.company):
		if doc.docstatus != 0:
			frappe.throw(
				"Bokførte og annullerte dokumenter skal bevares. Bruk kreditnota eller korrigeringsbilag."
			)


def protect_rename(doc, method=None, old=None, new=None, merge=False):
	if doc.get("company") and frappe.db.exists("ENK Settings", doc.company):
		frappe.throw("Dokumentnummeret kan ikke endres i et ENK-regnskap.")


def protect_file(doc, method=None):
	if frappe.db.exists("ENK Tax Pool", {"opening_source_file": doc.name}):
		frappe.throw("Dokumentasjon av inngående skattesaldo skal bevares.")
	if frappe.db.exists("DocType", "ENK Settlement") and frappe.db.exists(
		"ENK Settlement", {"source_file": doc.name, "status": "Ready for review"}
	):
		frappe.throw("Oppgjørets kildefil skal bevares. Bruk et korrigerende oppgjør ved feil.")
	if doc.attached_to_doctype in ("ENK Year Report", "ENK VAT Return") and doc.attached_to_name:
		parent = frappe.get_doc(doc.attached_to_doctype, doc.attached_to_name)
		if parent.status == "Manually filed":
			frappe.throw("Vedlegg og kvittering til en innlevert rapport skal bevares.")
	if (
		doc.attached_to_doctype
		in ("Sales Invoice", "Purchase Invoice", "Journal Entry", "Payment Entry", "ENK Bank Import")
		and doc.attached_to_name
	):
		parent = frappe.get_doc(doc.attached_to_doctype, doc.attached_to_name)
		if parent.docstatus != 0 and frappe.db.exists("ENK Settings", parent.company):
			frappe.throw("Bilag til et bokført dokument skal bevares. Legg til en rettelse som nytt vedlegg.")


def _validate_sale_taxes(doc, settings, registered):
	treatment = doc.enk_tax_treatment
	allowed = ("Domestic 25", "Domestic 15", "Domestic 12", "Export services", "Exempt", "Not registered")
	if treatment not in allowed:
		frappe.throw("Velg en støttet avgiftsbehandling.")
	if treatment == "Exempt" and not (doc.get("enk_tax_reason") or "").strip():
		frappe.throw("Oppgi regel og begrunnelse for at leveransen er unntatt fra MVA.")
	if registered and treatment == "Not registered":
		frappe.throw("Foretaket er MVA-registrert på denne datoen.")
	if not registered and treatment.startswith("Domestic"):
		frappe.throw("MVA kan ikke faktureres før registreringen gjelder.")
	rate = Decimal(treatment.split()[1]) if treatment.startswith("Domestic") else Decimal(0)
	expected = (Decimal(str(doc.net_total)) * rate / 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
	actual = sum(Decimal(str(t.tax_amount or 0)) for t in doc.taxes)
	if abs(actual - expected) > Decimal(".01"):
		frappe.throw("MVA-beløpet stemmer ikke med valgt norsk avgiftsbehandling.")
	if any(t.account_head != settings.output_vat_account for t in doc.taxes):
		frappe.throw("Bruk konto for utgående MVA fra ENK-oppsettet.")
	address = frappe.get_doc("Address", doc.customer_address)
	if not any(row.link_doctype == "Customer" and row.link_name == doc.customer for row in address.links):
		frappe.throw("Fakturaadressen må tilhøre valgt kunde.")
	if treatment == "Export services":
		if (
			address.country == "Norway"
			or frappe.db.get_value("Customer", doc.customer, "customer_type") != "Company"
		):
			frappe.throw("Denne eksportflyten gjelder fjernleverbare tjenester til utenlandske bedrifter.")
	elif address.country != "Norway":
		frappe.throw("Utenlandsk kunde krever egen avgiftsbehandling.")
	if doc.is_return and not doc.return_against:
		frappe.throw("En kreditnota må vise hvilken faktura den korrigerer.")


def _returned_item_amount(row):
	"""Beløpet på linjen, uten fortegn. Returer skal sammenlignes med originalens nettolinje."""
	return abs(Decimal(str(row.get("base_net_amount") or 0)))


def _validate_returned_invoice_items(doc, original):
	"""En original linje kan bare krediteres opp til opprinnelig nettobeløp, også på tvers av delkrediteringer."""
	if not doc.is_return or not doc.return_against:
		return
	if doc.return_against != original.name:
		frappe.throw("Kreditnotaen viser ikke til riktig originalfaktura.")
	tables = {
		"Sales Invoice": ("tabSales Invoice", "tabSales Invoice Item", "sales_invoice_item"),
		"Purchase Invoice": ("tabPurchase Invoice", "tabPurchase Invoice Item", "purchase_invoice_item"),
	}
	if doc.doctype not in tables:
		frappe.throw("Kreditnotaen har ukjent dokumenttype.")
	parent_table, item_table, item_field = tables[doc.doctype]
	# Alle native delkrediteringer av samme original går gjennom denne låsen. SELECT FOR UPDATE
	# er en current read, slik at neste transaksjon ser den første kreditnotaens bokførte linjer.
	frappe.db.sql(f"select name from `{parent_table}` where name=%s for update", original.name)
	original_items = {row.name: row for row in original.items}
	credited = {name: Decimal() for name in original_items}
	for row in frappe.db.sql(
		f"""select item.`{item_field}` linked_item, item.base_net_amount
		from `{parent_table}` return_doc
		join `{item_table}` item on item.parent=return_doc.name
		where return_doc.company=%s and return_doc.return_against=%s
		and return_doc.is_return=1 and return_doc.docstatus=1 and return_doc.name != %s
		for update""",
		(doc.company, original.name, doc.name),
		as_dict=True,
	):
		if row.linked_item in credited:
			credited[row.linked_item] += _returned_item_amount(row)
	for row in doc.items:
		linked_item = row.get(item_field)
		if linked_item not in original_items:
			frappe.throw("Hver kreditnotalinje må vise til en linje på originalfakturaen.")
		amount = _returned_item_amount(row)
		if amount <= 0:
			frappe.throw("Kreditnotalinjer må ha et beløp som reverserer originalfakturaen.")
		credited[linked_item] += amount
		if credited[linked_item] - _returned_item_amount(original_items[linked_item]) > Decimal(".01"):
			frappe.throw("Kreditnotaen overstiger beløpet som gjenstår på en original fakturalinje.")


def _validate_native_asset_sale(doc):
	if any(cint(row.get("is_fixed_asset")) or row.get("asset") for row in doc.items):
		frappe.throw(
			"Native salg av driftsmiddel støttes ikke for ENK. Bruk den dokumenterte ENK-flyten for driftsmiddelavgang."
		)


def validate_unsupported_native_accounting(doc, method=None):
	"""Stopp lager- og POS-flyter som kan skrive hovedbok uten ENK-kildekontrakt."""
	if not doc.get("company") or not frappe.db.exists("ENK Settings", doc.company):
		return
	from enk_norge.setup import get_settings

	settings = get_settings(doc.company)
	posting = getdate(doc.posting_date)
	if posting < getdate(settings.start_date):
		frappe.throw("Datoen er før regnskapsstart i ENK-oppsettet.")
	if settings.frozen_through and posting <= getdate(settings.frozen_through):
		frappe.throw("Perioden er stengt i ENK-oppsettet. Dokumentet kan ikke bokføres eller endres.")
	frappe.throw(f"{doc.doctype} støttes ikke for ENK-bokføring. Bruk ENK-faktura, betaling eller dokumentert journalføring.")


def validate_company_perpetual_inventory(doc, method=None):
	if doc.name and frappe.db.exists("ENK Settings", doc.name) and cint(doc.get("enable_perpetual_inventory")):
		frappe.throw("Evigvarende lager er ikke støttet for ENK-flyten.")


def validate_subscription(doc, method=None):
	"""ERPNext oppretter og kan bokføre første faktura i Subscription.after_insert."""
	if not doc.get("company") or not frappe.db.exists("ENK Settings", doc.company):
		return
	if cint(doc.get("submit_invoice")):
		frappe.throw(
			"ENK-abonnement kan ikke auto-bokføre fakturaer. Slå av «Submit Generated Invoices» og bruk kontrollert ENK-fakturautkast."
		)


def validate_subscription_invoice_creation(doc, method=None):
	"""Native Subscription-faktura mangler ENKs avtale, leverings- og periodiseringsgrunnlag."""
	if (
		doc.get("subscription")
		and doc.get("company")
		and frappe.db.exists("ENK Settings", doc.company)
		and (not doc.get("enk_external_id") or not any(cint(row.enable_deferred_revenue) for row in doc.items))
	):
		frappe.throw("Native abonnementfaktura kan ikke opprettes for ENK. Bruk kontrollert ENK-fakturautkast.")


def protect_file_update(doc, method=None):
	old = doc.get_doc_before_save()
	if old and any(
		old.get(key) != doc.get(key)
		for key in ("file_url", "is_private", "attached_to_doctype", "attached_to_name", "content_hash")
	):
		protect_file(old)


def vat_turnover_events(company, exclude=None):
	from enk_norge.norway_rules import TurnoverEvent, VATTreatment

	treatments = {"Exempt": VATTreatment.EXEMPT, "Export services": VATTreatment.ZERO_RATED}
	for value in ("Domestic 25", "Domestic 15", "Domestic 12", "Not registered"):
		treatments[value] = VATTreatment.TAXABLE
	filters = {"company": company, "docstatus": 1}
	if exclude:
		filters["name"] = ["!=", exclude]
	rows = frappe.get_all("Sales Invoice", filters=filters,
		fields=["enk_delivery_date", "enk_tax_treatment", "base_net_total"])
	events = []
	for row in rows:
		if not row.enk_delivery_date or row.enk_tax_treatment not in treatments:
			frappe.throw("MVA-historikken inneholder et salg uten kjent levering eller avgiftsbehandling.")
		events.append(TurnoverEvent(getdate(row.enk_delivery_date), Decimal(str(row.base_net_total)), treatments[row.enk_tax_treatment]))
	settings = frappe.get_doc("ENK Settings", company)
	for row in frappe.db.sql(
		"""select entry.name, entry.posting_date, sum(line.debit_in_account_currency-line.credit_in_account_currency) proceeds
		from `tabJournal Entry` entry join `tabJournal Entry Account` line on line.parent=entry.name
		where entry.company=%s and entry.docstatus=1 and entry.voucher_type='Asset Disposal'
		and line.account=%s and entry.name != %s group by entry.name, entry.posting_date""",
		(company, settings.bank_ledger_account, exclude or ""), as_dict=True):
		if Decimal(str(row.proceeds)) > 0:
			events.append(TurnoverEvent(getdate(row.posting_date), Decimal(str(row.proceeds)), VATTreatment.TAXABLE))
	return events


def _validate_vat_threshold(doc, settings):
	from enk_norge.norway_rules import TurnoverEvent, VATTreatment, vat_registration_threshold_crossings

	# Samtidig bokføring må ikke slippe to fakturaer forbi samme grense.
	frappe.db.sql("select name from `tabCompany` where name=%s for update", doc.company)
	treatment = VATTreatment.EXEMPT if doc.enk_tax_treatment == "Exempt" else VATTreatment.ZERO_RATED if doc.enk_tax_treatment == "Export services" else VATTreatment.TAXABLE
	events = vat_turnover_events(doc.company, exclude=doc.name)
	events.append(TurnoverEvent(getdate(doc.enk_delivery_date), Decimal(str(doc.base_net_total)), treatment))
	crossings = vat_registration_threshold_crossings(events)
	if crossings and not doc.enk_vat_registration_pending:
		first = crossings[0]
		frappe.throw(
			f"Salgsgrunnlaget passerer 50 000 kroner {first.occurred_on}: {first.registration_basis} NOK over tolv måneder. "
			"Avklar registrering og alle berørte salg fra grensepasseringen. Hvis du utsteder uten MVA mens registreringen behandles, "
			"bekreft «MVA-registrering følges opp» og korriger hele det berørte salget når registreringen gjelder."
		)


def _validate_purchase_taxes(doc, settings, registered):
	from decimal import InvalidOperation

	try:
		fraction = Decimal(str(doc.get("enk_deductible_fraction", 1)))
		tax_fraction = Decimal(str(doc.get("enk_tax_deductible_fraction", 1)))
		business_fraction = Decimal(str(doc.get("enk_business_fraction", 1)))
		basis = Decimal(str(doc.get("enk_vat_basis") or 0))
		if (
			not fraction.is_finite()
			or not tax_fraction.is_finite()
			or not 0 <= tax_fraction <= 1
			or not business_fraction.is_finite()
			or not basis.is_finite()
			or not 0 < business_fraction <= 1
			or not 0 <= fraction <= business_fraction
		):
			raise ValueError
	except InvalidOperation, ValueError:
		frappe.throw(
			"MVA-grunnlag og andeler må være gyldige tall. MVA-fradragsandelen kan ikke overstige virksomhetsandelen."
		)
	private_total = sum(
		Decimal(str(row.base_net_amount or 0))
		for row in doc.items
		if row.expense_account == settings.withdrawal_account
	)
	expected_private = (Decimal(str(doc.base_grand_total)) * (1 - business_fraction)).quantize(
		Decimal(".01"), rounding=ROUND_HALF_UP
	)
	if abs(private_total - expected_private) > Decimal(".01"):
		frappe.throw("Privat andel må føres på eierens uttakskonto og stemme med virksomhetsandelen.")
	treatment = doc.get("enk_tax_treatment")
	if tax_fraction < 1:
		if not (doc.get("enk_tax_adjustment_reason") or "").strip():
			frappe.throw("Redusert skattemessig fradrag krever begrunnelse.")
		if treatment == "Foreign services" or any(
			frappe.get_cached_value("Account", row.expense_account, "root_type") == "Asset"
			for row in doc.items
		):
			frappe.throw(
				"Redusert skattefradrag for eiendel eller utenlandsk tjeneste krever særskilt årsjustering."
			)
	if not treatment:
		frappe.throw("Velg norsk avgiftsbehandling for kjøpet.")
	if treatment == "Foreign services":
		if business_fraction != 1:
			frappe.throw("Utenlandske tjenester med privat andel krever særskilt avgiftsavklaring.")
		country = frappe.db.get_value("Supplier", doc.supplier, "country")
		if not country or country == "Norway":
			frappe.throw("Utenlandsk tjeneste krever at leverandørens utenlandske hjemland er oppgitt.")
		if abs(basis - Decimal(str(doc.base_net_total))) > Decimal(".01"):
			frappe.throw("MVA-grunnlaget for utenlandsk tjeneste må stemme med kjøpet i NOK.")
		return
	if treatment.startswith("Domestic"):
		if treatment not in ("Domestic 25", "Domestic 15", "Domestic 12") or not registered:
			frappe.throw("Denne MVA-behandlingen krever registrert foretak og kjent sats.")
		rate = Decimal(treatment.split()[1])
		expected_gross = (basis * (1 + rate / 100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
		if abs(expected_gross - Decimal(str(doc.base_grand_total))) > Decimal(".01"):
			frappe.throw("MVA-grunnlaget må stemme med hele kjøpet før fordeling av fradrag og privat andel.")
		expected = (basis * rate / 100 * fraction).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
		actual = sum(Decimal(str(row.base_tax_amount or 0)) for row in doc.taxes)
		if abs(expected - actual) > Decimal(".01") or any(
			row.account_head != settings.input_vat_account for row in doc.taxes
		):
			frappe.throw("Inngående MVA stemmer ikke med grunnlag, sats og fradragsandel.")
	elif treatment == "No input VAT":
		if not (doc.get("enk_tax_reason") or "").strip() or any(row.tax_amount for row in doc.taxes):
			frappe.throw("Kjøp uten MVA må ha begrunnelse og kan ikke ha avgiftsfradrag.")
	elif treatment == "Not registered":
		original_without_vat = (
			doc.is_return
			and doc.return_against
			and frappe.db.get_value("Purchase Invoice", doc.return_against, "enk_tax_treatment")
			== "Not registered"
		)
		if (registered and not original_without_vat) or any(row.tax_amount for row in doc.taxes):
			frappe.throw("Velg uttrykkelig kjøp uten MVA med begrunnelse når foretaket er registrert.")
	else:
		frappe.throw("Kjøpet må ha kjent norsk MVA-behandling.")


def _is_prior_year_settlement(doc):
	"""Oppgjør av kjente 2026-fakturaer krever ingen antatte 2027-avgiftssatser."""
	if getdate(doc.posting_date).year != 2027 or not doc.get("enk_posting_contract"):
		return False
	if doc.doctype == "Journal Entry" and doc.get("enk_fx_payment_entry"):
		payment = frappe.get_doc("Payment Entry", doc.enk_fx_payment_entry)
		return payment.company == doc.company and _is_prior_year_settlement(payment)
	if doc.doctype != "Payment Entry" or not doc.references:
		return False
	for row in doc.references:
		if row.reference_doctype not in ("Sales Invoice", "Purchase Invoice"):
			return False
		invoice = frappe.get_doc(row.reference_doctype, row.reference_name)
		if invoice.company != doc.company or invoice.docstatus != 1 or getdate(invoice.posting_date).year != 2026:
			return False
	return True


def _validate_asset_disposal(doc, settings):
	frappe.db.sql("select name from `tabCompany` where name=%s for update", doc.company)
	if doc.voucher_type == "Asset Disposal":
		if settings.vat_registered and getdate(doc.posting_date) >= getdate(settings.vat_registration_date):
			frappe.throw("Avgang etter MVA-registrering krever en egen dokumentert avgiftsflyt.")
		from enk_norge.norway_rules import TurnoverEvent, VATTreatment, vat_registration_threshold_crossings

		proceeds = sum(Decimal(str(row.debit_in_account_currency or 0))-Decimal(str(row.credit_in_account_currency or 0)) for row in doc.accounts if row.account == settings.bank_ledger_account)
		if proceeds > 0:
			events = vat_turnover_events(doc.company, exclude=doc.name)
			events.append(TurnoverEvent(getdate(doc.posting_date), proceeds, VATTreatment.TAXABLE))
			if vat_registration_threshold_crossings(events):
				frappe.throw("Salg av driftsmiddel medfører passering av MVA-grensen. Avklar registrering og fakturaflyt før avgangen bokføres.")
	if doc.voucher_type == "Asset Disposal" and not frappe.db.exists("File", {"attached_to_doctype": "Journal Entry", "attached_to_name": doc.name, "is_private":1}):
		frappe.throw("Driftsmiddelavgang krever privat dokumentasjon av vederlag og bokført verdi.")
	frappe.db.sql("select name from `tabCompany` where name=%s for update", doc.company)
	carrying = sum(Decimal(str(row.credit_in_account_currency or 0)) - Decimal(str(row.debit_in_account_currency or 0)) for row in doc.accounts if row.account == settings.asset_account)
	balance = frappe.db.sql("select coalesce(sum(debit-credit),0) from `tabGL Entry` where company=%s and account=%s and is_cancelled=0 and posting_date<=%s", (doc.company,settings.asset_account,doc.posting_date))[0][0]
	if carrying < 0 or carrying > Decimal(str(balance)):
		frappe.throw("Avgangen overstiger tilgjengelig bokført driftsmiddelverdi.")
