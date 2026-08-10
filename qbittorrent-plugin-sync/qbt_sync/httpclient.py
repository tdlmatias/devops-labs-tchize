"""Shared HTTP helpers for GET requests against untrusted external hosts.

Used for fetching the catalogue and downloading candidate plugin source files.
Provides conservative retry-with-backoff for idempotent GETs and manual,
validated redirect following so that a redirect can never land on a
private/internal address.
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urljoin

import requests

from .logging_config import get_logger
from .security import UrlValidationError, validate_url

logger = get_logger()

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE = 1.0  # seconds
MAX_REDIRECTS = 5
_RETRYABLE_STATUS = {500, 502, 503, 504}


class DownloadError(Exception):
    """Raised when a resource cannot be safely downloaded."""


def get_with_retries(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    stream: bool = False,
    sleep_func=time.sleep,
) -> requests.Response:
    """Perform a GET with conservative retries on network errors and 5xx.

    Non-retryable responses (e.g. 404, 403) are returned to the caller so it can
    decide what to do. Authentication and mutation requests must NOT use this.
    """

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(
                url, timeout=timeout, stream=stream, allow_redirects=False
            )
        except requests.RequestException as exc:
            last_exc = exc
            logger.debug("GET %s failed (attempt %d/%d): %s", url, attempt, max_attempts, exc)
        else:
            if response.status_code in _RETRYABLE_STATUS and attempt < max_attempts:
                logger.debug(
                    "GET %s returned %d (attempt %d/%d), retrying",
                    url,
                    response.status_code,
                    attempt,
                    max_attempts,
                )
            else:
                return response
        if attempt < max_attempts:
            sleep_func(backoff_base * (2 ** (attempt - 1)))

    raise DownloadError(f"GET {url} failed after {max_attempts} attempts: {last_exc}")


def fetch_text(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    max_bytes: Optional[int] = None,
    sleep_func=time.sleep,
) -> str:
    """Fetch a text resource (e.g. the catalogue), following safe redirects."""

    data = fetch_bytes(
        session, url, timeout=timeout, max_bytes=max_bytes, sleep_func=sleep_func,
        validate=False,
    )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def fetch_bytes(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    max_bytes: Optional[int] = None,
    validate: bool = True,
    require_https: bool = True,
    check_dns: bool = True,
    sleep_func=time.sleep,
) -> bytes:
    """Download a resource as bytes, following redirects with per-hop validation.

    :param validate: when True, validate the initial URL and every redirect hop
        with :func:`qbt_sync.security.validate_url` (used for plugin downloads).
    :param max_bytes: hard cap enforced both via Content-Length and streamed
        byte count.
    """

    current = url
    for hop in range(MAX_REDIRECTS + 1):
        if validate:
            validate_url(current, require_https=require_https, check_dns=check_dns)

        response = get_with_retries(
            session, current, timeout=timeout, stream=True, sleep_func=sleep_func
        )

        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise DownloadError(f"Redirect from {current} had no Location header.")
            current = urljoin(current, location)
            logger.debug("Following redirect -> %s", current)
            continue

        if response.status_code != 200:
            response.close()
            raise DownloadError(
                f"GET {current} returned HTTP {response.status_code}."
            )

        # Enforce Content-Length up-front when advertised.
        if max_bytes is not None:
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    if int(length) > max_bytes:
                        response.close()
                        raise DownloadError(
                            f"Resource advertises {length} bytes (> {max_bytes})."
                        )
                except ValueError:
                    pass

        chunks = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                chunks.extend(chunk)
                if max_bytes is not None and len(chunks) > max_bytes:
                    raise DownloadError(
                        f"Resource exceeds maximum size of {max_bytes} bytes."
                    )
        finally:
            response.close()
        return bytes(chunks)

    raise DownloadError(f"Too many redirects while fetching {url}.")
