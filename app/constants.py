"""Shared workflow status constants for the extrusion pilot."""

STATUS_IMPORTED = "imported"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

CARD_STATUSES = (
    STATUS_IMPORTED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_PAUSED,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)

STATUS_LABELS = {
    STATUS_IMPORTED: "Импортирана",
    STATUS_PENDING: "Изчакване",
    STATUS_RUNNING: "Изработване",
    STATUS_PAUSED: "Паузирана",
    STATUS_COMPLETED: "Завършена",
    STATUS_CANCELLED: "Анулирана",
}

TIMING_REASON_LABELS = {
    "pause": "пауза",
    "finish": "приключване",
    "correction": "корекция",
}

ACTIVE_TERMINAL_STATUSES = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_PAUSED,
)

ARCHIVE_STATUSES = (
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)

TERMINAL_ARCHIVE_STATUSES = (
    STATUS_COMPLETED,
)

TERMINAL_VISIBLE_STATUSES = (
    *ACTIVE_TERMINAL_STATUSES,
    *TERMINAL_ARCHIVE_STATUSES,
)
