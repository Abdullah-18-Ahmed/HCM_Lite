"""Allow-list logging (research D-11, constitution Art. XVI, FR-034).

Only the event name (the static log message) and the fields in :data:`ALLOWED_FIELDS` are
emitted. Format arguments, any other ``extra`` attribute and exception text are dropped, so
passwords, message text, document text and employee names cannot reach the logs. The event
name and every allowed field are validated; anything that does not match is replaced or dropped.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import IO

from hcm_lite.models.domain import AuditAction, AuditOutcome, Channel

ALLOWED_FIELDS: tuple[str, ...] = (
    "category", "correlation_id", "action", "outcome", "duration_ms", "channel",
)
INVALID_EVENT = "invalid_event"
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_ENUMS: dict[str, frozenset[str]] = {
    "outcome": frozenset(v.value for v in AuditOutcome),
    "channel": frozenset(v.value for v in Channel),
    "action": frozenset(v.value for v in AuditAction),
}

# Attributes every LogRecord has; anything else on a record came from ``extra``.
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


def _valid(key: str, value: object) -> bool:
    if key in _ENUMS:
        return isinstance(value, str) and value in _ENUMS[key]
    if key == "duration_ms":
        return type(value) is int and value >= 0
    return isinstance(value, str) and bool(_TOKEN_RE.match(value))


class AllowListFilter(logging.Filter):
    """Strip a record down to a validated event name plus validated allow-listed fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.args = ()  # never interpolate caller-supplied values into the message
        if not (isinstance(record.msg, str) and _EVENT_RE.match(record.msg)):
            record.msg = INVALID_EVENT
        for key in list(record.__dict__):
            if key in _STANDARD_ATTRS:
                continue
            if key not in ALLOWED_FIELDS or not _valid(key, record.__dict__[key]):
                delattr(record, key)  # also drops any caller-supplied exc_type_name
        if record.exc_info:
            exc_type = record.exc_info[0]
            record.exc_type_name = exc_type.__name__ if exc_type else "Exception"
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class AllowListFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        fields = [f"{k}={getattr(record, k)}" for k in ALLOWED_FIELDS if hasattr(record, k)]
        exc_name = getattr(record, "exc_type_name", None)
        if exc_name:
            fields.append(f"exception={exc_name}")
        return " ".join([line, *fields])


def configure_logging(
    level: int = logging.INFO,
    *,
    stream: IO[str] | None = None,
    logger: logging.Logger | None = None,
) -> logging.Handler:
    """Attach an allow-listed handler to ``logger`` (default: the ``hcm_lite`` logger).

    Idempotent: a handler previously attached by this function is replaced, never duplicated.
    """
    target = logger or logging.getLogger("hcm_lite")
    for existing in list(target.handlers):
        if getattr(existing, "_hcm_allow_list", False):
            target.removeHandler(existing)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler._hcm_allow_list = True  # type: ignore[attr-defined]
    handler.addFilter(AllowListFilter())
    handler.setFormatter(AllowListFormatter())
    target.addHandler(handler)
    target.setLevel(level)
    return handler
