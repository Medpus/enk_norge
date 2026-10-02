"""Bilagsliste og bilagsvisning for ENK-siden.

ERPNext eier dokumentene og bokføringen. Her samler vi bare det brukeren trenger for å se,
bokføre eller slette en kladd uten å åpne ERPNexts skjema.
"""

import frappe
from frappe.utils import add_days, add_months, flt, getdate, today

from enk_norge.setup import get_settings

DOCTYPES = {
	"Sales Invoice": "customer_name",
	"Purchase Invoice": "supplier_name",
	"Payment Entry": "party_name",
	"Journal Entry": None,
}
KINDS = {
	"sales": ("Sales Invoice",),
	"purchases": ("Purchase Invoice",),
	"other": ("Payment Entry", "Journal Entry"),
}


def _check_doctype(doctype):
	if doctype not in DOCTYPES:
		frappe.throw("Dokumenttypen vises ikke i ENK Norge.")


def _list_fields(doctype):
	fields = ["name", "posting_date", "docstatus", "modified"]
	party = DOCTYPES[doctype]
	if party:
		fields.append(f"{party} as party")
	if doctype in ("Sales Invoice", "Purchase Invoice"):
		fields += ["grand_total as total", "outstanding_amount", "currency", "is_return", "due_date"]
		if doctype == "Purchase Invoice":
			fields.append("enk_payment_method as payment_method")
	elif doctype == "Payment Entry":
		fields += ["paid_amount as total", "payment_type", "paid_from_account_currency as currency"]
	else:
		fields += ["total_debit as total", "user_remark as description", "voucher_type"]
	return fields


def _status(doctype, row):
	if row.docstatus == 0:
		return "draft"
	if row.docstatus == 2:
		return "cancelled"
	if doctype in ("Sales Invoice", "Purchase Invoice"):
		if row.get("is_return"):
			return "credit_note"
		if flt(row.get("outstanding_amount")) > 0.005:
			if doctype == "Sales Invoice" and row.get("due_date") and getdate(row.due_date) < getdate(today()):
				return "overdue"
			return "unpaid"
		return "paid"
	return "posted"


@frappe.whitelist()
def list_documents(company, kind="all", search="", limit=50, from_date=None, to_date=None, account=None):
	get_settings(company)
	doctypes = KINDS.get(kind) or tuple(DOCTYPES)
	limit = min(max(int(limit or 50), 1), 200)
	search = (search or "").strip()
	# Fra oversikten: bare bilag som har postert på kontoen i perioden.
	vouchers = _vouchers_on_account(company, account, from_date, to_date) if account else None
	rows = []
	for doctype in doctypes:
		filters = {"company": company}
		if from_date and to_date:
			filters["posting_date"] = ["between", [from_date, to_date]]
		or_filters = None
		if search:
			or_filters = {"name": ["like", f"%{search}%"]}
			if DOCTYPES[doctype]:
				or_filters[DOCTYPES[doctype]] = ["like", f"%{search}%"]
		# Betalinger vises i fakturaen sin. Ved filter på en konto skal de likevel med.
		settling = (
			_settling_entries(company)
			if kind == "all" and not account and doctype in ("Payment Entry", "Journal Entry")
			else set()
		)
		for row in frappe.get_list(
			doctype,
			filters=filters,
			or_filters=or_filters,
			fields=_list_fields(doctype),
			order_by="posting_date desc, modified desc",
			limit_page_length=limit,
		):
			if (doctype, row.name) in settling:
				continue
			if vouchers is not None and (doctype, row.name) not in vouchers:
				continue
			row.doctype = doctype
			row.status = _status(doctype, row)
			row.total = str(flt(row.get("total"), 2))
			if "outstanding_amount" in row:
				row.outstanding_amount = str(flt(row.outstanding_amount, 2))
			row.posting_date = str(row.posting_date) if row.posting_date else None
			if row.get("due_date"):
				row.due_date = str(row.due_date)
			row.pop("modified", None)
			rows.append(row)
	rows.sort(key=lambda row: (row.posting_date or "", row.name), reverse=True)
	return rows[:limit]


def _vouchers_on_account(company, account, from_date=None, to_date=None):
	if frappe.db.get_value("Account", account, "company") != company:
		frappe.throw("Kontoen tilhører et annet foretak.")
	conditions = "company=%(company)s and account=%(account)s and is_cancelled=0"
	if from_date and to_date:
		conditions += " and posting_date between %(from_date)s and %(to_date)s"
	rows = frappe.db.sql(
		f"select distinct voucher_type, voucher_no from `tabGL Entry` where {conditions}",
		dict(company=company, account=account, from_date=from_date, to_date=to_date),
	)
	return {tuple(row) for row in rows}


# Navn på kostnadskontoene slik brukeren kjenner dem fra kjøpsskjemaet.
EXPENSE_LABELS = (
	("software_account", "Programvare og abonnementer"),
	("equipment_account", "Utstyr"),
	("expense_account", "Annen driftskostnad"),
	("fees_account", "Bank- og betalingsgebyr"),
	("depreciation_account", "Avskrivning av utstyr"),
)


@frappe.whitelist()
def overview(company, year=None):
	"""Inntekter og kostnader per måned og kostnader per type, fra hovedboken."""
	settings = get_settings(company)
	frappe.has_permission("GL Entry", "read", throw=True)
	year = int(year or getdate(today()).year)
	rows = frappe.db.sql(
		"""select month(g.posting_date) month, a.root_type, g.account, a.account_name,
			sum(g.debit - g.credit) amount
		from `tabGL Entry` g join `tabAccount` a on a.name = g.account
		where g.company = %(company)s and g.is_cancelled = 0
		and g.voucher_type != 'Period Closing Voucher'
		and a.root_type in ('Income', 'Expense')
		and g.posting_date between %(start)s and %(end)s
		group by month(g.posting_date), a.root_type, g.account, a.account_name""",
		dict(company=company, start=f"{year}-01-01", end=f"{year}-12-31"),
		as_dict=True,
	)
	months = [dict(month=m, income=0.0, expense=0.0) for m in range(1, 13)]
	categories = {}
	labels = {settings.get(field): label for field, label in EXPENSE_LABELS if settings.get(field)}
	for row in rows:
		amount = flt(row.amount, 2)
		if row.root_type == "Income":
			months[row.month - 1]["income"] += -amount
		else:
			months[row.month - 1]["expense"] += amount
			category = categories.setdefault(
				row.account, dict(account=row.account, label=labels.get(row.account, row.account_name), amount=0.0)
			)
			category["amount"] += amount
	for month in months:
		month["income"] = flt(month["income"], 2)
		month["expense"] = flt(month["expense"], 2)
	return dict(
		year=year,
		months=months,
		categories=sorted(
			(dict(c, amount=flt(c["amount"], 2)) for c in categories.values() if abs(c["amount"]) >= 0.005),
			key=lambda c: -c["amount"],
		),
	)


def _settling_entries(company):
	"""Bokførte betalinger og private oppgjør som bare gjør opp en faktura. De vises i fakturaen."""
	rows = frappe.db.sql(
		"""select 'Payment Entry', pe.name from `tabPayment Entry` pe
		where pe.company = %(company)s and pe.docstatus = 1
		and exists (select 1 from `tabPayment Entry Reference` r where r.parent = pe.name)
		union all
		select 'Journal Entry', je.name from `tabJournal Entry` je
		where je.company = %(company)s and je.docstatus = 1 and je.enk_payment_key is not null
		and exists (
			select 1 from `tabJournal Entry Account` a
			where a.parent = je.name and a.reference_type in ('Sales Invoice', 'Purchase Invoice')
		)""",
		dict(company=company),
	)
	return {tuple(row) for row in rows}


def _load(doctype, name):
	_check_doctype(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	get_settings(doc.company)
	return doc


def _attachments(doc):
	return frappe.get_all(
		"File",
		filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
		fields=["name", "file_name", "file_url", "is_private", "creation"],
		order_by="creation asc",
	)


def _lines(doc):
	if doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		return [
			dict(
				description=row.description or row.item_name,
				qty=flt(row.qty),
				rate=str(flt(row.rate, 2)),
				amount=str(flt(row.amount, 2)),
				deferred=bool(row.get("enable_deferred_revenue") or row.get("enable_deferred_expense")),
			)
			for row in doc.items
		]
	if doc.doctype == "Journal Entry":
		names = {
			row.account: frappe.db.get_value("Account", row.account, "account_name") or row.account
			for row in doc.accounts
		}
		return [
			dict(
				description=names[row.account],
				debit=str(flt(row.debit, 2)),
				credit=str(flt(row.credit, 2)),
			)
			for row in doc.accounts
		]
	return [
		dict(
			description=row.reference_name,
			reference_doctype=row.reference_doctype,
			amount=str(flt(row.allocated_amount, 2)),
		)
		for row in doc.references
	]


def _summary(doc):
	party_field = DOCTYPES[doc.doctype]
	result = dict(
		doctype=doc.doctype,
		name=doc.name,
		company=doc.company,
		docstatus=doc.docstatus,
		posting_date=str(doc.posting_date) if doc.posting_date else None,
		party=doc.get(party_field) if party_field else None,
		lines=_lines(doc),
		attachments=_attachments(doc),
		can_submit=doc.docstatus == 0 and frappe.has_permission(doc.doctype, "submit", doc),
		can_delete=doc.docstatus == 0 and frappe.has_permission(doc.doctype, "delete", doc),
	)
	if doc.doctype in ("Sales Invoice", "Purchase Invoice") and doc.docstatus == 1:
		result["payments"] = _payments(doc)
	if doc.doctype == "Purchase Invoice":
		result["payment_method"] = doc.get("enk_payment_method") or ""
	if doc.doctype == "Purchase Invoice" and doc.docstatus == 1:
		activated, allocated = _activation(doc)
		result.update(activated_amount=str(activated), tax_pool_remaining=str(activated - allocated))
	if doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		result.update(
			currency=doc.currency,
			net_total=str(flt(doc.net_total, 2)),
			tax_total=str(flt(doc.total_taxes_and_charges, 2)),
			grand_total=str(flt(doc.grand_total, 2)),
			outstanding_amount=str(flt(doc.outstanding_amount, 2)),
			due_date=str(doc.due_date) if doc.due_date else None,
			is_return=bool(doc.is_return),
			return_against=doc.return_against,
			bill_no=doc.get("bill_no"),
			deferred=any(row.get("enable_deferred_revenue") for row in doc.items),
		)
	elif doc.doctype == "Payment Entry":
		result.update(
			currency=doc.paid_from_account_currency,
			grand_total=str(flt(doc.paid_amount, 2)),
			payment_type=doc.payment_type,
			reference_no=doc.reference_no,
		)
	else:
		result.update(
			currency=doc.get("total_amount_currency") or "NOK",
			grand_total=str(flt(doc.total_debit, 2)),
			description=doc.user_remark,
		)
	result["status"] = _status(doc.doctype, frappe._dict(result))
	if doc.docstatus == 0 and not doc.get("enk_external_id") and result["can_submit"]:
		result["edit"] = _edit_values(doc)
	return result


def _edit_values(doc):
	"""Verdiene skjemaet trenger for å redigere kladden. Bare salg og kjøp kan redigeres."""
	common = dict(
		currency=doc.get("currency") or "NOK",
		conversion_rate=flt(doc.get("conversion_rate")) if (doc.get("currency") or "NOK") != "NOK" else None,
		exchange_rate_source=doc.get("enk_exchange_rate_source"),
		exchange_rate_date=str(doc.enk_exchange_rate_date) if doc.get("enk_exchange_rate_date") else None,
	)
	if doc.doctype == "Sales Invoice":
		first = doc.items[0] if doc.items else frappe._dict()
		source = doc.get("enk_subscription_source_file")
		return common | dict(
			customer=doc.customer,
			customer_address=doc.customer_address,
			delivery_date=str(doc.enk_delivery_date) if doc.enk_delivery_date else None,
			due_date=str(doc.due_date) if doc.due_date else None,
			tax_treatment="" if doc.enk_tax_treatment in ("Not registered", "Domestic 25") else doc.enk_tax_treatment,
			tax_reason=doc.enk_tax_reason,
			items=[
				dict(description=row.description, quantity=str(flt(row.qty)), unit_price=str(flt(row.rate, 2)))
				for row in doc.items
			],
			defer_revenue=1 if first.get("enable_deferred_revenue") else 0,
			service_start_date=str(first.service_start_date) if first.get("service_start_date") else None,
			service_end_date=str(first.service_end_date) if first.get("service_end_date") else None,
			subscription_source_file=frappe.db.get_value("File", source, "file_url") if source else None,
		)
	if doc.doctype == "Purchase Invoice":
		settings = get_settings(doc.company)
		first = doc.items[0] if doc.items else frappe._dict()
		category = next(
			(
				key
				for key in ("software", "equipment", "expense", "fees", "asset")
				if settings.get(key + "_account") == first.get("expense_account")
			),
			"expense",
		)
		treatment = doc.enk_tax_treatment or ""
		return common | dict(
			supplier=doc.supplier,
			bill_no=doc.bill_no,
			bill_date=str(doc.bill_date) if doc.bill_date else None,
			description=first.get("description"),
			gross_amount=flt(doc.grand_total, 2),
			category="equipment" if category == "asset" else category,
			expected_life_months=doc.get("enk_expected_life_months") or None,
			vat_rate=treatment.split()[1] if treatment.startswith("Domestic") else "0",
			tax_reason=doc.get("enk_tax_reason"),
			business_fraction_percent=flt(doc.get("enk_business_fraction") or 1) * 100,
			deductible_fraction_percent=flt(doc.get("enk_deductible_fraction") or 1) * 100,
			tax_deductible_fraction_percent=flt(doc.get("enk_tax_deductible_fraction") or 1) * 100,
			tax_adjustment_reason=doc.get("enk_tax_adjustment_reason"),
			payment_method=doc.get("enk_payment_method") or "Unpaid",
		)
	return None


def _activation(doc):
	"""Aktivert beløp på kjøpet og hvor mye som alt ligger i en saldogruppe samme år."""
	import json
	from decimal import Decimal

	settings = get_settings(doc.company)
	activated = Decimal(
		str(
			frappe.db.sql(
				"""select coalesce(sum(debit-credit),0) from `tabGL Entry`
				where company=%s and voucher_type=%s and voucher_no=%s and account=%s and is_cancelled=0""",
				(doc.company, doc.doctype, doc.name, settings.asset_account),
			)[0][0]
		)
	).quantize(Decimal(".01"))
	allocated = Decimal(0)
	for pool in frappe.get_all(
		"ENK Tax Pool",
		filters={"company": doc.company, "income_year": getdate(doc.posting_date).year},
		pluck="acquisition_sources_json",
	):
		for source in json.loads(pool or "[]"):
			if source["doctype"] == doc.doctype and source["name"] == doc.name:
				allocated += Decimal(str(source["amount"]))
	return activated, allocated


@frappe.whitelist(methods=["POST"])
def add_to_tax_pool(name, saldo_group):
	"""Legg et aktivert kjøp i årets saldogruppe. Gruppen opprettes ved første kjøp."""
	import json

	doc = _load("Purchase Invoice", name)
	if doc.docstatus != 1:
		frappe.throw("Kjøpet må være bokført før det legges i en saldogruppe.")
	if saldo_group not in ("a", "d"):
		frappe.throw("Velg saldogruppe a eller d.")
	activated, allocated = _activation(doc)
	remaining = activated - allocated
	if activated <= 0:
		frappe.throw("Kjøpet er ikke aktivert som driftsmiddel og skal ikke i en saldogruppe.")
	if remaining <= 0:
		frappe.throw("Kjøpet ligger allerede i en saldogruppe.")
	year = getdate(doc.posting_date).year
	existing = frappe.db.get_value(
		"ENK Tax Pool", {"company": doc.company, "income_year": year, "saldo_group": saldo_group}, "name"
	)
	if existing:
		pool = frappe.get_doc("ENK Tax Pool", existing)
		pool.check_permission("write")
	else:
		frappe.has_permission("ENK Tax Pool", "create", throw=True)
		pool = frappe.get_doc(
			dict(doctype="ENK Tax Pool", company=doc.company, income_year=year, saldo_group=saldo_group, opening_balance=0)
		)
	sources = json.loads(pool.acquisition_sources_json or "[]")
	sources.append(dict(doctype=doc.doctype, name=doc.name, amount=str(remaining)))
	pool.acquisition_sources_json = json.dumps(sources)
	pool.acquisitions = flt(pool.acquisitions) + float(remaining)
	pool.save()
	return dict(
		name=pool.name,
		saldo_group=pool.saldo_group,
		acquisitions=str(pool.acquisitions),
		depreciation_deduction=str(pool.depreciation_deduction),
		closing_balance=str(pool.closing_balance),
	)


@frappe.whitelist()
def get_document(doctype, name):
	return _summary(_load(doctype, name))


@frappe.whitelist(methods=["POST"])
def submit_document(doctype, name):
	doc = _load(doctype, name)
	if doc.docstatus != 0:
		frappe.throw("Dokumentet er allerede bokført.")
	doc.check_permission("submit")
	doc.submit()
	if doc.doctype == "Purchase Invoice" and doc.get("enk_payment_method") in ("Private", "Bank"):
		_pay_on_submit(doc)
		doc.reload()
	return _summary(doc)


def _pay_on_submit(doc):
	"""Kortkjøp er betalt samtidig. Registrer og bokfør betalingen sammen med kjøpet.

	Alt skjer i samme transaksjon. Feiler betalingen, blir heller ikke kjøpet bokført.
	"""
	from enk_norge.api import pay_purchase_privately
	from enk_norge.banking import create_payment

	posting_date = str(doc.bill_date or doc.posting_date)
	if doc.enk_payment_method == "Private":
		payment = pay_purchase_privately(doc.name, posting_date=posting_date)
	else:
		payment = create_payment(
			doc.doctype,
			doc.name,
			amount=str(flt(doc.outstanding_amount, 2)),
			posting_date=posting_date,
			reference=f"Kortkjøp {doc.bill_no}"[:140],
		)
	entry = frappe.get_doc(payment["doctype"], payment["name"])
	if entry.docstatus == 0:
		entry.submit()


def _payments(doc):
	"""Bokførte betalinger og private oppgjør som gjelder fakturaen."""
	rows = frappe.db.sql(
		"""select pe.name, pe.posting_date, 'Payment Entry' doctype
		from `tabPayment Entry Reference` r join `tabPayment Entry` pe on pe.name = r.parent
		where r.reference_doctype = %(doctype)s and r.reference_name = %(name)s and pe.docstatus = 1
		union all
		select je.name, je.posting_date, 'Journal Entry' doctype
		from `tabJournal Entry Account` a join `tabJournal Entry` je on je.name = a.parent
		where a.reference_type = %(doctype)s and a.reference_name = %(name)s and je.docstatus = 1
		and je.enk_payment_key is not null
		order by posting_date""",
		dict(doctype=doc.doctype, name=doc.name),
		as_dict=True,
	)
	return [dict(doctype=row.doctype, name=row.name, posting_date=str(row.posting_date)) for row in rows]


@frappe.whitelist(methods=["POST"])
def delete_draft(doctype, name):
	doc = _load(doctype, name)
	if doc.docstatus != 0:
		frappe.throw("Bare kladder kan slettes. Bruk kreditnota eller korrigeringsbilag for bokførte dokumenter.")
	doc.check_permission("delete")
	company = doc.company
	frappe.delete_doc(doctype, name)
	return dict(company=company)


def _next_period(start, end):
	"""Neste periode har samme lengde. Hele måneder forblir hele måneder."""
	start, end = getdate(start), getdate(end)
	following = add_days(end, 1)
	for months in range(1, 13):
		if add_days(add_months(start, months), -1) == end:
			return following, add_days(add_months(following, months), -1)
	return following, add_days(following, (end - start).days)


@frappe.whitelist(methods=["POST"])
def create_next_period(name):
	"""Lag kladd for neste abonnementsperiode fra en bokført, periodisert faktura."""
	from enk_norge.api import create_sale

	doc = _load("Sales Invoice", name)
	if doc.docstatus != 1 or doc.is_return:
		frappe.throw("Bare bokførte fakturaer kan videreføres.")
	periods = {(str(row.service_start_date), str(row.service_end_date)) for row in doc.items}
	if (
		not all(row.enable_deferred_revenue for row in doc.items)
		or len(periods) != 1
		or not doc.enk_subscription_source_file
	):
		frappe.throw("Bare abonnementsfakturaer der alle linjene har samme periode og avtale kan videreføres.")
	if (doc.currency or "NOK") != "NOK":
		frappe.throw("Abonnement i utenlandsk valuta må faktureres med ny faktura, fordi kursen må dokumenteres.")
	external_id = f"neste-periode:{doc.name}"
	existing = frappe.db.get_value(
		"Sales Invoice", {"company": doc.company, "enk_external_id": external_id, "docstatus": ["!=", 2]}, "name"
	)
	if existing:
		return dict(doctype="Sales Invoice", name=existing, reused=True)
	row = doc.items[0]
	start, end = _next_period(row.service_start_date, row.service_end_date)
	posting = min(getdate(today()), start)
	source = frappe.get_doc("File", doc.enk_subscription_source_file)
	source.check_permission("read")
	# Avtalen kan bare knyttes til ett bilag, så neste periode får en egen kopi.
	copy = frappe.get_doc(
		dict(doctype="File", file_name=source.file_name, content=source.get_content(), is_private=1)
	).insert()
	treatment = doc.enk_tax_treatment if doc.enk_tax_treatment not in ("Not registered", "Domestic 25") else None
	return create_sale(
		dict(
			company=doc.company,
			customer=doc.customer,
			customer_address=doc.customer_address,
			posting_date=str(posting),
			delivery_date=str(start),
			due_date=str(add_days(posting, (getdate(doc.due_date) - getdate(doc.posting_date)).days)),
			description=doc.enk_delivery_description,
			items=[
				dict(description=line.description, quantity=str(flt(line.qty)), unit_price=str(flt(line.rate, 2)))
				for line in doc.items
			],
			tax_treatment=treatment,
			tax_reason=doc.enk_tax_reason if treatment == "Exempt" else None,
			service_start_date=str(start),
			service_end_date=str(end),
			subscription_source_file=copy.name,
			external_id=external_id,
		)
	)
