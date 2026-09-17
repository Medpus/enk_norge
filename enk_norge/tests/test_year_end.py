from __future__ import annotations

import json
import unittest
from datetime import date
from decimal import Decimal

from enk_norge.year_end import (
	LedgerEntry,
	PersonalIncomeInput,
	TaxAdjustment,
	TaxPoolSummary,
	YearEndError,
	calculate_personal_income,
	calculate_pool_from_values,
	calculate_purchase_tax_adjustment,
	calculate_year_end,
	parse_source_references,
	snapshot_hash,
	snapshot_payload,
)


class YearEndCoreTest(unittest.TestCase):
	def ledger_entries(self):
		return [
			LedgerEntry("Bank", Decimal("1000"), Decimal("0"), "Journal Entry", "OPEN", date(2025, 12, 31)),
			LedgerEntry("Equity", Decimal("0"), Decimal("1000"), "Journal Entry", "OPEN", date(2025, 12, 31)),
			LedgerEntry("Bank", Decimal("1000"), Decimal("0"), "Sales Invoice", "SINV-1", date(2026, 1, 1)),
			LedgerEntry("Income", Decimal("0"), Decimal("1000"), "Sales Invoice", "SINV-1", date(2026, 1, 1)),
			LedgerEntry(
				"Expense", Decimal("200"), Decimal("0"), "Purchase Invoice", "PINV-1", date(2026, 1, 2)
			),
			LedgerEntry("Bank", Decimal("0"), Decimal("200"), "Purchase Invoice", "PINV-1", date(2026, 1, 2)),
			LedgerEntry(
				"Depreciation", Decimal("300"), Decimal("0"), "Journal Entry", "ACC-1", date(2026, 12, 31)
			),
			LedgerEntry("Asset", Decimal("0"), Decimal("300"), "Journal Entry", "ACC-1", date(2026, 12, 31)),
		]

	@property
	def categories(self):
		return {
			"Bank": "Asset",
			"Asset": "Asset",
			"Equity": "Equity",
			"Income": "Income",
			"Expense": "Expense",
			"Depreciation": "Expense",
		}

	def test_calculates_profit_tax_depreciation_and_equity_reconciliation(self) -> None:
		calculation = calculate_year_end(
			self.ledger_entries(),
			account_categories=self.categories,
			depreciation_account="Depreciation",
			tax_pools=[TaxPoolSummary("POOL-A", Decimal("400"), Decimal("0"))],
			tax_adjustments=[
				TaxAdjustment(Decimal("50"), "Ikke fradragsberettiget kostnad", "Purchase Invoice", "PINV-2")
			],
		)
		self.assertEqual(calculation.operating_income, Decimal("1000.00"))
		self.assertEqual(calculation.operating_expenses, Decimal("500.00"))
		self.assertEqual(calculation.accounting_profit, Decimal("500.00"))
		self.assertEqual(calculation.book_depreciation, Decimal("300.00"))
		self.assertEqual(calculation.tax_depreciation, Decimal("400.00"))
		self.assertEqual(calculation.taxable_business_profit, Decimal("450.00"))
		self.assertEqual(calculation.net_assets, Decimal("1500.00"))
		self.assertEqual(calculation.equity_reconciliation_difference, Decimal("0.00"))

	def test_negative_pool_income_is_added_without_changing_bookkeeping_result(self) -> None:
		calculation = calculate_year_end(
			self.ledger_entries(),
			account_categories=self.categories,
			depreciation_account="Depreciation",
			tax_pools=[TaxPoolSummary("POOL-A", Decimal("300"), Decimal("75"))],
		)
		self.assertEqual(calculation.accounting_profit, Decimal("500.00"))
		self.assertEqual(calculation.taxable_business_profit, Decimal("575.00"))

	def test_asset_book_gain_is_replaced_by_tax_saldo_treatment(self):
		entries = [
			LedgerEntry("Asset", Decimal("30000"), Decimal("0")),
			LedgerEntry("Equity", Decimal("0"), Decimal("30000")),
			LedgerEntry("Bank", Decimal("40000"), Decimal("0")),
			LedgerEntry("Asset", Decimal("0"), Decimal("30000")),
			LedgerEntry("Income", Decimal("0"), Decimal("10000")),
		]
		for pool in (
			TaxPoolSummary("POOL-A", Decimal("0"), Decimal("10000"), Decimal("40000")),
			TaxPoolSummary("POOL-A", Decimal("0"), Decimal("0"), Decimal("40000"), Decimal("10000")),
		):
			result = calculate_year_end(
				entries,
				account_categories=self.categories,
				depreciation_account="Depreciation",
				asset_gain_account="Income",
				tax_pools=[pool],
			)
			self.assertEqual(result.accounting_profit, Decimal("10000"))
			self.assertEqual(result.taxable_business_profit, Decimal("10000"))
			self.assertEqual(result.book_disposal_result, Decimal("10000"))

	def test_purchase_tax_adjustment_uses_only_expense_lines_and_reverses_credit_notes(self) -> None:
		self.assertEqual(
			calculate_purchase_tax_adjustment(
				[Decimal("1000.00"), Decimal("-100.00")], Decimal("0.60"), is_credit_note=False
			),
			Decimal("360.00"),
		)
		self.assertEqual(
			calculate_purchase_tax_adjustment(
				[Decimal("1000.00"), Decimal("-100.00")], Decimal("0.60"), is_credit_note=True
			),
			Decimal("-360.00"),
		)
		with self.assertRaisesRegex(YearEndError, "Skattemessig fradragsandel"):
			calculate_purchase_tax_adjustment([], Decimal("1.01"), is_credit_note=False)

	def test_unknown_account_fails_closed(self) -> None:
		with self.assertRaisesRegex(YearEndError, "mangler årsoppgjørskategori"):
			calculate_year_end(
				[LedgerEntry("Unknown", Decimal("1"), Decimal("0"))],
				account_categories=self.categories,
				depreciation_account="Depreciation",
			)

	def test_manual_adjustment_requires_reason_and_source(self) -> None:
		with self.assertRaisesRegex(YearEndError, "begrunnelse og kildebilag"):
			calculate_year_end(
				self.ledger_entries(),
				account_categories=self.categories,
				depreciation_account="Depreciation",
				tax_adjustments=[TaxAdjustment(Decimal("1"), "", "", "")],
			)

	def test_pool_values_delegate_to_2026_rule_engine(self) -> None:
		pool = calculate_pool_from_values(
			{
				"income_year": 2026,
				"saldo_group": "a",
				"opening_balance": "10000",
				"acquisitions": "0",
				"disposal_proceeds": "45000",
			}
		)
		self.assertEqual(pool.depreciation_deduction, Decimal("0"))
		self.assertEqual(pool.negative_balance_income, Decimal("10500.00"))
		self.assertEqual(pool.closing_balance, Decimal("-24500.00"))
		with self.assertRaisesRegex(YearEndError, "bare inntektsåret 2026"):
			calculate_pool_from_values({"income_year": 2027, "saldo_group": "a", "opening_balance": "0"})

	def test_source_references_are_complete_and_match_amount(self) -> None:
		references = parse_source_references(
			json.dumps(
				[
					{"doctype": "Purchase Invoice", "name": "PINV-1", "amount": "100.01"},
					{"doctype": "Journal Entry", "name": "ACC-1", "amount": "99.99"},
				]
			),
			Decimal("200.00"),
			"Kildebilag for anskaffelser",
		)
		self.assertEqual(references[0]["amount"], "100.01")
		with self.assertRaisesRegex(YearEndError, "krever minst ett kildebilag"):
			parse_source_references("[]", Decimal("1"), "Kildebilag for avgang")

	def test_snapshot_hash_is_stable_independent_of_input_order(self) -> None:
		calculation = calculate_year_end(
			self.ledger_entries(), account_categories=self.categories, depreciation_account="Depreciation"
		)
		controls = {
			"person_income_reviewed": False,
			"shielding_reviewed": False,
			"private_corrections_reviewed": False,
		}
		first = snapshot_payload(
			calculation,
			income_year=2026,
			entries=self.ledger_entries(),
			tax_pools=[
				TaxPoolSummary("B", Decimal("1"), Decimal("0")),
				TaxPoolSummary("A", Decimal("2"), Decimal("0")),
			],
			tax_adjustments=[],
			controls=controls,
		)
		second = snapshot_payload(
			calculation,
			income_year=2026,
			entries=list(reversed(self.ledger_entries())),
			tax_pools=[
				TaxPoolSummary("A", Decimal("2"), Decimal("0")),
				TaxPoolSummary("B", Decimal("1"), Decimal("0")),
			],
			tax_adjustments=[],
			controls=dict(reversed(list(controls.items()))),
		)
		self.assertEqual(snapshot_hash(first), snapshot_hash(second))


try:
	import frappe

	from enk_norge.tests.test_workflows import WorkflowsTest
except ModuleNotFoundError:
	frappe = None

	class WorkflowsTest(unittest.TestCase):
		purchase = None
		attach = None


@unittest.skipIf(frappe is None, "Krever Frappe-testsite")
class YearEndWorkflowTest(unittest.TestCase):
	def setUp(self) -> None:
		from uuid import uuid4

		from enk_norge.setup import create_company, get_settings

		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("enk_year_end_test")
		self.company = create_company(
			dict(
				company_name="Årsrapport ENK " + uuid4().hex[:8],
				abbr=uuid4().hex[:5].upper(),
				organization_number="974761076",
				bank_account="86011117947",
				bank_name="Fiktiv testbank",
				start_date="2026-01-01",
				address_line="Testveien 1",
				postal_code="0001",
				city="Oslo",
				phone="40000000",
				vat_registered=0,
				history_confirmed=1,
			)
		)["company"]
		self.settings = get_settings(self.company)

	def tearDown(self) -> None:
		frappe.db.rollback(save_point="enk_year_end_test")
		frappe.set_user(self.previous_user)

	def test_report_revisions_private_receipt_and_depreciation_draft(self) -> None:
		from enk_norge.year_end import (
			build_year_report,
			create_depreciation_journal_entry_draft,
			mark_year_report_manually_filed,
		)

		asset_entry = frappe.get_doc(
			dict(
				doctype="Journal Entry",
				company=self.company,
				posting_date="2026-01-02",
				voucher_type="Journal Entry",
				enk_manual_reason="Aktivering av fiktivt utstyr i årsrapporttesten",
				accounts=[
					dict(account=self.settings.asset_account, debit_in_account_currency="30000.00"),
					dict(account=self.settings.owner_account, credit_in_account_currency="30000.00"),
				],
			)
		).insert()
		frappe.get_doc(
			dict(
				doctype="File",
				file_name="anskaffelsesbilag.txt",
				content="Fiktivt anskaffelsesbilag",
				is_private=1,
				attached_to_doctype="Journal Entry",
				attached_to_name=asset_entry.name,
			)
		).insert()
		asset_entry.submit()
		pool = frappe.get_doc(
			dict(
				doctype="ENK Tax Pool",
				company=self.company,
				income_year=2026,
				saldo_group="a",
				opening_balance="0.00",
				acquisitions="30000.00",
				acquisition_sources_json=json.dumps(
					[{"doctype": "Journal Entry", "name": asset_entry.name, "amount": "30000.00"}]
				),
			)
		).insert()
		self.assertEqual(Decimal(str(pool.depreciation_deduction)), Decimal("9000.00"))

		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		customer = frappe.get_doc(
			dict(
				doctype="Customer",
				customer_name="Årsrapportkunde",
				customer_type="Company",
				customer_group=customer_group,
				territory=territory,
			)
		).insert()
		address = frappe.get_doc(
			dict(
				doctype="Address",
				address_title=customer.name,
				address_type="Billing",
				address_line1="Kundeveien 1",
				city="Oslo",
				pincode="0001",
				country="Norway",
				links=[dict(link_doctype="Customer", link_name=customer.name)],
			)
		).insert()
		from enk_norge.api import create_sale

		sale = frappe.get_doc(
			"Sales Invoice",
			create_sale(
				dict(
					company=self.company,
					customer=customer.name,
					customer_address=address.name,
					posting_date="2026-09-17",
					delivery_date="2026-09-17",
					due_date="2026-10-01",
					description="Fiktiv konsulenttjeneste",
					quantity="1",
					unit_price="10000",
				)
			)["name"],
		)
		sale.submit()
		controls = dict(
			person_income_reviewed=True, shielding_reviewed=True, private_corrections_reviewed=True
		)
		personal_inputs = {"capital_return_base": "0"}
		first = build_year_report(
			self.company, 2026, controls=controls, personal_income_inputs=personal_inputs
		)
		self.assertEqual(first["status"], "Ready for review")
		self.assertEqual(Decimal(str(first["taxable_business_profit"])), Decimal("1000.00"))
		for status in ("Ready for review", "Manually filed"):
			forged = frappe.new_doc("ENK Year Report")
			forged.company = self.company
			forged.income_year = 2026
			forged.revision = 99 if status == "Ready for review" else 98
			forged.status = status
			with self.assertRaises(frappe.ValidationError):
				forged.insert()
		second = build_year_report(self.company, 2026, controls=controls)
		self.assertEqual(second["revision"], 2)
		report = frappe.get_doc("ENK Year Report", second["name"])
		self.assertEqual(len(json.loads(report.snapshot_history_json)), 1)
		self.assertEqual(json.loads(report.personal_income_inputs_json)["capital_return_base"], "0.00")
		self.assertEqual(
			json.loads(report.snapshot_json)["personal_income_result"]["person_income"], "1000.00"
		)

		draft = create_depreciation_journal_entry_draft(self.company, 2026)
		self.assertEqual(Decimal(draft["amount"]), Decimal("9000.00"))
		self.assertEqual(create_depreciation_journal_entry_draft(self.company, 2026)["name"], draft["name"])
		frappe.get_doc("Journal Entry", draft["name"]).submit()
		third = build_year_report(self.company, 2026, controls=controls)
		self.assertEqual(Decimal(str(third["taxable_business_profit"])), Decimal("1000.00"))

		unlinked_receipt = frappe.get_doc(
			dict(
				doctype="File",
				file_name="uknyttet-leveringskvittering.txt",
				content="Fiktiv kvittering",
				is_private=1,
			)
		).insert()
		with self.assertRaises(frappe.ValidationError):
			mark_year_report_manually_filed(self.company, 2026, unlinked_receipt.name)
		receipt = frappe.get_doc(
			dict(
				doctype="File",
				file_name="leveringskvittering.txt",
				content="Fiktiv kvittering",
				is_private=1,
				attached_to_doctype="ENK Year Report",
				attached_to_name=third["name"],
			)
		).insert()
		filed = mark_year_report_manually_filed(self.company, 2026, receipt.name)
		self.assertEqual(filed["status"], "Manually filed")
		filed_report = frappe.get_doc("ENK Year Report", filed["name"])
		filed_snapshot = filed_report.snapshot_json
		with self.assertRaises(frappe.ValidationError):
			filed_report.save()
		with self.assertRaises(frappe.ValidationError):
			filed_report.delete()
		with self.assertRaises(frappe.ValidationError):
			receipt.delete()
		correction = build_year_report(self.company, 2026, controls=controls)
		self.assertEqual(correction["revision"], 4)
		self.assertNotEqual(correction["name"], filed["name"])
		self.assertEqual(frappe.get_doc("ENK Year Report", filed["name"]).snapshot_json, filed_snapshot)
		self.assertEqual(
			len(json.loads(frappe.get_doc("ENK Year Report", correction["name"]).snapshot_history_json)), 3
		)


@unittest.skipIf(frappe is None, "Krever Frappe-testsite")
class YearEndPurchaseTaxAdjustmentWorkflowTest(unittest.TestCase):
	setUp = WorkflowsTest.setUp
	tearDown = WorkflowsTest.tearDown
	purchase = WorkflowsTest.purchase
	attach = WorkflowsTest.attach

	def test_purchase_tax_adjustment_excludes_private_line_reverses_credit_and_rejects_manual_duplicate(self):
		from enk_norge.api import create_credit_note
		from enk_norge.year_end import build_year_report

		self.settings.vat_registered = 1
		self.settings.vat_registration_date = "2026-01-01"
		self.settings.save()
		purchase = self.purchase(
			business_fraction="0.80",
			deductible_fraction="0.60",
			tax_deductible_fraction="0.50",
			tax_adjustment_reason="Fiktiv ikke-fradragsberettiget næringsandel",
		)
		self.attach(purchase)
		purchase.submit()
		controls = dict(
			person_income_reviewed=True, shielding_reviewed=True, private_corrections_reviewed=True
		)
		report = build_year_report(self.company, 2026, controls=controls)
		self.assertEqual(Decimal(str(report["taxable_business_profit"])), Decimal("-425.00"))
		stored = frappe.get_doc("ENK Year Report", report["name"])
		adjustments = json.loads(stored.tax_adjustments_json)
		self.assertEqual(
			adjustments,
			[
				{
					"effect": "425.00",
					"reason": "Fiktiv ikke-fradragsberettiget næringsandel",
					"reference_doctype": "Purchase Invoice",
					"reference_name": purchase.name,
				}
			],
		)
		with self.assertRaises(frappe.ValidationError):
			build_year_report(
				self.company,
				2026,
				tax_adjustments=[
					dict(
						effect="1.00",
						reason="Ville dobleført automatisk justering",
						reference_doctype="Purchase Invoice",
						reference_name=purchase.name,
					)
				],
				controls=controls,
			)
		credit = frappe.get_doc(
			"Purchase Invoice",
			create_credit_note("Purchase Invoice", purchase.name, "2026-10-01")["name"],
		)
		credit.enk_tax_deductible_fraction = purchase.enk_tax_deductible_fraction
		credit.enk_tax_adjustment_reason = purchase.enk_tax_adjustment_reason
		credit.enk_business_fraction = purchase.enk_business_fraction
		credit.enk_deductible_fraction = purchase.enk_deductible_fraction
		credit.bill_no = "KREDIT-" + purchase.bill_no
		credit.bill_date = "2026-10-01"
		credit.save()
		self.attach(credit)
		credit.submit()
		corrected = build_year_report(self.company, 2026, controls=controls)
		corrected_report = frappe.get_doc("ENK Year Report", corrected["name"])
		self.assertEqual(Decimal(str(corrected_report.manual_tax_adjustments)), Decimal("0.00"))
		self.assertEqual(
			[Decimal(row["effect"]) for row in json.loads(corrected_report.tax_adjustments_json)],
			[Decimal("425.00"), Decimal("-425.00")],
		)


@unittest.skipIf(frappe is None, "Krever Frappe-testsite")
class AssetDisposalWorkflowTest(unittest.TestCase):
	setUp = WorkflowsTest.setUp
	tearDown = WorkflowsTest.tearDown
	attach = WorkflowsTest.attach

	def _asset_acquisition(self, amount: str = "30000.00"):
		entry = frappe.get_doc(
			dict(
				doctype="Journal Entry",
				company=self.company,
				posting_date="2026-01-02",
				voucher_type="Journal Entry",
				enk_manual_reason="Aktivering av fiktivt driftsmiddel for test av avgang",
				accounts=[
					dict(account=self.settings.asset_account, debit_in_account_currency=amount),
					dict(account=self.settings.owner_account, credit_in_account_currency=amount),
				],
			)
		).insert()
		self.attach(entry)
		entry.submit()
		return entry

	def _source_file(self, name: str):
		return frappe.get_doc(
			dict(doctype="File", file_name=name, content="Fiktivt salgs- eller uttaksbevis", is_private=1)
		).insert()

	def test_asset_sale_pool_and_direct_income_have_one_tax_effect(self):
		from enk_norge.year_end import build_year_report, create_asset_disposal_journal_entry_draft

		asset = self._asset_acquisition()
		proof = self._source_file("fiktiv-salgskontrakt.txt")
		created = create_asset_disposal_journal_entry_draft(
			self.company,
			"2026-09-01",
			"40000.00",
			direct_income="10000.00",
			description="Fiktivt driftsmiddel",
			private_source_file=proof.name,
			carrying_amount="30000.00",
		)
		disposal = frappe.get_doc("Journal Entry", created["name"])
		self.assertEqual(disposal.voucher_type, "Asset Disposal")
		self.assertTrue(disposal.enk_posting_contract)
		disposal.submit()
		pool = frappe.get_doc(
			dict(
				doctype="ENK Tax Pool",
				company=self.company,
				income_year=2026,
				saldo_group="a",
				opening_balance="0.00",
				acquisitions="30000.00",
				acquisition_sources_json=json.dumps(
					[{"doctype": "Journal Entry", "name": asset.name, "amount": "30000.00"}]
				),
				disposal_proceeds="40000.00",
				disposal_sources_json=json.dumps([created["disposal_source"]]),
				disposal_proceeds_taken_to_income=created["disposal_proceeds_taken_to_income"],
			)
		).insert()
		self.assertEqual(Decimal(str(pool.negative_balance_income)), Decimal("0.00"))
		controls = dict(
			person_income_reviewed=True, shielding_reviewed=True, private_corrections_reviewed=True
		)
		report = build_year_report(self.company, 2026, controls=controls)
		self.assertEqual(Decimal(str(report["accounting_profit"])), Decimal("10000.00"))
		self.assertEqual(Decimal(str(report["taxable_business_profit"])), Decimal("10000.00"))
		snapshot_pool = json.loads(frappe.get_doc("ENK Year Report", report["name"]).snapshot_json)[
			"tax_pools"
		][0]
		self.assertEqual(snapshot_pool["disposal_proceeds"], "40000.00")
		self.assertEqual(snapshot_pool["disposal_proceeds_taken_to_income"], "10000.00")
		self.assertTrue(snapshot_pool["source_hash"])

	def test_asset_withdrawal_requires_private_proof_and_uses_owner_account(self):
		from enk_norge.year_end import create_asset_disposal_journal_entry_draft

		self._asset_acquisition()
		with self.assertRaisesRegex(frappe.ValidationError, "privat kildebilag"):
			create_asset_disposal_journal_entry_draft(
				self.company, "2026-09-01", "30000.00", disposition="Withdrawal", description="Fiktivt uttak"
			)
		proof = self._source_file("fiktiv-uttaksverdi.txt")
		created = create_asset_disposal_journal_entry_draft(
			self.company,
			"2026-09-01",
			"30000.00",
			disposition="Withdrawal",
			description="Fiktivt uttak til markedsverdi",
			private_source_file=proof.name,
			carrying_amount="30000.00",
		)
		disposal = frappe.get_doc("Journal Entry", created["name"])
		disposal.submit()
		self.assertEqual(
			Decimal(
				str(
					frappe.db.get_value(
						"GL Entry",
						{"voucher_no": disposal.name, "account": self.settings.withdrawal_account},
						"debit",
					)
				)
			),
			Decimal("30000.00"),
		)
		self.assertEqual(
			Decimal(
				str(
					frappe.db.get_value(
						"GL Entry",
						{"voucher_no": disposal.name, "account": self.settings.asset_account},
						"credit",
					)
				)
			),
			Decimal("30000.00"),
		)

	def test_sale_below_book_value_removes_whole_asset_and_reconciles_tax(self):
		from enk_norge.year_end import build_year_report, create_asset_disposal_journal_entry_draft

		asset = self._asset_acquisition()
		proof = self._source_file("fiktiv-bokverdi-og-salg.txt")
		result = create_asset_disposal_journal_entry_draft(
			self.company,
			"2026-09-01",
			"20000",
			description="Hele driftsmiddelet solgt med tap",
			private_source_file=proof.name,
			carrying_amount="30000",
		)
		entry = frappe.get_doc("Journal Entry", result["name"])
		entry.submit()
		balance = frappe.db.sql(
			"select sum(debit-credit) from `tabGL Entry` where company=%s and account=%s and is_cancelled=0",
			(self.company, self.settings.asset_account),
		)[0][0]
		self.assertEqual(Decimal(str(balance)), 0)
		with self.assertRaisesRegex(frappe.ValidationError, "saldogrupper"):
			build_year_report(self.company)
		frappe.get_doc(
			dict(
				doctype="ENK Tax Pool",
				company=self.company,
				income_year=2026,
				saldo_group="a",
				opening_balance=0,
				acquisitions=30000,
				acquisition_sources_json=json.dumps(
					[dict(doctype=asset.doctype, name=asset.name, amount="30000")]
				),
				disposal_proceeds=20000,
				disposal_sources_json=json.dumps([result["disposal_source"]]),
			)
		).insert()
		report = build_year_report(self.company)
		self.assertEqual(Decimal(str(report["accounting_profit"])), -10000)
		self.assertEqual(Decimal(str(report["taxable_business_profit"])), -3000)
		self.assertEqual(
			next(row["amount"] for row in report["return_basis"] if row["code"] == "7880"), "10000.00"
		)

	def test_asset_sale_is_included_in_later_vat_threshold(self):
		from enk_norge.year_end import create_asset_disposal_journal_entry_draft

		self._asset_acquisition()
		proof = self._source_file("fiktivt-salgsbilag.txt")
		result = create_asset_disposal_journal_entry_draft(
			self.company,
			"2026-09-01",
			"40000",
			description="Dokumentert salg",
			private_source_file=proof.name,
			carrying_amount="30000",
		)
		frappe.get_doc("Journal Entry", result["name"]).submit()
		invoice = WorkflowsTest.sale(self, unit_price="10001")
		with self.assertRaisesRegex(frappe.ValidationError, "50 000"):
			invoice.submit()


def run() -> dict[str, int | bool]:
	if frappe is None or frappe.local.site != "test.localhost":
		raise RuntimeError("Kun test.localhost kan kjøre denne integrasjonstesten.")
	if not frappe.db.exists("DocType", "ENK Tax Pool"):
		raise RuntimeError("Kjør migrate før ENK-årsavslutningstesten.")
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.defaultTestLoader.loadTestsFromTestCase(YearEndWorkflowTest)
	)
	frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("ENK-årsavslutningstesten feilet.")
	return {"tests": result.testsRun, "successful": True}


if __name__ == "__main__":
	unittest.main()


class PersonalIncomeTest(unittest.TestCase):
	def test_official_categories_and_interest_relation(self):
		r = calculate_personal_income(
			Decimal("1000"),
			PersonalIncomeInput(
				capital_return_base=Decimal("600"),
				capital_income=Decimal("100"),
				capital_costs=Decimal("40"),
				qualifying_business_debt=Decimal("1000"),
				qualifying_business_debt_interest=Decimal("100"),
				special_deductions=Decimal("20"),
				documented_shielding=Decimal("30"),
				carried_forward_negative=Decimal("50"),
			),
		)
		self.assertEqual(r.person_income, Decimal("920.00"))
		self.assertEqual(r.interest_addback, Decimal("40.00"))

	def test_zero_base_allows_zero_shielding(self):
		self.assertEqual(
			calculate_personal_income(
				Decimal("10"), PersonalIncomeInput(capital_return_base=Decimal("0"))
			).person_income,
			Decimal("10.00"),
		)

	def test_negative_current_person_income_is_added_to_carryforward(self):
		result = calculate_personal_income(
			Decimal("100"),
			PersonalIncomeInput(
				capital_return_base=Decimal("0"),
				capital_income=Decimal("200"),
				carried_forward_negative=Decimal("40"),
			),
		)
		self.assertEqual(result.person_income_before_carryforward, Decimal("-100.00"))
		self.assertEqual(result.person_income, Decimal("-100.00"))
		self.assertEqual(result.carried_forward_negative_used, Decimal("0.00"))
		self.assertEqual(result.remaining_negative_carryforward, Decimal("140.00"))

	def test_negative_shielding_base_is_rejected_and_interest_addback_is_capped(self):
		with self.assertRaisesRegex(YearEndError, "Kapitalavkastningsgrunnlag"):
			calculate_personal_income(Decimal("0"), PersonalIncomeInput(capital_return_base=Decimal("-1")))
		result = calculate_personal_income(
			Decimal("0"),
			PersonalIncomeInput(
				capital_return_base=Decimal("0"),
				qualifying_business_debt=Decimal("100"),
				qualifying_business_debt_interest=Decimal("100"),
			),
		)
		self.assertEqual(result.interest_addback, Decimal("100.00"))
