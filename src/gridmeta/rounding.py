"""Rounding of the record's shares (contract 4.4 to 4.6)."""

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

HUNDREDTH = Decimal("0.01")


def round_share(part: float, total: float) -> float:
    """part / total rounded half up to 2 decimals (0.125 -> 0.13)."""
    exact = Fraction(part) / Fraction(total)
    hundredths = Decimal(exact.numerator) / Decimal(exact.denominator)
    return float(hundredths.quantize(HUNDREDTH, rounding=ROUND_HALF_UP))


def largest_remainder_shares(weights: list[float]) -> list[float]:
    """Each weight's share of the total in hundredths, adding up to exactly 1.

    Each share is first rounded down; the hundredths left over go to the largest remainders,
    ties to the earlier weight.
    """
    # contract 4.5a: largest remainder keeps the 4.6 sum of 1 ± 0.01.
    total = sum(weights)
    exact = [Fraction(weight) * 100 / Fraction(total) for weight in weights]
    hundredths = [int(share) for share in exact]
    by_remainder = sorted(
        range(len(weights)), key=lambda index: (-(exact[index] - hundredths[index]), index)
    )
    for index in by_remainder[: 100 - sum(hundredths)]:
        hundredths[index] += 1
    return [count / 100 for count in hundredths]
