"""Money. One module, one representation, no scattered ``* 100``.

Meta's ads interfaces express budgets and bids in **minor currency units** of
the ad account's currency. A "70" in an API call is 70 minor units - 0.70 in a
two-decimal currency, 70 in a zero-decimal one. Getting that wrong is a 100x
budget error, and it fails silently because both numbers look plausible.

Three rules this module exists to enforce:

1. A number never travels without its currency and scale. :class:`Money` is the
   only currency-carrying type in the codebase.
2. An unknown currency raises. It never falls back to "probably two decimals".
3. Meta's own ``currency_offset`` for the account outranks our table. Read the
   account first; pass the offset in.

The table below is ISO 4217 minor-unit digits, which is verifiable and correct
for the overwhelming majority of cases. It is a *default*, used when the caller
has no account data to hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from meta_ads_agent.errors import CurrencyError

# ISO 4217 minor-unit digits for currencies that are not the 2-digit default.
# Anything absent from both maps is assumed 2 only if it is in KNOWN_2, so an
# unrecognised code raises instead of being guessed at.
_ZERO_DECIMAL = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "ISK",
        "JPY",
        "KMF",
        "KRW",
        "PYG",
        "RWF",
        "UGX",
        "UYI",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)
_THREE_DECIMAL = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})
_FOUR_DECIMAL = frozenset({"CLF", "UYW"})

# Currencies Meta commonly supports that use the 2-digit default. Listing them
# explicitly is what makes an unknown code an error rather than a silent guess.
_TWO_DECIMAL = frozenset(
    {
        "AED",
        "ARS",
        "AUD",
        "BDT",
        "BGN",
        "BOB",
        "BRL",
        "CAD",
        "CHF",
        "CNY",
        "COP",
        "CRC",
        "CZK",
        "DKK",
        "DZD",
        "EGP",
        "EUR",
        "GBP",
        "GTQ",
        "HKD",
        "HNL",
        "HRK",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "KES",
        "LKR",
        "MAD",
        "MOP",
        "MXN",
        "MYR",
        "NGN",
        "NIO",
        "NOK",
        "NZD",
        "PEN",
        "PHP",
        "PKR",
        "PLN",
        "QAR",
        "RON",
        "RSD",
        "RUB",
        "SAR",
        "SEK",
        "SGD",
        "THB",
        "TRY",
        "TWD",
        "UAH",
        "USD",
        "UYU",
        "VES",
        "VEF",
        "ZAR",
    }
)


def minor_unit_digits(currency: str) -> int:
    """Number of decimal digits in *currency* per ISO 4217.

    Raises :class:`CurrencyError` for an unrecognised code. That is deliberate:
    a wrong scale is a 100x error, and an exception is cheaper than a wire
    transfer.
    """
    code = _normalise(currency)
    if code in _ZERO_DECIMAL:
        return 0
    if code in _THREE_DECIMAL:
        return 3
    if code in _FOUR_DECIMAL:
        return 4
    if code in _TWO_DECIMAL:
        return 2
    raise CurrencyError(
        f"Unknown currency {code!r}: refusing to guess its minor-unit scale. "
        "Read the ad account's currency and offset from Meta and pass "
        "offset= explicitly, or add the code to meta_ads_agent.money."
    )


def offset_for(currency: str) -> int:
    """Multiplier between display amount and minor units, e.g. 100 for USD.

    Meta calls this the currency offset. If the account object gives you one,
    prefer it over this function - see the module docstring.
    """
    return int(10 ** minor_unit_digits(currency))


def _normalise(currency: str) -> str:
    code = (currency or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise CurrencyError(f"Not an ISO 4217 currency code: {currency!r}")
    return code


def _to_decimal(value: Decimal | int | str | float) -> Decimal:
    """Coerce to Decimal without inheriting binary float error.

    Floats go through ``str`` so ``0.1`` means 0.1 and not
    0.1000000000000000055511151231257827.
    """
    try:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool):  # bool is an int; almost certainly a bug
            raise CurrencyError(f"Refusing to treat {value!r} as an amount")
        if isinstance(value, float):
            return Decimal(str(value))
        return Decimal(value)
    except (InvalidOperation, ArithmeticError, ValueError) as exc:
        raise CurrencyError(f"Not a valid amount: {value!r}") from exc


def _is_power_of_ten(value: object) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return False
    while value % 10 == 0:
        value //= 10
    return value == 1


@dataclass(frozen=True, slots=True)
class Money:
    """An exact amount of one currency, stored in minor units.

    ``minor`` is what goes on the wire. ``display`` is what a human reads.
    Never format ``minor`` for a user and never send ``display`` to Meta.
    """

    minor: int
    currency: str
    offset: int

    def __post_init__(self) -> None:
        if not isinstance(self.minor, int) or isinstance(self.minor, bool):
            raise CurrencyError(f"minor must be an int, got {type(self.minor).__name__}")
        if not _is_power_of_ten(self.offset):
            raise CurrencyError(f"Currency offset must be a power of ten, got {self.offset!r}")
        object.__setattr__(self, "currency", _normalise(self.currency))

    # -- constructors ------------------------------------------------------
    @classmethod
    def from_minor(cls, minor: int, currency: str, *, offset: int | None = None) -> Money:
        """Build from a wire value, e.g. a budget read back from Meta."""
        code = _normalise(currency)
        return cls(minor=int(minor), currency=code, offset=offset or offset_for(code))

    @classmethod
    def from_display(
        cls,
        amount: Decimal | int | str | float,
        currency: str,
        *,
        offset: int | None = None,
    ) -> Money:
        """Build from a human amount, e.g. the "70" in "70 PLN per day".

        Rejects an amount with more precision than the currency can express:
        ``10.005 USD`` is a typo or a unit confusion, not a half-cent.
        """
        code = _normalise(currency)
        scale = offset or offset_for(code)
        dec = _to_decimal(amount)
        scaled = dec * scale
        if scaled != scaled.to_integral_value():
            raise CurrencyError(
                f"{dec} {code} is finer than the currency's smallest unit "
                f"(1/{scale}). Round it, or check whether this number is "
                "already in minor units."
            )
        return cls(minor=int(scaled), currency=code, offset=scale)

    # -- accessors ---------------------------------------------------------
    @property
    def display(self) -> Decimal:
        """The amount a human reads. Never send this to Meta."""
        return (Decimal(self.minor) / Decimal(self.offset)).quantize(
            Decimal(1).scaleb(-self._digits), rounding=ROUND_HALF_UP
        )

    @property
    def _digits(self) -> int:
        digits = 0
        scale = self.offset
        while scale >= 10:
            scale //= 10
            digits += 1
        return digits

    def format(self) -> str:
        """Human-readable, currency-suffixed, unambiguous: ``70.00 PLN``."""
        return f"{self.display} {self.currency}"

    def __str__(self) -> str:
        return self.format()

    # -- arithmetic --------------------------------------------------------
    def _check_same(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyError(
                f"Cannot combine {self.currency} and {other.currency}. "
                "This project never converts between currencies."
            )
        if self.offset != other.offset:
            raise CurrencyError(
                f"Same currency {self.currency} with different offsets "
                f"({self.offset} vs {other.offset}). One of them is wrong."
            )

    def __add__(self, other: Money) -> Money:
        self._check_same(other)
        return Money(self.minor + other.minor, self.currency, self.offset)

    def __sub__(self, other: Money) -> Money:
        self._check_same(other)
        return Money(self.minor - other.minor, self.currency, self.offset)

    def scaled(self, factor: Decimal | int | str | float) -> Money:
        """Multiply, rounding half-up to the nearest minor unit.

        Rounding is explicit because a budget must land on a whole minor unit
        and the direction should never be a surprise.
        """
        product = Decimal(self.minor) * _to_decimal(factor)
        return Money(
            int(product.quantize(Decimal(1), rounding=ROUND_HALF_UP)),
            self.currency,
            self.offset,
        )

    def pct_change_to(self, other: Money) -> Decimal | None:
        """Percentage change from ``self`` to ``other``, or None from zero.

        Returns None rather than infinity when the baseline is zero: "up from
        nothing" has no percentage, and pretending otherwise produces the
        nonsense percentages that show up in automated ad reports.
        """
        self._check_same(other)
        if self.minor == 0:
            return None
        delta = Decimal(other.minor - self.minor) / Decimal(self.minor) * 100
        return delta.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def describe_change(old: Money, new: Money) -> dict[str, object]:
    """Render a budget change for an approval prompt.

    Every spend-affecting change must be shown with its old value, its new
    value, and the currency - read from Meta, never assumed. This produces that
    structure so no caller has to remember the shape.
    """
    old._check_same(new)
    pct = old.pct_change_to(new)
    return {
        "currency": old.currency,
        "from": old.format(),
        "to": new.format(),
        "from_minor": old.minor,
        "to_minor": new.minor,
        "delta": (new - old).format(),
        "pct_change": None if pct is None else f"{pct:+}%",
        "direction": "increase"
        if new.minor > old.minor
        else "decrease"
        if new.minor < old.minor
        else "unchanged",
    }
