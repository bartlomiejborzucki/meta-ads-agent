"""Money conversion.

The most dangerous arithmetic in the project: a wrong minor-unit scale is a
100x budget error that looks plausible either way.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from meta_ads_agent.errors import CurrencyError
from meta_ads_agent.money import (
    META_OFFSET_OVERRIDES,
    Money,
    describe_change,
    minor_unit_digits,
    offset_for,
)


class TestCurrencyScale:
    @pytest.mark.parametrize(
        ("currency", "digits"),
        [
            ("USD", 2),
            ("PLN", 2),
            ("EUR", 2),
            ("GBP", 2),
            ("JPY", 0),
            ("KRW", 0),
            ("VND", 0),
            ("ISK", 0),
            ("CLP", 0),
            ("KWD", 3),
            ("BHD", 3),
            ("TND", 3),
            ("CLF", 4),
        ],
    )
    def test_iso_minor_unit_digits(self, currency: str, digits: int) -> None:
        assert minor_unit_digits(currency) == digits
        if currency not in META_OFFSET_OVERRIDES:
            assert offset_for(currency) == 10**digits

    @pytest.mark.parametrize(
        ("currency", "iso", "meta"),
        [
            # Meta counts these in whole units, not ISO's hundredths.
            ("COP", 100, 1),
            ("CRC", 100, 1),
            ("HUF", 100, 1),
            ("IDR", 100, 1),
            ("TWD", 100, 1),
            # And these in hundredths, not ISO's thousandths.
            ("BHD", 1000, 100),
            ("JOD", 1000, 100),
        ],
    )
    def test_meta_offsets_win_over_iso_where_they_differ(
        self, currency: str, iso: int, meta: int
    ) -> None:
        # With the ISO default, 10000 HUF/day went to Meta as 1000000: 100x.
        assert 10 ** minor_unit_digits(currency) == iso
        assert offset_for(currency) == meta
        assert Money.from_display("10000", currency).minor == 10000 * meta

    def test_case_and_whitespace_insensitive(self) -> None:
        assert offset_for(" pln ") == 100

    def test_unknown_currency_raises_rather_than_guessing(self) -> None:
        # Guessing "probably two decimals" here is how a budget ends up 100x off.
        with pytest.raises(CurrencyError, match="refusing to guess"):
            offset_for("XYZ")

    @pytest.mark.parametrize("bad", ["", "US", "USDX", "12A", "  "])
    def test_malformed_codes_rejected(self, bad: str) -> None:
        with pytest.raises(CurrencyError):
            offset_for(bad)


class TestConversion:
    @pytest.mark.parametrize("amount", ["Infinity", "-Infinity", "NaN", "sNaN", float("inf")])
    def test_non_finite_amounts_are_refused(self, amount: object) -> None:
        with pytest.raises(CurrencyError, match="Not a valid amount"):
            Money.from_display(amount, "PLN")  # type: ignore[arg-type]

    @pytest.mark.parametrize("minor", [70.9, "70.5", Decimal("0.1")])
    def test_fractional_minor_units_are_refused_not_truncated(self, minor: object) -> None:
        with pytest.raises(CurrencyError, match="must be whole"):
            Money.from_minor(minor, "PLN")  # type: ignore[arg-type]

    def test_a_whole_minor_amount_in_another_type_is_accepted(self) -> None:
        assert Money.from_minor("7000", "PLN").minor == 7000  # type: ignore[arg-type]
        assert Money.from_minor(7000.0, "PLN").minor == 7000  # type: ignore[arg-type]

    def test_an_explicit_zero_offset_is_refused_not_defaulted(self) -> None:
        with pytest.raises(CurrencyError, match="power of ten"):
            Money.from_display("70", "PLN", offset=0)
        with pytest.raises(CurrencyError, match="power of ten"):
            Money.from_minor(7000, "PLN", offset=0)

    def test_two_decimal_currency(self) -> None:
        money = Money.from_display("70", "PLN")
        assert money.minor == 7000
        assert money.display == Decimal("70.00")
        assert money.format() == "70.00 PLN"

    def test_zero_decimal_currency_is_not_multiplied(self) -> None:
        # The bug this test exists for: 5000 JPY is 5000 minor units, not 500000.
        money = Money.from_display(5000, "JPY")
        assert money.minor == 5000
        assert money.format() == "5000 JPY"

    def test_three_decimal_currency(self) -> None:
        money = Money.from_display("1.500", "KWD")
        assert money.minor == 1500

    def test_float_input_does_not_inherit_binary_error(self) -> None:
        assert Money.from_display(0.1, "USD").minor == 10
        assert Money.from_display(19.99, "USD").minor == 1999

    def test_round_trip(self) -> None:
        original = Money.from_display("123.45", "EUR")
        assert Money.from_minor(original.minor, "EUR").display == Decimal("123.45")

    def test_finer_than_smallest_unit_rejected(self) -> None:
        with pytest.raises(CurrencyError, match="finer than"):
            Money.from_display("10.005", "USD")

    def test_fractional_yen_rejected(self) -> None:
        with pytest.raises(CurrencyError, match="finer than"):
            Money.from_display("100.5", "JPY")

    def test_explicit_offset_overrides_iso_table(self) -> None:
        # Meta's currency_offset for the account outranks our table.
        money = Money.from_display("70", "PLN", offset=1)
        assert money.minor == 70

    def test_bool_is_not_an_amount(self) -> None:
        with pytest.raises(CurrencyError):
            Money.from_display(True, "USD")

    @pytest.mark.parametrize("bad_offset", [0, -100, 7, 3])
    def test_offset_must_be_a_power_of_ten(self, bad_offset: int) -> None:
        with pytest.raises(CurrencyError):
            Money(100, "USD", bad_offset)


class TestArithmetic:
    def test_add_and_subtract(self) -> None:
        a = Money.from_display("50", "PLN")
        b = Money.from_display("20", "PLN")
        assert (a + b).format() == "70.00 PLN"
        assert (a - b).format() == "30.00 PLN"

    def test_mixing_currencies_is_refused(self) -> None:
        with pytest.raises(CurrencyError, match="never converts"):
            Money.from_display("1", "USD") + Money.from_display("1", "EUR")

    def test_mismatched_offsets_for_same_currency_refused(self) -> None:
        with pytest.raises(CurrencyError, match="different offsets"):
            Money(100, "PLN", 100) + Money(100, "PLN", 1)

    def test_scaling_rounds_half_up_explicitly(self) -> None:
        assert Money.from_display("10", "USD").scaled("1.205").minor == 1205
        assert Money.from_display("1", "USD").scaled("1.005").minor == 101

    def test_pct_change(self) -> None:
        old = Money.from_display("50", "PLN")
        new = Money.from_display("70", "PLN")
        assert old.pct_change_to(new) == Decimal("40.0")

    def test_pct_change_from_zero_is_none_not_infinity(self) -> None:
        zero = Money.from_display("0.00", "PLN")
        assert zero.pct_change_to(Money.from_display("70", "PLN")) is None


class TestDescribeChange:
    def test_budget_increase_reports_both_values_and_currency(self) -> None:
        change = describe_change(Money.from_display("50", "PLN"), Money.from_display("70", "PLN"))
        assert change["currency"] == "PLN"
        assert change["from"] == "50.00 PLN"
        assert change["to"] == "70.00 PLN"
        assert change["delta"] == "20.00 PLN"
        assert change["pct_change"] == "+40.0%"
        assert change["direction"] == "increase"
        # Minor units travel alongside, so the caller never re-derives them.
        assert change["from_minor"] == 5000
        assert change["to_minor"] == 7000

    def test_decrease_and_unchanged(self) -> None:
        fifty = Money.from_display("50", "PLN")
        assert describe_change(fifty, Money.from_display("30", "PLN"))["direction"] == "decrease"
        assert describe_change(fifty, fifty)["direction"] == "unchanged"

    def test_zero_decimal_currency_change_is_not_inflated(self) -> None:
        change = describe_change(Money.from_display(5000, "JPY"), Money.from_display(7000, "JPY"))
        assert change["from"] == "5000 JPY"
        assert change["to_minor"] == 7000
