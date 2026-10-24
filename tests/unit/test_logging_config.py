"""T021: allow-list log filter. Logs never contain passwords, message text, document text or
employee names (Art. XVI, FR-034)."""

from __future__ import annotations

import io
import logging

import pytest

from hcm_lite.logging_config import ALLOWED_FIELDS, AllowListFilter, configure_logging


@pytest.fixture
def capture():
    stream = io.StringIO()
    logger = logging.getLogger("hcm_lite.test_logging")
    handler = configure_logging(stream=stream, logger=logger)
    yield logger, stream
    logger.removeHandler(handler)


def test_allowed_fields():
    assert set(ALLOWED_FIELDS) == {
        "category", "correlation_id", "action", "outcome", "duration_ms", "channel"}


def test_allowed_extras_kept(capture):
    logger, stream = capture
    logger.info("tool_call", extra={"category": "database", "correlation_id": "c-1",
                                    "duration_ms": 12, "channel": "chat"})
    out = stream.getvalue()
    for piece in ("tool_call", "category=database", "correlation_id=c-1", "duration_ms=12",
                  "channel=chat"):
        assert piece in out


def test_disallowed_extras_dropped(capture):
    logger, stream = capture
    logger.info("login", extra={"password": "hunter2", "full_name": "Jane Doe",
                                "message_text": "secret chat", "outcome": "ok"})
    out = stream.getvalue()
    assert "outcome=ok" in out
    for leaked in ("hunter2", "Jane Doe", "secret chat"):
        assert leaked not in out


def test_format_args_are_not_interpolated(capture):
    logger, stream = capture
    logger.info("user_said %s", "my password is hunter2")
    out = stream.getvalue()
    assert "hunter2" not in out
    assert "invalid_event" in out


def test_exception_text_not_logged_only_type(capture):
    logger, stream = capture
    try:
        raise RuntimeError("Jane Doe salary 9000")
    except RuntimeError:
        logger.exception("failure", extra={"category": "database"})
    out = stream.getvalue()
    assert "Jane Doe" not in out and "9000" not in out
    assert "RuntimeError" in out


def test_filter_is_a_logging_filter():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "evt %s", ("secret",), None)
    record.password = "hunter2"
    assert AllowListFilter().filter(record) is True
    assert record.args == ()
    assert not hasattr(record, "password")


@pytest.mark.parametrize("msg", ["Jane Doe logged in", "x" * 80, "Upper", 42, "a b"])
def test_event_name_must_be_a_short_token(capture, msg):
    logger, stream = capture
    logger.info(msg)
    out = stream.getvalue()
    assert "invalid_event" in out and "Jane" not in out


def test_valid_event_name_kept(capture):
    logger, stream = capture
    logger.info("auth.login_ok")
    assert "auth.login_ok" in stream.getvalue()


def test_field_values_validated(capture):
    logger, stream = capture
    logger.info("evt", extra={"outcome": "Jane Doe", "channel": "smoke", "action": "free text",
                              "duration_ms": "12 secret", "correlation_id": "has space x",
                              "category": "x" * 100})
    out = stream.getvalue()
    for k in ALLOWED_FIELDS:
        assert f"{k}=" not in out
    assert "Jane" not in out and "secret" not in out


def test_valid_enum_fields_kept(capture):
    logger, stream = capture
    logger.info("evt", extra={"outcome": "denied", "channel": "api", "action": "logout",
                              "duration_ms": 5})
    out = stream.getvalue()
    for piece in ("outcome=denied", "channel=api", "action=logout", "duration_ms=5"):
        assert piece in out


def test_bool_duration_rejected(capture):
    logger, stream = capture
    logger.info("evt", extra={"duration_ms": True})
    assert "duration_ms=" not in stream.getvalue()


def test_caller_supplied_exc_type_name_dropped(capture):
    logger, stream = capture
    logger.info("evt", extra={"exc_type_name": "Jane Doe"})
    out = stream.getvalue()
    assert "Jane" not in out and "exception=" not in out


def test_configure_logging_idempotent():
    logger = logging.getLogger("hcm_lite.test_idem")
    try:
        configure_logging(stream=io.StringIO(), logger=logger)
        configure_logging(stream=io.StringIO(), logger=logger)
        assert len(logger.handlers) == 1
    finally:
        for h in list(logger.handlers):
            logger.removeHandler(h)
