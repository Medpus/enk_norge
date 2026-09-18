"""Foretaksoppsett med en liten, egen kontoplan for tjenesteytende ENK."""

import re

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import disable_future_access
from frappe.utils import cint, getdate

# Egen inndeling og egne kontonavn. Dette er ikke en gjengivelse av NS 4102.
ACCOUNTS = [
	("A100", "Bank", "Asset", "Bank", "bank", "19"),
	("A110", "Ubetalte kundefakturaer", "Asset", "Receivable", "receivable", "15"),
	("A120", "Oppgjør underveis", "Asset", "", "clearing", "15"),
	("A130", "Utstyr med varig verdi", "Asset", "Fixed Asset", "asset", "12"),
	("A140", "MVA til fradrag", "Asset", "Tax", "input_vat", "27"),
	("L100", "Ubetalte leverandørfakturaer", "Liability", "Payable", "payable", "24"),
	("L110", "MVA på salg", "Liability", "Tax", "output_vat", "27"),
	("L120", "MVA på utenlandske tjenester", "Liability", "Tax", "reverse_vat", "27"),
	("L130", "Utsatt inntekt fra abonnement", "Liability", "", "deferred_revenue", "29"),
	("E100", "Innskudd og private utlegg", "Equity", "", "owner", "20"),
	("E110", "Uttak til innehaver", "Equity", "", "withdrawal", "20"),
	("I100", "Salg av tjenester og produkter", "Income", "Income Account", "income", "30"),
	("I120", "Fjernleverbare tjenester til utlandet", "Income", "Income Account", "export_income", "31"),
	("I130", "Omsetning unntatt fra MVA", "Income", "Income Account", "exempt_income", "32"),
	("I140", "Valutagevinst", "Income", "Income Account", "fx_gain", "80"),
	("I150", "Gevinst ved salg og uttak av utstyr", "Income", "Income Account", "asset_gain", "38"),
	("C170", "Tap ved salg og uttak av utstyr", "Expense", "", "asset_loss", "78"),
	("C100", "Programvare og nettjenester", "Expense", "", "software", "65"),
	("C110", "Utstyr kostnadsført ved kjøp", "Expense", "", "equipment", "65"),
	("C120", "Andre driftskostnader", "Expense", "", "expense", "77"),
	("C130", "Gebyrer for bank og betaling", "Expense", "", "fees", "77"),
	("C140", "Avskrivning av utstyr", "Expense", "Depreciation", "depreciation", "60"),
	("C150", "Avrundingsdifferanser", "Expense", "Round Off", "rounding", "77"),
	("C160", "Valutatap", "Expense", "", "fx_loss", "81"),
]


# Offentlig SAF-T klassifisering mot næringsspesifikasjonen 2025-2026.
GROUPINGS = {
	"A100": ("balanseverdiForOmloepsmiddel", "1920"),
	"A110": ("balanseverdiForOmloepsmiddel", "1500"),
	"A120": ("balanseverdiForOmloepsmiddel", "1570"),
	"A130": ("balanseverdiForAnleggsmiddel", "1280"),
	"A140": ("balanseverdiForOmloepsmiddel", "1570"),
	"L100": ("kortsiktigGjeld", "2400"),
	"L110": ("kortsiktigGjeld", "2740"),
	"L120": ("kortsiktigGjeld", "2740"),
	"L130": ("kortsiktigGjeld", "2970"),
	"E100": ("egenkapital", "2050"),
	"E110": ("egenkapital", "2050"),
	"I100": ("salgsinntekt", "3000"),
	"I120": ("salgsinntekt", "3100"),
	"I130": ("salgsinntekt", "3200"),
	"I140": ("finansinntekt", "8060"),
	"I150": ("annenDriftsinntekt", "3880"),
	"C170": ("annenDriftskostnad", "7880"),
	"C100": ("annenDriftskostnad", "6500"),
	"C110": ("annenDriftskostnad", "6500"),
	"C120": ("annenDriftskostnad", "7700"),
	"C130": ("annenDriftskostnad", "7700"),
	"C140": ("annenDriftskostnad", "6000"),
	"C150": ("annenDriftskostnad", "7700"),
	"C160": ("finanskostnad", "8160"),
}


def ensure_currency_accounts():
	"""Utvid eksisterende ENK-kontoplan uten å endre historiske koblinger."""
	for name in frappe.get_all("ENK Settings", pluck="name"):
		settings = frappe.get_doc("ENK Settings", name)
		changed = False
		for code, label, root, account_type, purpose, standard in ACCOUNTS:
			if purpose not in ("fx_gain", "fx_loss", "asset_gain", "asset_loss", "deferred_revenue") or settings.get(purpose + "_account"):
				continue
			account = frappe.db.get_value(
				"Account", {"company": settings.company, "account_number": code}, "name"
			)
			if not account:
				parent = frappe.db.get_value(
					"Account",
					{
						"company": settings.company,
						"root_type": root,
						"is_group": 1,
						"parent_account": ["is", "not set"],
					},
					"name",
				)
				account = (
					frappe.get_doc(
						dict(
							doctype="Account",
							company=settings.company,
							account_name=label,
							account_number=code,
							parent_account=parent,
							root_type=root,
							account_type=account_type,
							is_group=0,
							account_currency="NOK",
						)
					)
					.insert(ignore_permissions=True)
					.name
				)
			settings.set(purpose + "_account", account)
			if not any(row.account == account for row in settings.accounts):
				settings.append(
					"accounts",
					dict(
						account=account,
						standard_account_id=standard,
						grouping_category=GROUPINGS[code][0],
						grouping_code=GROUPINGS[code][1],
						tax_category=root,
					),
				)
			changed = True
		if changed:
			settings.save(ignore_permissions=True)


def get_settings(company, write=False):
	frappe.get_doc("Company", company).check_permission("read")
	settings = frappe.get_doc("ENK Settings", company)
	settings.check_permission("write" if write else "read")
	return settings


ENK_HOME_PAGE = "enk-norge"


def finish_first_run():
	"""Bruk Frappes egen avslutning før ENKs første landingsside settes."""
	# complete_first_run har allerede slått på app-flaggene i samme request.
	# Tøm request-cachen slik at disable_future_access leser dem på nytt.
	frappe.clear_cache()
	disable_future_access()
	frappe.db.set_default("desktop:home_page", ENK_HOME_PAGE)
	frappe.clear_cache()


def repair_completed_setup_home_page():
	"""Reparer bare ENK-siter som er ferdige, men fortsatt peker på veiviseren."""
	if (
		not frappe.is_setup_complete()
		or not frappe.db.count("Company")
		or not frappe.db.count("ENK Settings")
		or frappe.db.get_default("desktop:home_page") != "setup-wizard"
	):
		return False
	frappe.db.set_default("desktop:home_page", ENK_HOME_PAGE)
	frappe.clear_cache()
	return True


@frappe.whitelist()
def list_companies():
	frappe.only_for(["Accounts User", "Accounts Manager", "System Manager"])
	return [
		dict(company=c.name, configured=bool(frappe.db.exists("ENK Settings", c.name)))
		for c in frappe.get_list("Company", fields=["name"], filters={"country": "Norway"})
	]


@frappe.whitelist(methods=["POST"])
def create_company(data):
	frappe.only_for(["Accounts Manager", "System Manager"])
	data = frappe.parse_json(data) if isinstance(data, str) else data
	if not isinstance(data, dict):
		frappe.throw("Ugyldig foretaksoppsett.")
	from enk_norge.validation import validate_setup_values

	validate_setup_values(data)
	from enk_norge.norway_rules import validate_norwegian_bank_account, validate_norwegian_organization_number

	data["organization_number"] = validate_norwegian_organization_number(
		data["organization_number"]
	).normalized_value
	data["bank_account"] = validate_norwegian_bank_account(data["bank_account"]).normalized_value
	frappe.db.sql("select name from `tabDocType` where name=%s for update", "ENK Settings")
	name = data["company_name"].strip()
	if frappe.db.exists("Company", name):
		frappe.throw("Foretaket finnes allerede. Bruk oppsett for eksisterende foretak.")
	if frappe.db.exists("Company", {"tax_id": data["organization_number"]}):
		frappe.throw("Organisasjonsnummeret er allerede brukt av et foretak.")
	if not frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger"):
		if frappe.db.count("GL Entry"):
			frappe.throw("Eksisterende regnskap må vurderes før uforanderlig hovedbok aktiveres.")
		frappe.db.set_single_value("Accounts Settings", "enable_immutable_ledger", 1)
	abbr = data["abbr"].strip().upper()
	if not re.fullmatch(r"[A-Z0-9]{2,5}", abbr):
		frappe.throw("Forkortelsen må ha 2-5 bokstaver A-Z eller tall.")
	frappe.flags.ignore_chart_of_accounts = True
	try:
		company = frappe.get_doc(
			dict(
				doctype="Company",
				company_name=name,
				abbr=abbr,
				country="Norway",
				default_currency="NOK",
				tax_id=data["organization_number"],
				phone_no=data.get("phone"),
				enable_perpetual_inventory=0,
			)
		).insert()
	finally:
		frappe.flags.ignore_chart_of_accounts = False
	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts

	roots = {
		"Asset": "Eiendeler",
		"Liability": "Gjeld",
		"Equity": "Eierkapital",
		"Income": "Inntekter",
		"Expense": "Kostnader",
	}
	chart = {label: {"root_type": root, "is_group": 1} for root, label in roots.items()}
	for code, label, root, account_type, _purpose, _standard in ACCOUNTS:
		chart[roots[root]][label] = dict(account_number=code, account_type=account_type)
	create_charts(company.name, custom_chart=chart)
	settings = frappe.new_doc("ENK Settings")
	settings.company = company.name
	for key in (
		"organization_number",
		"bank_account",
		"start_date",
		"address_line",
		"postal_code",
		"city",
		"phone",
		"bank_name",
		"vat_registered",
		"vat_registration_date",
		"history_confirmed",
	):
		settings.set(key, data.get(key))
	settings.invoice_prefix = "ENK-" + abbr
	for code, _label, root, _account_type, purpose, standard in ACCOUNTS:
		account = frappe.db.get_value("Account", {"company": company.name, "account_number": code}, "name")
		settings.set("bank_ledger_account" if purpose == "bank" else purpose + "_account", account)
		settings.append(
			"accounts",
			dict(
				account=account,
				standard_account_id=standard,
				tax_category=root,
				grouping_category=GROUPINGS[code][0],
				grouping_code=GROUPINGS[code][1],
			),
		)
	if not frappe.db.exists("Bank", data["bank_name"]):
		frappe.get_doc(dict(doctype="Bank", bank_name=data["bank_name"])).insert()
	bank_record = frappe.get_doc(
		dict(
			doctype="Bank Account",
			account_name=company.name,
			bank=data["bank_name"],
			bank_account_no=data["bank_account"],
			account=settings.bank_ledger_account,
			is_company_account=1,
			is_default=1,
			company=company.name,
		)
	).insert()
	settings.bank_account_record = bank_record.name
	settings.insert()
	company.reload()
	company.default_bank_account = settings.bank_ledger_account
	company.default_receivable_account = settings.receivable_account
	company.default_payable_account = settings.payable_account
	company.default_income_account = settings.income_account
	company.default_expense_account = settings.expense_account
	company.round_off_account = settings.rounding_account
	company.round_off_cost_center = company.cost_center
	company.save()
	year = getdate(settings.start_date).year
	if not frappe.db.exists("Fiscal Year", str(year)):
		frappe.get_doc(
			dict(
				doctype="Fiscal Year",
				year=str(year),
				year_start_date=f"{year}-01-01",
				year_end_date=f"{year}-12-31",
			)
		).insert()
	frappe.get_doc(
		dict(
			doctype="Address",
			address_title=company.name,
			address_type="Billing",
			address_line1=settings.address_line,
			city=settings.city,
			pincode=settings.postal_code,
			country="Norway",
			is_your_company_address=1,
			links=[dict(link_doctype="Company", link_name=company.name)],
		)
	).insert()
	return dict(company=company.name, settings=settings.name)


@frappe.whitelist(methods=["POST"])
def complete_first_run(data):
	"""Fullfør kun et tomt site. Samme transaksjon lager bruker, foretak og standarder."""
	frappe.only_for("System Manager")
	if frappe.is_setup_complete() or frappe.db.count("Company"):
		frappe.throw("Førstegangsoppsettet er allerede startet eller fullført. Åpne ENK Norge.")
	data = frappe._dict(frappe.parse_json(data) if isinstance(data, str) else data)
	from enk_norge.validation import validate_setup_values

	validate_setup_values(data)
	data.full_name = data.get("system_user_full_name")
	data.email = data.get("system_user_email")
	data.password = data.get("system_user_password")
	if not data.get("full_name") or not data.get("email") or not data.get("password"):
		frappe.throw("Oppgi navn, e-post og et nytt passord for din personlige bruker.")
	if frappe.db.exists("User", data.email):
		frappe.throw("E-postadressen har allerede en bruker. Brukeroppsettet må avklares før videre oppsett.")
	from erpnext.setup.setup_wizard.operations import install_fixtures
	from frappe.desk.page.setup_wizard.setup_wizard import (
		enable_setup_wizard_complete,
		update_system_settings,
	)

	args = frappe._dict(
		country="Norway",
		language="nb",
		currency="NOK",
		timezone="Europe/Oslo",
		company_name=data.company_name,
	)
	update_system_settings(args)
	install_fixtures.add_uom_data()
	install_fixtures.update_selling_defaults()
	install_fixtures.update_buying_defaults()
	result = create_company(data)
	install_fixtures.set_global_defaults(args)
	for kind, field in (("Selling", "selling"), ("Buying", "buying")):
		if not frappe.db.exists("Price List", "ENK " + kind):
			frappe.get_doc(
				dict(
					doctype="Price List",
					price_list_name="ENK " + kind,
					enabled=1,
					currency="NOK",
					**{field: 1},
				)
			).insert()
	frappe.db.set_single_value("Selling Settings", "selling_price_list", "ENK Selling")
	frappe.db.set_single_value("Buying Settings", "buying_price_list", "ENK Buying")
	user = frappe.get_doc(
		dict(
			doctype="User",
			email=data.email,
			first_name=data.full_name,
			user_type="System User",
			send_welcome_email=0,
			new_password=data.password,
			language="nb",
			roles=[{"role": r} for r in ["System Manager", "Accounts Manager", "Accounts User"]],
		)
	)
	user.insert()
	for app in ("frappe", "erpnext", "enk_norge"):
		enable_setup_wizard_complete(app)
	finish_first_run()
	return result
