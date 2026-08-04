from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


ExactDecimal = tuple[int, int]
ZERO: ExactDecimal = (0, 0)


class PalletSummaryDataError(ValueError):
    """A saved roll cannot be represented safely in a pallet summary."""


def _saved_weight(value: Any, *, field: str, index: int) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PalletSummaryDataError(
            f"Roll entry {index} has invalid {field}."
        ) from None
    if not parsed.is_finite() or parsed < 0:
        raise PalletSummaryDataError(
            f"Roll entry {index} has invalid {field}."
        )
    return parsed


def _saved_pallet(value: Any, *, index: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= 999:
        raise PalletSummaryDataError(
            f"Roll entry {index} has invalid pallet_number."
        )
    return value


def _normalize_exact(value: ExactDecimal) -> ExactDecimal:
    coefficient, exponent = value
    if coefficient == 0:
        return ZERO
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    return coefficient, exponent


def _exact_parts(value: Decimal) -> ExactDecimal:
    decimal_tuple = value.as_tuple()
    coefficient = 0
    for digit in decimal_tuple.digits:
        coefficient = coefficient * 10 + digit
    if decimal_tuple.sign:
        coefficient = -coefficient
    return _normalize_exact((coefficient, int(decimal_tuple.exponent)))


def _exact_add(left: ExactDecimal, right: ExactDecimal) -> ExactDecimal:
    left_coefficient, left_exponent = left
    right_coefficient, right_exponent = right
    if left_coefficient == 0:
        return right
    if right_coefficient == 0:
        return left

    common_exponent = min(left_exponent, right_exponent)
    coefficient = (
        left_coefficient * (10 ** (left_exponent - common_exponent))
        + right_coefficient * (10 ** (right_exponent - common_exponent))
    )
    return _normalize_exact((coefficient, common_exponent))


def _exact_subtract(left: ExactDecimal, right: ExactDecimal) -> ExactDecimal:
    coefficient, exponent = right
    return _exact_add(left, (-coefficient, exponent))


def _parts_to_decimal(value: ExactDecimal) -> Decimal:
    coefficient, exponent = value
    digits = Decimal(abs(coefficient)).as_tuple().digits
    return Decimal((int(coefficient < 0), digits, exponent))


def _weight_display(value: ExactDecimal) -> str:
    coefficient, exponent = value
    sign = -1 if coefficient < 0 else 1
    coefficient = abs(coefficient)
    discarded_places = -exponent - 1

    if discarded_places <= 0:
        rounded_tenths = coefficient * (10 ** -discarded_places)
    else:
        digits = Decimal(coefficient).as_tuple().digits
        if discarded_places > len(digits):
            rounded_tenths = 0
        elif discarded_places == len(digits):
            rounded_tenths = int(digits[0] >= 5)
        else:
            divisor = 10 ** discarded_places
            rounded_tenths, remainder = divmod(coefficient, divisor)
            if remainder * 2 >= divisor:
                rounded_tenths += 1

    displayed = _parts_to_decimal((sign * rounded_tenths, -1))
    return format(displayed, "f")


def _summary_row(
    *,
    roll_count: int,
    gross_weight: ExactDecimal,
    net_weight: ExactDecimal,
    pallet_number: int | None = None,
    include_pallet: bool = False,
) -> dict[str, Any]:
    gross_decimal = _parts_to_decimal(gross_weight)
    net_decimal = _parts_to_decimal(net_weight)
    row = {
        "roll_count": roll_count,
        "gross_weight": gross_decimal,
        "net_weight": net_decimal,
        "gross_display": _weight_display(gross_weight),
        "net_display": _weight_display(net_weight),
    }
    if include_pallet:
        row.update({
            "pallet_number": pallet_number,
            "pallet_label": (
                str(pallet_number) if pallet_number is not None else "Без палет"
            ),
        })
    return row


def build_terminal_pallet_summary(
    roll_entries: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return an empty or ready pallet-summary view model.

    Raises PalletSummaryDataError when any entered roll has unusable saved data.
    Unexpected programming errors are intentionally not caught here.
    """
    buckets: dict[int | None, tuple[int, ExactDecimal, ExactDecimal]] = {}
    total_count = 0
    total_gross = ZERO
    total_net = ZERO

    for index, entry in enumerate(roll_entries):
        gross_value = entry.get("gross_weight")
        if gross_value is None:
            continue

        gross_weight = _saved_weight(
            gross_value, field="gross_weight", index=index
        )
        tare_weight = _saved_weight(
            entry.get("tare_weight"), field="tare_weight", index=index
        )
        net_weight = _saved_weight(
            entry.get("net_weight"), field="net_weight", index=index
        )
        gross_exact = _exact_parts(gross_weight)
        tare_exact = _exact_parts(tare_weight)
        net_exact = _exact_parts(net_weight)
        if net_exact != _exact_subtract(gross_exact, tare_exact):
            raise PalletSummaryDataError(
                f"Roll entry {index} has invalid net_weight."
            )
        pallet_number = _saved_pallet(entry.get("pallet_number"), index=index)

        roll_count, gross_total, net_total = buckets.get(
            pallet_number, (0, ZERO, ZERO)
        )
        buckets[pallet_number] = (
            roll_count + 1,
            _exact_add(gross_total, gross_exact),
            _exact_add(net_total, net_exact),
        )
        total_count += 1
        total_gross = _exact_add(total_gross, gross_exact)
        total_net = _exact_add(total_net, net_exact)

    if total_count == 0:
        return {"state": "empty", "rows": [], "total": None}

    numbered = sorted(key for key in buckets if key is not None)
    ordered_keys: list[int | None] = [*numbered]
    if None in buckets:
        ordered_keys.append(None)

    rows = []
    for pallet_number in ordered_keys:
        roll_count, gross_weight, net_weight = buckets[pallet_number]
        rows.append(_summary_row(
            pallet_number=pallet_number,
            include_pallet=True,
            roll_count=roll_count,
            gross_weight=gross_weight,
            net_weight=net_weight,
        ))

    return {
        "state": "ready",
        "rows": rows,
        "total": _summary_row(
            roll_count=total_count,
            gross_weight=total_gross,
            net_weight=total_net,
        ),
    }
