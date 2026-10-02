"""ENK-sidens enkle flyter: kunder, leverandører, bilagsvisning, timer og MVA-status."""

import unittest
from uuid import uuid4

import frappe

from enk_norge import documents, hours, parties
from enk_norge.api import create_purchase, create_sale
from enk_norge.setup import OWNER_ROLES, company_profile, create_company, update_vat_registration


class SimpleFlowsTest(unittest.TestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("enk_simple")
		self.addCleanup(frappe.db.rollback, save_point="enk_simple")
		self.addCleanup(frappe.set_user, self.previous_user)
		self.company = create_company(
			dict(
				company_name="Fiktivt ENK " + uuid4().hex[:8],
				abbr=uuid4().hex[:5].upper(),
				organization_number="974761076",
				bank_account="86011117947",
				start_date="2026-01-01",
				address_line="Testveien 1",
				postal_code="0001",
				city="Oslo",
				phone="00000000",
				bank_name="Fiktiv testbank",
				vat_registered=0,
				history_confirmed=1,
			)
		)["company"]
		# Kjør som eieren veiviseren lager, ikke som Administrator, så rollefeil blir synlige.
		owner = frappe.get_doc(
			dict(
				doctype="User",
				email=f"eier-{uuid4().hex[:8]}@example.invalid",
				first_name="Fiktiv eier",
				user_type="System User",
				send_welcome_email=0,
				roles=[{"role": role} for role in OWNER_ROLES],
			)
		).insert()
		frappe.set_user(owner.name)

	def customer(self, **overrides):
		data = dict(
			customer_name="Fiktiv kunde " + uuid4().hex[:8],
			customer_type="Company",
			address_line="Kundeveien 1",
			postal_code="0150",
			city="Oslo",
		)
		data.update(overrides)
		return parties.create_customer(data)

	def attach(self, doctype, name):
		frappe.get_doc(
			dict(
				doctype="File",
				file_name="kvittering.txt",
				content="Fiktiv kvittering",
				is_private=1,
				attached_to_doctype=doctype,
				attached_to_name=name,
			)
		).insert()

	def test_new_customer_can_be_invoiced_and_posted_from_enk_page(self):
		customer = self.customer()
		self.assertEqual(parties.billing_address(customer["customer"]).name, customer["customer_address"])
		draft = create_sale(
			dict(
				company=self.company,
				customer=customer["customer"],
				customer_address=customer["customer_address"],
				posting_date="2026-09-17",
				delivery_date="2026-09-17",
				due_date="2026-10-01",
				description="Konsulentbistand",
				quantity="10",
				unit_price="1200",
			)
		)
		summary = documents.get_document(draft["doctype"], draft["name"])
		self.assertEqual(summary["status"], "draft")
		self.assertTrue(summary["can_submit"])
		self.assertEqual(summary["grand_total"], "12000.0")
		posted = documents.submit_document(draft["doctype"], draft["name"])
		self.assertEqual(posted["status"], "unpaid")
		listed = documents.list_documents(self.company, "sales")
		self.assertEqual([row.name for row in listed], [draft["name"]])
		self.assertEqual(documents.list_documents(self.company, "sales", search="ingen-treff"), [])

	def test_foreign_supplier_service_and_receipt_requirement(self):
		supplier = parties.create_supplier(dict(supplier_name="Fiktiv AI " + uuid4().hex[:6], country="United States"))
		self.assertEqual(supplier["country"], "United States")
		draft = create_purchase(
			dict(
				company=self.company,
				supplier=supplier["supplier"],
				posting_date="2026-09-17",
				bill_date="2026-09-17",
				bill_no="INV-1",
				description="AI-abonnement",
				category="software",
				gross_amount="240",
				vat_rate="0",
				foreign_service=1,
			)
		)
		with self.assertRaises(frappe.ValidationError):
			documents.submit_document(draft["doctype"], draft["name"])
		self.attach(draft["doctype"], draft["name"])
		posted = documents.submit_document(draft["doctype"], draft["name"])
		self.assertEqual(posted["status"], "unpaid")
		self.assertEqual(len(posted["attachments"]), 1)

	def test_draft_can_be_deleted_but_posted_document_is_kept(self):
		customer = self.customer()
		args = dict(
			company=self.company,
			customer=customer["customer"],
			customer_address=customer["customer_address"],
			posting_date="2026-09-17",
			delivery_date="2026-09-17",
			due_date="2026-10-01",
			description="Feilført",
			unit_price="100",
		)
		draft = create_sale(args)
		documents.delete_draft(draft["doctype"], draft["name"])
		self.assertFalse(frappe.db.exists(draft["doctype"], draft["name"]))
		posted = create_sale(args)
		documents.submit_document(posted["doctype"], posted["name"])
		with self.assertRaises(frappe.ValidationError):
			documents.delete_draft(posted["doctype"], posted["name"])

	def test_logged_hours_become_one_invoice_draft(self):
		customer = self.customer()
		base = dict(company=self.company, customer=customer["customer"], rate="1200")
		hours.log_hours(base | dict(date="2026-09-01", hours="3", description="Analyse"))
		summary = hours.log_hours(base | dict(date="2026-09-01", hours="2", description="Møte"))
		self.assertEqual(summary["hours"], 5)
		self.assertEqual(len(hours.open_hours(self.company)), 1)
		draft = hours.invoice_hours(
			dict(
				company=self.company,
				timesheet=summary["timesheet"],
				posting_date="2026-09-30",
				due_date="2026-10-14",
				delivery_description="Konsulenttimer september",
			)
		)
		invoice = documents.get_document(draft["doctype"], draft["name"])
		self.assertEqual(invoice["grand_total"], "6000.0")
		documents.submit_document(draft["doctype"], draft["name"])
		self.assertEqual(hours.open_hours(self.company), [])

	def test_removing_last_hour_line_removes_empty_timesheet(self):
		customer = self.customer()
		summary = hours.log_hours(
			dict(company=self.company, customer=customer["customer"], rate="900", date="2026-09-02", hours="1", description="Feil")
		)
		self.assertIsNone(hours.remove_hours(summary["timesheet"], summary["logs"][0]["row"]))
		self.assertFalse(frappe.db.exists("Timesheet", summary["timesheet"]))

	def test_vat_registration_can_be_set_before_postings(self):
		profile = update_vat_registration(self.company, 1, "2026-10-01")
		self.assertTrue(profile["vat_registered"])
		self.assertEqual(profile["vat_registration_date"], "2026-10-01")
		self.assertFalse(company_profile(self.company)["has_postings"])

	def test_equipment_is_activated_by_rule_engine_when_required(self):
		from enk_norge.setup import get_settings

		settings = get_settings(self.company)
		supplier = parties.create_supplier(dict(supplier_name="Fiktiv elektronikk " + uuid4().hex[:6]))

		def mac(amount, bill_no):
			draft = create_purchase(
				dict(
					company=self.company,
					supplier=supplier["supplier"],
					posting_date="2026-09-17",
					bill_date="2026-09-17",
					bill_no=bill_no,
					description="Mac til konsulentarbeid",
					category="equipment",
					gross_amount=amount,
					expected_life_months=48,
				)
			)
			return frappe.get_doc(draft["doctype"], draft["name"]).items[0].expense_account

		self.assertEqual(mac("15000", "MAC-1"), settings.equipment_account)
		self.assertEqual(mac("35000", "MAC-2"), settings.asset_account)

	def test_owner_can_report_reverse_charge_for_foreign_services(self):
		from enk_norge import vat

		supplier = parties.create_supplier(dict(supplier_name="Fiktiv AI " + uuid4().hex[:6], country="United States"))
		draft = create_purchase(
			dict(
				company=self.company,
				supplier=supplier["supplier"],
				posting_date="2026-09-17",
				bill_date="2026-09-17",
				bill_no="API-1",
				description="AI-tjeneste",
				category="software",
				gross_amount="2400",
				vat_rate="0",
				foreign_service=1,
			)
		)
		self.attach(draft["doctype"], draft["name"])
		documents.submit_document(draft["doctype"], draft["name"])
		args = dict(company=self.company, period_end="2026-09-30", report_type="Reverse charge unregistered")
		first = frappe.get_doc("ENK VAT Return", vat.build_vat_return(**args)["name"])
		self.assertEqual(first.status, "Draft")
		reverse = vat.create_reverse_charge_draft(**args)
		self.assertEqual(reverse["doctype"], "Journal Entry")
		documents.submit_document(reverse["doctype"], reverse["name"])
		ready = frappe.get_doc("ENK VAT Return", vat.build_vat_return(**args)["name"])
		self.assertEqual(ready.status, "Ready for review")
		self.assertEqual(str(ready.reverse_charge_output_vat), "600.0")
		self.attach("ENK VAT Return", ready.name)
		receipt = frappe.get_all("File", filters={"attached_to_doctype": "ENK VAT Return", "attached_to_name": ready.name}, pluck="name")[0]
		self.assertEqual(vat.mark_vat_return_manually_filed(private_receipt_file=receipt, **args)["status"], "Manually filed")

	def test_subscription_invoice_continues_to_next_period_once(self):
		customer = self.customer()
		agreement = frappe.get_doc(
			dict(doctype="File", file_name="avtale.txt", content="Fiktiv abonnementsavtale", is_private=1)
		).insert()
		first = create_sale(
			dict(
				company=self.company,
				customer=customer["customer"],
				customer_address=customer["customer_address"],
				posting_date="2026-09-01",
				delivery_date="2026-09-01",
				due_date="2026-09-15",
				description="SaaS-abonnement",
				unit_price="499",
				service_start_date="2026-09-01",
				service_end_date="2026-09-30",
				subscription_source_file=agreement.name,
			)
		)
		documents.submit_document(first["doctype"], first["name"])
		self.assertEqual(documents._next_period("2026-01-01", "2026-12-31")[1].isoformat(), "2027-12-31")
		draft = documents.create_next_period(first["name"])
		item = frappe.get_doc("Sales Invoice", draft["name"]).items[0]
		self.assertEqual((str(item.service_start_date), str(item.service_end_date)), ("2026-10-01", "2026-10-31"))
		self.assertEqual(documents.create_next_period(first["name"])["name"], draft["name"])
		documents.submit_document(draft["doctype"], draft["name"])

	def test_activated_equipment_goes_into_tax_pool_once(self):
		supplier = parties.create_supplier(dict(supplier_name="Fiktiv elektronikk " + uuid4().hex[:6]))
		draft = create_purchase(
			dict(
				company=self.company,
				supplier=supplier["supplier"],
				posting_date="2026-09-17",
				bill_date="2026-09-17",
				bill_no="MAC-POOL",
				description="Mac til konsulentarbeid",
				category="equipment",
				gross_amount="36000",
				expected_life_months=48,
			)
		)
		self.attach(draft["doctype"], draft["name"])
		posted = documents.submit_document(draft["doctype"], draft["name"])
		self.assertEqual(posted["tax_pool_remaining"], "36000.00")
		pool = documents.add_to_tax_pool(draft["name"], "a")
		self.assertEqual(pool["saldo_group"], "a")
		self.assertEqual(float(pool["depreciation_deduction"]), 10800.0)
		self.assertEqual(documents.get_document(draft["doctype"], draft["name"])["tax_pool_remaining"], "0.00")
		with self.assertRaises(frappe.ValidationError):
			documents.add_to_tax_pool(draft["name"], "a")

	def test_invoice_with_several_lines_and_plain_numbers(self):
		from enk_norge.printing import enk_format_number

		# Et foretak alene på sitet får fakturanummer 1, 2, 3. Testsitet har flere, så prefiksen fjernes her.
		frappe.db.set_value("ENK Settings", self.company, "invoice_prefix", "")
		customer = self.customer()
		draft = create_sale(
			dict(
				company=self.company,
				customer=customer["customer"],
				customer_address=customer["customer_address"],
				posting_date="2026-09-17",
				delivery_date="2026-09-17",
				due_date="2026-10-01",
				items=[
					dict(description="Palli, modul for pakkseddel", quantity="1", unit_price="4000"),
					dict(description="Palli, modul for strekkode", quantity="2", unit_price="1500"),
					dict(description="Palli, modul for fraktbrev", quantity="1", unit_price="3000"),
				],
			)
		)
		self.assertTrue(draft["name"].isdigit(), draft["name"])
		invoice = frappe.get_doc(draft["doctype"], draft["name"])
		self.assertEqual([row.description for row in invoice.items][1], "Palli, modul for strekkode")
		self.assertEqual(invoice.grand_total, 10000)
		documents.submit_document(draft["doctype"], draft["name"])
		html = frappe.get_print("Sales Invoice", draft["name"], print_format="ENK Faktura")
		self.assertIn("Palli, modul for fraktbrev", html)
		self.assertIn("Betalingsinformasjon", html)
		self.assertNotIn("Merverdiavgiftsregisteret", html)
		self.assertEqual(enk_format_number("86011117947", "account"), "8601.11.17947")
		self.assertEqual(enk_format_number("974761076", "org"), "974 761 076")
		with self.assertRaises(frappe.ValidationError):
			create_sale(dict(company=self.company, customer=customer["customer"], customer_address=customer["customer_address"], delivery_date="2026-09-17", due_date="2026-10-01", items=[dict(description="", quantity="1", unit_price="1")]))

	def test_drafts_can_be_edited_and_keep_their_number(self):
		customer = self.customer()
		args = dict(
			company=self.company,
			customer=customer["customer"],
			customer_address=customer["customer_address"],
			posting_date="2026-09-17",
			delivery_date="2026-09-17",
			due_date="2026-10-01",
			items=[dict(description="Første utkast", quantity="1", unit_price="1000")],
		)
		draft = create_sale(args)
		edit = documents.get_document(draft["doctype"], draft["name"])["edit"]
		self.assertEqual(edit["items"][0]["description"], "Første utkast")
		edited = create_sale(args | dict(draft=draft["name"], items=[
			dict(description="Palli grunnmodul", quantity="1", unit_price="6000"),
			dict(description="Palli strekkode", quantity="2", unit_price="2000"),
		]))
		self.assertEqual(edited["name"], draft["name"])
		invoice = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual((len(invoice.items), invoice.grand_total), (2, 10000))
		documents.submit_document(draft["doctype"], draft["name"])
		with self.assertRaises(frappe.ValidationError):
			create_sale(args | dict(draft=draft["name"]))

		supplier = parties.create_supplier(dict(supplier_name="Fiktiv leverandør " + uuid4().hex[:6]))
		purchase_args = dict(
			company=self.company,
			supplier=supplier["supplier"],
			posting_date="2026-09-17",
			bill_date="2026-09-17",
			bill_no="K-1",
			description="Kontorrekvisita",
			category="expense",
			gross_amount="300",
		)
		purchase = create_purchase(purchase_args)
		values = documents.get_document(purchase["doctype"], purchase["name"])["edit"]
		self.assertEqual((values["gross_amount"], values["category"]), (300.0, "expense"))
		create_purchase(purchase_args | dict(draft=purchase["name"], gross_amount="450"))
		self.assertEqual(frappe.get_doc("Purchase Invoice", purchase["name"]).grand_total, 450)
