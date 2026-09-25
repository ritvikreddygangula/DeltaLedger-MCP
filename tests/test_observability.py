import json
import logging

import pytest

from src.observability import get_logger, log_event, timed


def test_get_logger_returns_named_logger():
    logger = get_logger("some.module")
    assert logger.name == "some.module"


def test_log_event_emits_json_with_event_and_fields(caplog):
    logger = get_logger("test.log_event")
    with caplog.at_level(logging.INFO):
        log_event(logger, "thing_happened", ticker="AAPL", count=3)

    assert len(caplog.records) == 1
    # The record itself carries the raw fields dict for direct inspection,
    # independent of formatter wiring -- avoids coupling this test to
    # exactly which handler pytest's caplog attaches.
    fields = caplog.records[0].fields
    assert fields["event"] == "thing_happened"
    assert fields["ticker"] == "AAPL"
    assert fields["count"] == 3


def test_json_formatter_produces_valid_json_with_expected_shape():
    from src.observability import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname=__file__, lineno=1,
        msg="my_event", args=(), exc_info=None,
    )
    record.fields = {"event": "my_event", "ticker": "AAPL"}

    parsed = json.loads(formatter.format(record))

    assert parsed["message"] == "my_event"
    assert parsed["logger"] == "test.logger"
    assert parsed["level"] == "INFO"
    assert parsed["event"] == "my_event"
    assert parsed["ticker"] == "AAPL"
    assert "timestamp" in parsed


def test_timed_logs_duration_and_up_front_fields(caplog):
    logger = get_logger("test.timed")
    with caplog.at_level(logging.INFO):
        with timed(logger, "stage_ran", stage="align"):
            pass

    fields = caplog.records[0].fields
    assert fields["event"] == "stage_ran"
    assert fields["stage"] == "align"
    assert fields["duration_ms"] >= 0


def test_timed_merges_fields_added_during_the_block(caplog):
    logger = get_logger("test.timed2")
    with caplog.at_level(logging.INFO):
        with timed(logger, "stage_ran") as extra:
            extra["item_count"] = 4

    fields = caplog.records[0].fields
    assert fields["item_count"] == 4


def test_timed_still_logs_when_the_block_raises(caplog):
    logger = get_logger("test.timed3")
    with caplog.at_level(logging.INFO):
        with pytest.raises(ValueError):
            with timed(logger, "stage_ran"):
                raise ValueError("boom")

    assert len(caplog.records) == 1
    assert caplog.records[0].fields["event"] == "stage_ran"
