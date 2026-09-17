"""Kontrakt for eksplisitte valutainndata uten kursoppslag."""

import unittest
from decimal import Decimal

import frappe

from enk_norge.currency import nok_amount, parse_currency_input


class CurrencyInputTest(unittest.TestCase):
	def test_foreign_currency_requires_explicit_rate_source_and_date(self):
		value = parse_currency_input(
			{
				"currency": "eur",
				"conversion_rate": "11.250000",
				"exchange_rate_source": "Kurs på leverandørfaktura",
				"exchange_rate_date": "2026-09-17",
			}
		)
		self.assertEqual(value.currency, "EUR")
		self.assertEqual(value.conversion_rate, Decimal("11.250000"))
		self.assertEqual(value.rate_date.isoformat(), "2026-09-17")
		self.assertEqual(nok_amount("100.00", value.conversion_rate), Decimal("1125.00"))

	def test_nok_has_no_separate_rate_documentation(self):
		value = parse_currency_input({"currency": "NOK", "conversion_rate": "1.000000"})
		self.assertEqual(value.currency, "NOK")
		self.assertEqual(value.conversion_rate, Decimal(1))
		with self.assertRaises(frappe.ValidationError):
			parse_currency_input({"currency": "NOK", "conversion_rate": "1.1"})

	def test_foreign_currency_rejects_missing_or_imprecise_rate(self):
		base = {
			"currency": "USD",
			"conversion_rate": "10.123456",
			"exchange_rate_source": "Bankbilag",
			"exchange_rate_date": "2026-09-17",
		}
		for invalid in (
			base | {"conversion_rate": "0"},
			base | {"conversion_rate": "10.1234567"},
			base | {"exchange_rate_source": ""},
			base | {"exchange_rate_date": ""},
		):
			with self.assertRaises(frappe.ValidationError):
				parse_currency_input(invalid)


@unittest.skipUnless(frappe.db.exists("DocType", "ENK Settings"), "Krever migrert ENK-oppsett")
class CurrencyWorkflowTest(unittest.TestCase):
	def setUp(self):
		from enk_norge.tests.test_workflows import WorkflowsTest

		self.workflows = WorkflowsTest
		WorkflowsTest.setUp(self)
		if not frappe.db.exists("Currency", "EUR"):
			self.skipTest("ERPNext mangler EUR.")

	def _foreign_customer(self):
		self.customer.customer_type = "Company"
		self.customer.save()
		self.address.country = "Sweden"
		self.address.save()

	def _foreign_supplier(self):
		self.supplier.country = "United States"
		self.supplier.save()

	def _rows(self, voucher_no, account):
		return frappe.get_all(
			"GL Entry",
			filters={"voucher_no": voucher_no, "account": account, "is_cancelled": 0},
			fields=["debit", "credit", "party", "party_type", "account_currency"],
		)

	def test_eur_export_payment_separates_bank_fee_and_gain(self):
		from enk_norge.api import create_sale
		from enk_norge.banking import create_payment
		from enk_norge.saft import _frappe_export_data, build_saf_t, validate_saf_t

		self._foreign_customer()
		sale = frappe.get_doc(
			"Sales Invoice",
			create_sale(
				dict(
					company=self.company,
					customer=self.customer.name,
					customer_address=self.address.name,
					posting_date="2026-09-17",
					delivery_date="2026-09-17",
					due_date="2026-10-01",
					description="Fjernleverbar tjeneste",
					quantity="1",
					unit_price="100.00",
					currency="EUR",
					conversion_rate="11.000000",
					exchange_rate_source="Avtalt kurs på faktura",
					exchange_rate_date="2026-09-17",
					tax_treatment="Export services",
				)
			)["name"],
		)
		self.assertEqual(sale.debit_to.split(" - ")[0], "A110-EUR")
		self.assertEqual(sale.base_grand_total, 1100)
		sale.submit()
		result = create_payment(
			"Sales Invoice",
			sale.name,
			"100.00",
			"2026-09-18",
			"EUR-SALE-1",
			fee="20.00",
			bank_amount_nok="1180.00",
			exchange_rate_source="NOK-innbetaling i bank",
			exchange_rate_date="2026-09-18",
		)
		retry = create_payment(
			"Sales Invoice", sale.name, "100.00", "2026-09-18", "EUR-SALE-1", fee="20.00",
			bank_amount_nok="1180.00", exchange_rate_source="NOK-innbetaling i bank", exchange_rate_date="2026-09-18",
		)
		self.assertTrue(retry["reused"])
		self.assertEqual(retry["adjustment_journal_entry"], result["adjustment_journal_entry"])
		with self.assertRaisesRegex(frappe.ValidationError, "andre opplysninger"):
			create_payment(
				"Sales Invoice", sale.name, "100.00", "2026-09-18", "EUR-SALE-1", fee="20.00",
				bank_amount_nok="1181.00", exchange_rate_source="NOK-innbetaling i bank", exchange_rate_date="2026-09-18",
			)
		payment = frappe.get_doc("Payment Entry", result["name"])
		adjustment = frappe.get_doc("Journal Entry", result["adjustment_journal_entry"])
		self.assertTrue(payment.enk_posting_contract)
		self.assertTrue(adjustment.enk_posting_contract)
		with self.assertRaisesRegex(frappe.ValidationError, "sammen med betalingen"):
			adjustment.submit()
		adjustment.reload()
		payment.submit()
		adjustment.reload()
		self.assertEqual(adjustment.docstatus, 1)
		sale.reload()
		self.assertEqual(sale.outstanding_amount, 0)
		self.assertEqual(payment.enk_bank_amount_nok, 1180)
		self.assertEqual(payment.enk_fee_amount_nok, 20)
		self.assertEqual(sum(row.debit - row.credit for row in self._rows(payment.name, sale.debit_to)), -1100)
		bank_total = sum(row.debit - row.credit for voucher in (payment.name, adjustment.name) for row in self._rows(voucher, self.settings.bank_ledger_account))
		self.assertEqual(bank_total, 1180)
		self.assertEqual(self._rows(adjustment.name, self.settings.fees_account)[0].debit, 20)
		self.assertEqual(self._rows(adjustment.name, self.settings.fx_gain_account)[0].credit, 100)
		data = _frappe_export_data(self.company, frappe.utils.getdate("2026-09-01"), frappe.utils.getdate("2026-09-30"))
		validate_saf_t(build_saf_t(data))
		retry = create_payment(
			"Sales Invoice", sale.name, "100.00", "2026-09-18", "EUR-SALE-1", fee="20.00",
			bank_amount_nok="1180.00", exchange_rate_source="NOK-innbetaling i bank", exchange_rate_date="2026-09-18",
		)
		self.assertTrue(retry["reused"])
		with self.assertRaisesRegex(frappe.ValidationError, "sammen med betalingen"):
			adjustment.cancel()
		payment.cancel()
		adjustment.reload()
		self.assertEqual(adjustment.docstatus, 2)
		sale.reload()
		self.assertEqual(sale.outstanding_amount, 100)


	def test_eur_foreign_saas_payment_separates_bank_fee_and_loss(self):
		from enk_norge.api import create_purchase
		from enk_norge.banking import create_payment
		from enk_norge.vat import create_reverse_charge_draft

		self._foreign_supplier()
		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		purchase = frappe.get_doc(
			"Purchase Invoice",
			create_purchase(
				dict(
					company=self.company,
					supplier=self.supplier.name,
					posting_date="2026-09-17",
					bill_date="2026-09-17",
					bill_no="EUR-SAAS-1",
					due_date="2026-10-01",
					description="Utenlandsk SaaS",
					category="software",
					gross_amount="100.00",
					vat_rate="0",
					foreign_service=1,
					currency="EUR",
					conversion_rate="11.000000",
					exchange_rate_source="Kurs på leverandørfaktura",
					exchange_rate_date="2026-09-17",
				)
			)["name"],
		)
		self.workflows.attach(self, purchase)
		self.assertEqual(purchase.credit_to.split(" - ")[0], "L100-EUR")
		self.assertEqual(purchase.enk_vat_basis, 1100)
		purchase.submit()
		self.assertEqual(self._rows(purchase.name, self.settings.software_account)[0].debit, 1100)
		reverse = frappe.get_doc("Journal Entry", create_reverse_charge_draft(self.company, "2026-10-31")["name"])
		self.assertEqual(sum(row.credit_in_account_currency for row in reverse.accounts if row.account == self.settings.reverse_vat_account), 275)
		result = create_payment(
			"Purchase Invoice",
			purchase.name,
			"100.00",
			"2026-09-18",
			"EUR-BUY-1",
			fee="20.00",
			bank_amount_nok="1200.00",
			exchange_rate_source="NOK-belastning i bank",
			exchange_rate_date="2026-09-18",
		)
		payment = frappe.get_doc("Payment Entry", result["name"])
		adjustment = frappe.get_doc("Journal Entry", result["adjustment_journal_entry"])
		with self.assertRaisesRegex(frappe.ValidationError, "sammen med betalingen"):
			adjustment.submit()
		adjustment.reload()
		payment.submit()
		adjustment.reload()
		self.assertEqual(adjustment.docstatus, 1)
		purchase.reload()
		self.assertEqual(purchase.outstanding_amount, 0)
		bank_total = sum(row.debit - row.credit for voucher in (payment.name, adjustment.name) for row in self._rows(voucher, self.settings.bank_ledger_account))
		self.assertEqual(bank_total, -1200)
		self.assertEqual(self._rows(adjustment.name, self.settings.fees_account)[0].debit, 20)
		self.assertEqual(self._rows(adjustment.name, self.settings.fx_loss_account)[0].debit, 80)
