# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import logging
import sys

from app.core.logging import JsonFormatter


def _record() -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, "value=%s", ("x",), None)


def test_json_formatter_renders_message_and_context() -> None:
    output = json.loads(JsonFormatter().format(_record()))

    assert output["message"] == "value=x"
    assert output["level"] == "INFO"
    assert output["logger"] == "test"
    assert output["request_id"] is None
    assert output["timestamp"].endswith("+00:00")


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        record = _record()
        record.exc_info = sys.exc_info()

    output = json.loads(JsonFormatter().format(record))

    assert "ValueError: bad" in output["exception"]
