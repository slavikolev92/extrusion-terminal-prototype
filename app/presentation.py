from __future__ import annotations

from typing import Any


NEXT_OPERATION_LABELS_BG = {
    "printing": "Печат",
    "rewinding / slitting": "Разролване",
    "confection": "Конфекция",
}


def next_operation_display(value: Any) -> str:
    text = "" if value is None else str(value)
    return NEXT_OPERATION_LABELS_BG.get(text.strip().casefold(), text)
