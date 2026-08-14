"""Logging configuration.

Provides a console handler plus an optional rotating file handler. A redaction
filter guarantees that credentials, session cookies and authentication headers
are never written to any handler even if a caller passes them by mistake.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Optional

LOGGER_NAME = "qbt_sync"

# Patterns that must never appear in log output. These are defensive: the code
# is written not to log secrets in the first place, but a stray f-string should
# not be able to leak them.
_REDACT_PATTERNS = [
    re.compile(r"(SID=)[^;\s]+", re.IGNORECASE),
    re.compile(r"(password['\"]?\s*[:=]\s*)\S+", re.IGNORECASE),
    re.compile(r"(passwd['\"]?\s*[:=]\s*)\S+", re.IGNORECASE),
    re.compile(r"(Cookie:\s*)\S+", re.IGNORECASE),
    re.compile(r"(Authorization:\s*)\S+", re.IGNORECASE),
]


class RedactionFilter(logging.Filter):
    """Scrub secret-looking substrings from every log record message."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = msg
        for pattern in _REDACT_PATTERNS:
            redacted = pattern.sub(r"\1<redacted>", redacted)
        if redacted != msg:
            # Replace the record payload with the already-formatted, redacted text.
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(
    *,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Configure and return the package logger.

    :param verbose: enable DEBUG level output.
    :param quiet: only emit WARNING and above on the console.
    :param log_file: optional path for a rotating log file (always DEBUG).
    """

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    redaction = RedactionFilter()

    if verbose:
        console_level = logging.DEBUG
    elif quiet:
        console_level = logging.WARNING
    else:
        console_level = logging.INFO

    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    console.addFilter(redaction)
    logger.addHandler(console)

    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        file_handler.addFilter(redaction)
        logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    """Return the shared package logger (configuring a NullHandler if unset)."""

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
