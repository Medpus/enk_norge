"""Fakturautkast fra ERPNexts egne time- og abonnementsdokumenter."""

import unittest
from uuid import uuid4

import frappe
from frappe.utils import add_days, getdate, today

from enk_norge.billing import BillingError, subscription_event_id, timesheet_event_id


class BillingCoreTest(unittest.TestCase):
	def test_stable_source_event_ids(self):
		self.assertEqual(timesheet_event_id("TS-2026-00001"), "timesheet:TS-2026-00001")
		self.assertEqual(
			subscription_event_id("ACC-SUB-0001", "2026-10-01", "2026-10-31"),
			"subscription:ACC-SUB-0001:2026-10-01:2026-10-31",
		)
		with self.assertRaises(BillingError):
			subscription_event_id("", "2026-10-01", "2026-10-31")
		from enk_norge.billing import _money

		with self.assertRaisesRegex(frappe.ValidationError, "høyst to desimaler"):
			_money("1.001", "Pris")


@unittest.skipUnless(frappe.db.exists("DocType", "ENK Settings"), "Krever migrert ENK-oppsett")
class BillingWorkflowTest(unittest.TestCase):
	def setUp(self):
		from enk_norge.setup import create_company, get_settings

		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("enk_billing_test")
		self.addCleanup(frappe.db.rollback, save_point="enk_billing_test")
		self.addCleanup(frappe.set_user, self.previous_user)
		self.company = create_company(
			{
				"company_name": "Fiktivt faktura-ENK " + uuid4().hex[:8],
				"abbr": uuid4().hex[:5].upper(),
				"organization_number": self._organization_number(),
				"bank_account": "86011117947",
				"start_date": "2026-01-01",
				"address_line": "Testveien 1",
				"postal_code": "0001",
				"city": "Oslo",
				"phone": "00000000",
				"bank_name": "Fiktiv testbank",
				"vat_registered": 0,
				"history_confirmed": 1,
			}
		)["company"]
		self.settings = get_settings(self.company)
		self.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "Fiktiv fakturakunde " + uuid4().hex[:8],
				"customer_type": "Company",
				"customer_group": "Commercial",
				"territory": "Norway",
			}
		).insert()
		self.address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": self.customer.name,
				"address_type": "Billing",
				"address_line1": "Kundeveien 1",
				"city": "Oslo",
				"pincode": "0001",
				"country": "Norway",
				"links": [{"link_doctype": "Customer", "link_name": self.customer.name}],
			}
		).insert()
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not item_group:
			root = frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": "ENK testvarer", "is_group": 1}
			).insert(ignore_permissions=True)
			item_group = frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "ENK testtjenester",
					"parent_item_group": root.name,
					"is_group": 0,
				}
			).insert(ignore_permissions=True).name
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ENK-BILLING-" + uuid4().hex[:12],
				"item_name": "Fiktiv konsulenttime",
				"item_group": item_group,
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert()

	def _organization_number(self):
		for offset in range(100):
			base = f"{int(uuid4().hex[:8], 16) % 100_000_000 + offset:08d}"
			control = 11 - sum(
				int(digit) * weight for digit, weight in zip(base, (3, 2, 7, 6, 5, 4, 3, 2), strict=True)
			) % 11
			if control == 11:
				control = 0
			if control != 10:
				return base + str(control)
		raise AssertionError("Kunne ikke lage gyldig fiktivt organisasjonsnummer.")

	def _timesheet(self):
		activity = frappe.get_doc(
			{
				"doctype": "Activity Type",
				"activity_type": "ENK fakturatime " + uuid4().hex[:10],
				"billing_rate": 50,
				"costing_rate": 0,
			}
		).insert()
		return frappe.get_doc(
			{
				"doctype": "Timesheet",
				"company": self.company,
				"currency": "NOK",
				"time_logs": [
					{
						"from_time": "2026-09-17 09:00:00",
						"to_time": "2026-09-17 11:00:00",
						"hours": 2,
						"is_billable": 1,
						"activity_type": activity.name,
						"description": "Fiktiv konsulentbistand",
					}
				],
			}
		).insert().submit()

	def _timesheet_payload(self, timesheet, **overrides):
		data = {
			"company": self.company,
			"timesheet": timesheet.name,
			"customer": self.customer.name,
			"customer_address": self.address.name,
			"item_code": self.item.name,
			"posting_date": "2026-09-17",
			"delivery_date": "2026-09-17",
			"delivery_description": "To timer fiktiv konsulentbistand",
			"due_date": "2026-10-01",
			"unit_price": "50.00",
		}
		data.update(overrides)
		return data

	def _native_timesheet_draft(self, timesheet):
		from erpnext.projects.doctype.timesheet.timesheet import make_sales_invoice

		draft = make_sales_invoice(timesheet.name, self.item.name, self.customer.name, currency="NOK")
		draft.customer_address = self.address.name
		draft.posting_date = "2026-09-17"
		draft.due_date = "2026-10-01"
		draft.currency = "NOK"
		draft.conversion_rate = 1
		draft.selling_price_list = "ENK Selling"
		draft.price_list_currency = "NOK"
		draft.plc_conversion_rate = 1
		draft.debit_to = self.settings.receivable_account
		draft.naming_series = self.settings.invoice_prefix + "-.YYYY.-.#####"
		draft.enk_tax_treatment = "Not registered"
		draft.enk_delivery_date = "2026-09-17"
		draft.enk_delivery_description = "Native timesheet-utkast for test"
		draft.insert()
		return draft

	def test_timesheet_draft_reuses_native_link_and_rejects_price_change(self):
		from enk_norge.billing import create_timesheet_invoice_draft

		timesheet = self._timesheet()
		result = create_timesheet_invoice_draft(self._timesheet_payload(timesheet))
		invoice = frappe.get_doc("Sales Invoice", result["name"])
		self.assertFalse(result["reused"])
		self.assertEqual(invoice.enk_external_id, timesheet_event_id(timesheet.name))
		self.assertEqual(invoice.currency, "NOK")
		self.assertEqual(invoice.items[0].qty, 2)
		self.assertEqual(invoice.items[0].rate, 50)
		self.assertEqual(invoice.timesheets[0].time_sheet, timesheet.name)
		self.assertEqual(create_timesheet_invoice_draft(self._timesheet_payload(timesheet))["name"], invoice.name)
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			create_timesheet_invoice_draft(self._timesheet_payload(timesheet, delivery_description="Endret levering"))
		with self.assertRaisesRegex(frappe.ValidationError, "samme sats"):
			create_timesheet_invoice_draft(self._timesheet_payload(self._timesheet(), unit_price="51.00"))
		native_timesheet = self._timesheet()
		native = self._native_timesheet_draft(native_timesheet)
		with self.assertRaisesRegex(frappe.ValidationError, native.name):
			create_timesheet_invoice_draft(self._timesheet_payload(native_timesheet))
		invoice.submit()
		timesheet.reload()
		self.assertEqual(timesheet.status, "Billed")
		self.assertEqual(timesheet.time_logs[0].sales_invoice, invoice.name)

	def _subscription(self, start_date="2026-10-01", end_date=None):
		plan = frappe.get_doc(
			{
				"doctype": "Subscription Plan",
				"plan_name": "ENK plan " + uuid4().hex[:12],
				"item": self.item.name,
				"price_determination": "Fixed Rate",
				"cost": 1000,
				"billing_interval": "Month",
				"billing_interval_count": 1,
				"currency": "NOK",
			}
		).insert()
		start = getdate(start_date)
		end = getdate(end_date) if end_date else add_days(start, 62)
		return frappe.get_doc(
			{
				"doctype": "Subscription",
				"party_type": "Customer",
				"party": self.customer.name,
				"company": self.company,
				"start_date": start,
				"end_date": end,
				"submit_invoice": 0,
				"generate_invoice_at": "Beginning of the current subscription period",
				"plans": [{"plan": plan.name, "qty": 1}],
			}
		).insert()

	def test_subscription_starting_today_waits_for_controlled_enk_draft(self):
		from enk_norge.billing import create_subscription_invoice_draft

		subscription = self._subscription(today())
		self.assertTrue(subscription.current_invoice_start)
		self.assertTrue(subscription.current_invoice_end)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"subscription": subscription.name}))
		source = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "fiktiv-avtale-start-i-dag.txt",
				"content": "Fiktiv avtale for test",
				"is_private": 1,
			}
		).insert()
		start = getdate(subscription.current_invoice_start)
		end = getdate(subscription.current_invoice_end)
		from enk_norge.billing import _advance_subscription_to_requested_period

		subscription.status = "Cancelled"
		with self.assertRaisesRegex(frappe.ValidationError, "avsluttet"):
			_advance_subscription_to_requested_period(subscription, start, end)
		result = create_subscription_invoice_draft(
			{
				"company": self.company,
				"subscription": subscription.name,
				"customer": self.customer.name,
				"customer_address": self.address.name,
				"posting_date": start.isoformat(),
				"delivery_date": start.isoformat(),
				"delivery_description": "Fiktiv abonnementstjeneste fra oppstartsdato",
				"due_date": start.isoformat(),
				"service_start_date": start.isoformat(),
				"service_end_date": end.isoformat(),
				"subscription_source_file": source.name,
			}
		)
		invoice = frappe.get_doc("Sales Invoice", result["name"])
		self.assertEqual(invoice.subscription, subscription.name)
		self.assertEqual(invoice.docstatus, 0)

	def test_subscription_draft_has_period_event_and_blocks_native_auto_submit(self):
		from enk_norge.billing import create_subscription_invoice_draft

		subscription = self._subscription(end_date="2026-12-01")
		source = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "fiktiv-avtale.txt",
				"content": "Fiktiv avtale for test",
				"is_private": 1,
			}
		).insert()
		data = {
			"company": self.company,
			"subscription": subscription.name,
			"customer": self.customer.name,
			"customer_address": self.address.name,
			"posting_date": "2026-09-20",
			"delivery_date": "2026-10-01",
			"delivery_description": "Fiktiv abonnementstjeneste oktober 2026",
			"due_date": "2026-10-01",
			"service_start_date": "2026-10-01",
			"service_end_date": "2026-10-31",
			"subscription_source_file": source.name,
		}
		result = create_subscription_invoice_draft(data)
		invoice = frappe.get_doc("Sales Invoice", result["name"])
		self.assertEqual(invoice.subscription, subscription.name)
		self.assertEqual(invoice.from_date.isoformat(), "2026-10-01")
		self.assertEqual(invoice.to_date.isoformat(), "2026-10-31")
		self.assertEqual(invoice.enk_external_id, subscription_event_id(subscription.name, "2026-10-01", "2026-10-31"))
		self.assertEqual(create_subscription_invoice_draft(data)["name"], invoice.name)
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)
		next_source = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "fiktiv-avtale-november.txt",
				"content": "Fiktiv avtale for test, neste periode",
				"is_private": 1,
			}
		).insert()
		next_data = data | {
			"posting_date": "2026-10-20",
			"delivery_date": "2026-11-01",
			"due_date": "2026-11-01",
			"delivery_description": "Fiktiv abonnementstjeneste november 2026",
			"service_start_date": "2026-11-01",
			"service_end_date": "2026-11-30",
			"subscription_source_file": next_source.name,
		}
		next_invoice = frappe.get_doc("Sales Invoice", create_subscription_invoice_draft(next_data)["name"])
		self.assertEqual(next_invoice.from_date.isoformat(), "2026-11-01")
		# Hooken avviser lagring av dette for ENK; db_set her verifiserer i tillegg
		# at billing-inngangen ikke kan omgå sperren med eksisterende data.
		frappe.db.set_value("Subscription", subscription.name, "submit_invoice", 1)
		with self.assertRaisesRegex(frappe.ValidationError, "Submit Generated Invoices"):
			create_subscription_invoice_draft(next_data | {"delivery_description": "Ny tekst"})
