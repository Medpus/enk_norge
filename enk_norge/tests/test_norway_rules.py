from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from enk_norge.norway_rules import (
	ASSET_COST_THRESHOLD,
	REVERSE_CHARGE_UNREGISTERED_THRESHOLD,
	VAT_REGISTRATION_THRESHOLD,
	AssetTreatment,
	ForeignRemoteServicePurchase,
	RuleValidationError,
	SaldoGroup,
	TurnoverEvent,
	UnsupportedRuleDateError,
	VATTreatment,
	assess_asset,
	asset_cost_basis,
	calculate_saldo_pool,
	foreign_reverse_charge_status,
	rolling_vat_registration_status,
	round_nok,
	validate_bank_account,
	validate_norwegian_bank_account,
	validate_norwegian_organization_number,
	validate_org_number,
	vat_registration_threshold_crossings,
)


class IdentifierValidationTest(unittest.TestCase):
	def test_organization_number_normalizes_and_checks_mod11(self) -> None:
		result = validate_norwegian_organization_number("974 761 076")
		self.assertTrue(result.valid)
		self.assertEqual(result.normalized_value, "974761076")
		self.assertFalse(validate_norwegian_organization_number("974761075").valid)
		self.assertTrue(validate_org_number("974761076"))
		self.assertFalse(validate_org_number("974761075"))

	def test_bank_account_normalizes_and_checks_mod11(self) -> None:
		result = validate_norwegian_bank_account("8601.11.17947")
		self.assertTrue(result.valid)
		self.assertEqual(result.normalized_value, "86011117947")
		self.assertFalse(validate_norwegian_bank_account("8601 11 17946").valid)
		self.assertFalse(validate_norwegian_bank_account("not-an-account").valid)
		self.assertTrue(validate_bank_account("86011117947"))
		self.assertFalse(validate_bank_account("86011117946"))


class VatRegistrationTest(unittest.TestCase):
	AS_OF = date(2026, 9, 17)

	def test_exactly_50000_does_not_require_registration(self) -> None:
		result = rolling_vat_registration_status(
			[TurnoverEvent(date(2026, 9, 17), VAT_REGISTRATION_THRESHOLD, VATTreatment.TAXABLE)],
			as_of=self.AS_OF,
		)
		self.assertEqual(result.registration_basis, Decimal("50000"))
		self.assertFalse(result.registration_required)

	def test_zero_rated_counts_and_exempt_is_separate(self) -> None:
		result = rolling_vat_registration_status(
			[
				TurnoverEvent(date(2026, 1, 1), Decimal("49999.99"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2026, 9, 17), Decimal("0.01"), VATTreatment.ZERO_RATED),
				TurnoverEvent(date(2026, 9, 17), Decimal("900000"), VATTreatment.EXEMPT),
			],
			as_of=self.AS_OF,
		)
		self.assertEqual(result.taxable_turnover, Decimal("49999.99"))
		self.assertEqual(result.zero_rated_turnover, Decimal("0.01"))
		self.assertEqual(result.exempt_turnover, Decimal("900000"))
		self.assertEqual(result.registration_basis, Decimal("50000.00"))
		self.assertFalse(result.registration_required)

	def test_more_than_50000_and_rolling_boundary(self) -> None:
		result = rolling_vat_registration_status(
			[
				TurnoverEvent(date(2025, 9, 16), Decimal("90000"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2025, 9, 17), Decimal("50000.01"), VATTreatment.TAXABLE),
			],
			as_of=self.AS_OF,
		)
		self.assertEqual(result.window_start, date(2025, 9, 17))
		self.assertEqual(result.registration_basis, Decimal("50000.01"))
		self.assertTrue(result.registration_required)

	def test_outside_supported_rule_year_fails_closed(self) -> None:
		with self.assertRaises(UnsupportedRuleDateError):
			rolling_vat_registration_status([], as_of=date(2027, 1, 1))

	def test_backdated_sale_finds_later_crossing_date(self) -> None:
		crossings = vat_registration_threshold_crossings(
			[
				TurnoverEvent(date(2026, 1, 10), Decimal("30000"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2026, 5, 15), Decimal("6000"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2026, 6, 20), Decimal("15000"), VATTreatment.TAXABLE),
			]
		)
		self.assertEqual(len(crossings), 1)
		self.assertEqual(crossings[0].occurred_on, date(2026, 6, 20))
		self.assertEqual(crossings[0].registration_basis, Decimal("51000"))

	def test_credit_note_on_corrected_delivery_date_removes_false_crossing(self) -> None:
		crossings = vat_registration_threshold_crossings(
			[
				TurnoverEvent(date(2026, 1, 10), Decimal("30000"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2026, 6, 20), Decimal("25000"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2026, 6, 20), Decimal("-25000"), VATTreatment.TAXABLE),
			]
		)
		self.assertEqual(crossings, ())

	def test_window_includes_exactly_twelve_months_before_delivery(self) -> None:
		crossings = vat_registration_threshold_crossings(
			[
				TurnoverEvent(date(2025, 9, 17), Decimal("50000"), VATTreatment.TAXABLE),
				TurnoverEvent(date(2026, 9, 17), Decimal("0.01"), VATTreatment.TAXABLE),
			]
		)
		self.assertEqual(crossings[0].window_start, date(2025, 9, 17))
		self.assertEqual(crossings[0].registration_basis, Decimal("50000.01"))


class ReverseChargeTest(unittest.TestCase):
	PERIOD_END = date(2026, 6, 30)

	def test_unregistered_exactly_2000_has_no_liability(self) -> None:
		result = foreign_reverse_charge_status(
			[ForeignRemoteServicePurchase(date(2026, 4, 1), REVERSE_CHARGE_UNREGISTERED_THRESHOLD)],
			period_end=self.PERIOD_END,
			registered_for_vat=False,
		)
		self.assertFalse(result.liability_arises)
		self.assertFalse(result.separate_return_required)
		self.assertEqual(result.output_vat, Decimal("0.00"))

	def test_unregistered_purchase_over_2000_taxed_on_entire_basis(self) -> None:
		result = foreign_reverse_charge_status(
			[
				ForeignRemoteServicePurchase(date(2026, 4, 1), Decimal("1000.00")),
				ForeignRemoteServicePurchase(date(2026, 6, 30), Decimal("1000.01")),
				ForeignRemoteServicePurchase(date(2026, 3, 31), Decimal("999999")),
			],
			period_end=self.PERIOD_END,
			registered_for_vat=False,
		)
		self.assertEqual(result.relevant_purchase_basis, Decimal("2000.01"))
		self.assertTrue(result.liability_arises)
		self.assertTrue(result.separate_return_required)
		self.assertEqual(result.output_vat, Decimal("500.00"))

	def test_registered_business_has_no_amount_threshold_and_rounds_tax(self) -> None:
		result = foreign_reverse_charge_status(
			[ForeignRemoteServicePurchase(date(2026, 4, 1), Decimal("100.02"))],
			period_end=self.PERIOD_END,
			registered_for_vat=True,
		)
		self.assertTrue(result.liability_arises)
		self.assertFalse(result.separate_return_required)
		self.assertEqual(result.output_vat, Decimal("25.01"))


class AssetRulesTest(unittest.TestCase):
	AS_OF = date(2026, 5, 1)
	YEAR_END = date(2026, 12, 31)

	def test_cost_basis_includes_only_non_deductible_input_vat(self) -> None:
		self.assertEqual(
			asset_cost_basis(
				net_amount=Decimal("24000"), input_vat=Decimal("6000"), input_vat_deductible=False
			),
			ASSET_COST_THRESHOLD,
		)
		self.assertEqual(
			asset_cost_basis(
				net_amount=Decimal("24000"), input_vat=Decimal("6000"), input_vat_deductible=True
			),
			Decimal("24000"),
		)

	def test_exact_cost_and_lifetime_boundary_activates_asset(self) -> None:
		result = assess_asset(
			cost_basis=ASSET_COST_THRESHOLD,
			expected_useful_life_months=36,
			physical_asset=True,
			declines_in_value=True,
			predominantly_income_producing=True,
			as_of=self.AS_OF,
		)
		self.assertEqual(result.treatment, AssetTreatment.ACTIVATE_AND_DEPRECIATE)

	def test_below_either_asset_boundary_is_direct_expense(self) -> None:
		by_cost = assess_asset(
			cost_basis=Decimal("29999.99"),
			expected_useful_life_months=36,
			physical_asset=True,
			declines_in_value=True,
			predominantly_income_producing=True,
			as_of=self.AS_OF,
		)
		by_lifetime = assess_asset(
			cost_basis=ASSET_COST_THRESHOLD,
			expected_useful_life_months=35,
			physical_asset=True,
			declines_in_value=True,
			predominantly_income_producing=True,
			as_of=self.AS_OF,
		)
		self.assertEqual(by_cost.treatment, AssetTreatment.DIRECT_EXPENSE)
		self.assertEqual(by_lifetime.treatment, AssetTreatment.DIRECT_EXPENSE)

	def test_out_of_scope_asset_is_not_guessed(self) -> None:
		result = assess_asset(
			cost_basis=Decimal("50000"),
			expected_useful_life_months=60,
			physical_asset=False,
			declines_in_value=True,
			predominantly_income_producing=True,
			as_of=self.AS_OF,
		)
		self.assertEqual(result.treatment, AssetTreatment.OUTSIDE_SUPPORTED_SCOPE)

	def test_group_a_uses_30_percent_of_positive_pool_after_disposal(self) -> None:
		result = calculate_saldo_pool(
			group=SaldoGroup.A,
			year_end=self.YEAR_END,
			opening_balance=Decimal("100000"),
			acquisitions=Decimal("40000"),
			disposal_proceeds=Decimal("10000"),
		)
		self.assertEqual(result.balance_before_year_end_adjustments, Decimal("130000"))
		self.assertEqual(result.depreciation_deduction, Decimal("39000.00"))
		self.assertEqual(result.closing_balance, Decimal("91000.00"))

	def test_disposal_can_be_taken_directly_to_income_instead_of_reducing_pool(self) -> None:
		result = calculate_saldo_pool(
			group=SaldoGroup.A,
			year_end=self.YEAR_END,
			opening_balance=Decimal("100000"),
			disposal_proceeds=Decimal("10000"),
			disposal_proceeds_taken_to_income=Decimal("10000"),
		)
		self.assertEqual(result.balance_before_year_end_adjustments, Decimal("100000"))
		self.assertEqual(result.depreciation_deduction, Decimal("30000.00"))
		self.assertEqual(result.closing_balance, Decimal("70000.00"))

	def test_restsaldo_under_30000_can_be_fully_deducted_but_exactly_30000_cannot(self) -> None:
		small = calculate_saldo_pool(
			group=SaldoGroup.D,
			year_end=self.YEAR_END,
			opening_balance=Decimal("29999.99"),
			write_off_small_positive_balance=True,
		)
		self.assertEqual(small.depreciation_deduction, Decimal("29999.99"))
		self.assertEqual(small.closing_balance, Decimal("0.00"))
		with self.assertRaises(RuleValidationError):
			calculate_saldo_pool(
				group=SaldoGroup.A,
				year_end=self.YEAR_END,
				opening_balance=Decimal("30000"),
				write_off_small_positive_balance=True,
			)

	def test_negative_group_a_balance_uses_30_percent_and_small_negative_is_full_income(self) -> None:
		ordinary = calculate_saldo_pool(
			group=SaldoGroup.A,
			year_end=self.YEAR_END,
			opening_balance=Decimal("10000"),
			disposal_proceeds=Decimal("45000"),
		)
		small = calculate_saldo_pool(
			group=SaldoGroup.A,
			year_end=self.YEAR_END,
			opening_balance=Decimal("1"),
			disposal_proceeds=Decimal("30000"),
		)
		self.assertEqual(ordinary.balance_before_year_end_adjustments, Decimal("-35000"))
		self.assertEqual(ordinary.negative_balance_income, Decimal("10500.00"))
		self.assertEqual(ordinary.closing_balance, Decimal("-24500.00"))
		self.assertEqual(small.negative_balance_income, Decimal("29999"))
		self.assertEqual(small.closing_balance, Decimal("0"))

	def test_exact_negative_30000_is_not_small_balance_and_group_d_uses_20_percent(self) -> None:
		exact = calculate_saldo_pool(
			group=SaldoGroup.A,
			year_end=self.YEAR_END,
			opening_balance=Decimal("10000"),
			disposal_proceeds=Decimal("40000"),
		)
		group_d = calculate_saldo_pool(
			group=SaldoGroup.D,
			year_end=self.YEAR_END,
			opening_balance=Decimal("10000"),
			disposal_proceeds=Decimal("50000"),
		)
		self.assertEqual(exact.negative_balance_income, Decimal("9000.00"))
		self.assertEqual(exact.closing_balance, Decimal("-21000.00"))
		self.assertEqual(group_d.negative_balance_income, Decimal("8000.00"))
		self.assertEqual(group_d.closing_balance, Decimal("-32000.00"))

	def test_saldo_requires_2026_year_end(self) -> None:
		with self.assertRaises(UnsupportedRuleDateError):
			calculate_saldo_pool(
				group=SaldoGroup.A,
				year_end=date(2027, 12, 31),
				opening_balance=Decimal("1"),
			)


class MonetaryPrecisionTest(unittest.TestCase):
	def test_round_nok_uses_decimal_half_up_not_binary_float(self) -> None:
		self.assertEqual(round_nok(Decimal("25.005")), Decimal("25.01"))
		with self.assertRaises(RuleValidationError):
			round_nok(25.005)  # type: ignore[arg-type]


if __name__ == "__main__":
	unittest.main()
