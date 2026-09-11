import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


ExactDecimal = tuple[int, int]
ZERO: ExactDecimal = (0, 0)
PHYSICAL_PALLET_WEIGHT_PATTERN = re.compile(
    r"(?P<sign>-?)(?P<whole>[0-9]+)(?:[.,](?P<fraction>[0-9]{1,2}))?"
)


class PalletSummaryDataError(ValueError):
    """A saved roll cannot be represented safely in a pallet summary."""


def parse_physical_pallet_weight(
    raw: str,
    pallet_number: int,
) -> tuple[int | None, str | None]:
    """Parse an optional physical-pallet weight into exact integer hundredths."""
    value = raw.strip()
    if not value:
        return None, None

    match = PHYSICAL_PALLET_WEIGHT_PATTERN.fullmatch(value)
    if match is None:
        return (
            None,
            f"Теглото за палет №{pallet_number} трябва да бъде число "
            "с най-много два десетични знака.",
        )

    if match.group("sign"):
        return (
            None,
            f"Теглото за палет №{pallet_number} трябва да бъде поне 0.01 кг.",
        )

    whole_text = match.group("whole")
    bounded_whole = whole_text.lstrip("0") or "0"
    if len(bounded_whole) > 3 or (
        len(bounded_whole) == 3 and bounded_whole > "100"
    ):
        return (
            None,
            f"Теглото за палет №{pallet_number} не може да бъде повече от 100.00 кг.",
        )

    whole = int(bounded_whole)
    fraction_hundredths = int((match.group("fraction") or "0").ljust(2, "0"))
    raw_hundredths = whole * 100 + fraction_hundredths
    if raw_hundredths > 10000:
        return (
            None,
            f"Теглото за палет №{pallet_number} не може да бъде повече от 100.00 кг.",
        )
    if raw_hundredths < 1:
        return (
            None,
            f"Теглото за палет №{pallet_number} трябва да бъде поне 0.01 кг.",
        )
    return raw_hundredths, None


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


def _pallet_derived_weight_display(value: ExactDecimal) -> str:
    return format(_parts_to_decimal(value).quantize(Decimal("0.01")), "f")


def _physical_pallet_weight(
    pallet_number: Any,
    weight_hundredths: Any,
) -> ExactDecimal:
    if (
        type(pallet_number) is not int
        or not 1 <= pallet_number <= 999
        or type(weight_hundredths) is not int
        or not 1 <= weight_hundredths <= 10000
    ):
        raise PalletSummaryDataError("Saved pallet weight is invalid.")
    return _normalize_exact((weight_hundredths, -2))


def _summary_row(
    *,
    roll_count: int,
    gross_weight: ExactDecimal,
    net_weight: ExactDecimal,
    pallet_weight: ExactDecimal | None,
    pallet_number: int | None = None,
    include_pallet: bool = False,
) -> dict[str, Any]:
    gross_decimal = _parts_to_decimal(gross_weight)
    net_decimal = _parts_to_decimal(net_weight)
    pallet_decimal = (
        _parts_to_decimal(pallet_weight) if pallet_weight is not None else None
    )
    gross_with_pallet = (
        _exact_add(gross_weight, pallet_weight)
        if pallet_weight is not None
        else None
    )
    row = {
        "roll_count": roll_count,
        "gross_without_pallet": gross_decimal,
        "net_weight": net_decimal,
        "pallet_weight": pallet_decimal,
        "gross_with_pallet": (
            _parts_to_decimal(gross_with_pallet)
            if gross_with_pallet is not None
            else None
        ),
        "gross_without_pallet_display": _weight_display(gross_weight),
        "net_display": _weight_display(net_weight),
        "pallet_weight_display": (
            _pallet_derived_weight_display(pallet_weight)
            if pallet_weight is not None
            else "-"
        ),
        "gross_with_pallet_display": (
            _pallet_derived_weight_display(gross_with_pallet)
            if gross_with_pallet is not None
            else "-"
        ),
    }
    if include_pallet:
        row.update({
            "pallet_number": pallet_number,
            "pallet_label": (
                str(pallet_number) if pallet_number is not None else "Без палет"
            ),
            "pallet_weight_input": (
                _pallet_derived_weight_display(pallet_weight)
                if pallet_weight is not None
                else ""
            ),
        })
    return row


def build_pallet_summary(
    roll_entries: Iterable[Mapping[str, Any]],
    pallet_weights: Mapping[int, int],
) -> dict[str, Any]:
    """Return an empty or ready pallet-summary view model.

    Raises PalletSummaryDataError when any entered roll has unusable saved data.
    Unexpected programming errors are intentionally not caught here.
    """
    validated_pallet_weights = {
        pallet_number: _physical_pallet_weight(pallet_number, weight_hundredths)
        for pallet_number, weight_hundredths in pallet_weights.items()
    }
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

    numbered = sorted(key for key in buckets if key is not None)
    orphaned = sorted(set(validated_pallet_weights) - set(numbered))
    if orphaned:
        raise PalletSummaryDataError(
            f"Saved pallet weight for unused pallet {orphaned[0]} is invalid."
        )

    missing_numbers = tuple(
        pallet_number
        for pallet_number in numbered
        if pallet_number not in validated_pallet_weights
    )
    unassigned_roll_count = buckets.get(None, (0, ZERO, ZERO))[0]
    weight_state = (
        "none" if not validated_pallet_weights
        else "complete" if not missing_numbers and unassigned_roll_count == 0
        else "partial"
    )

    if total_count == 0:
        return {
            "state": "empty",
            "weight_state": weight_state,
            "rows": [],
            "total": _summary_row(
                roll_count=0,
                gross_weight=ZERO,
                net_weight=ZERO,
                pallet_weight=None,
            ),
            "used_pallet_numbers": (),
            "missing_weight_pallet_numbers": (),
            "unassigned_roll_count": 0,
        }

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
            pallet_weight=validated_pallet_weights.get(pallet_number),
        ))

    total_pallet_weight: ExactDecimal | None = None
    if weight_state == "complete":
        total_pallet_weight = ZERO
        for pallet_weight in validated_pallet_weights.values():
            total_pallet_weight = _exact_add(total_pallet_weight, pallet_weight)

    return {
        "state": "ready",
        "weight_state": weight_state,
        "rows": rows,
        "total": _summary_row(
            roll_count=total_count,
            gross_weight=total_gross,
            net_weight=total_net,
            pallet_weight=total_pallet_weight,
        ),
        "used_pallet_numbers": tuple(numbered),
        "missing_weight_pallet_numbers": missing_numbers,
        "unassigned_roll_count": unassigned_roll_count,
    }
