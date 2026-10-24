# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured JSON logging carrying the current request ID.

Never pass personal data (birth data, names, message text) to log calls.
"""

import json
import logging
from datetime import UTC, datetime
from typing import override

from app.core.config import LogLevel
from app.core.request_context import get_request_id


class JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: LogLevel) -> None:
    """Route all records through one stdout handler with the JSON formatter.

    :param level: Root log level.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.value)
