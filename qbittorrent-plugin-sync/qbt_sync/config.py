"""Configuration handling.

Configuration is resolved with the following precedence (highest first):

1. Command-line arguments (``--url``, ``--username``, ``--timeout``)
2. Environment variables (``QBT_URL``, ``QBT_USERNAME``, ``QBT_PASSWORD``)
3. Built-in defaults

The password is intentionally handled separately: it is read from the
environment, or prompted interactively with :func:`getpass.getpass`. It is
never accepted as a command-line argument (so it cannot leak into shell
history or a process listing) and is never logged.
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_URL = "http://localhost:8080"
DEFAULT_USERNAME = "admin"
DEFAULT_TIMEOUT = 30.0

# Canonical catalogue source (canonical MediaWiki repository file, not rendered HTML).
DEFAULT_CATALOGUE_URL = (
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/"
    "master/wiki/Unofficial-search-plugins.mediawiki"
)


class ConfigError(Exception):
    """Raised when configuration cannot be resolved (maps to exit code 2)."""


@dataclass
class Config:
    """Resolved runtime configuration (never serialised into reports)."""

    url: str
    username: str
    password: str
    timeout: float
    catalogue_url: str = DEFAULT_CATALOGUE_URL

    def __repr__(self) -> str:  # pragma: no cover - trivial
        # Guarantee the password never appears in a repr / traceback.
        return (
            f"Config(url={self.url!r}, username={self.username!r}, "
            f"password=<redacted>, timeout={self.timeout!r})"
        )


def _env(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is not None:
        value = value.strip()
    return value or None


def resolve_password(
    *,
    prompt: bool = True,
    getpass_func=getpass.getpass,
) -> str:
    """Resolve the qBittorrent password.

    Order: ``QBT_PASSWORD`` environment variable, then an interactive prompt.

    :param prompt: if ``False`` and the env var is unset, raise ConfigError
        instead of prompting (used for non-interactive / test contexts).
    """

    password = _env("QBT_PASSWORD")
    if password:
        return password
    if not prompt:
        raise ConfigError(
            "No password supplied. Set QBT_PASSWORD or run interactively."
        )
    try:
        password = getpass_func("qBittorrent password: ")
    except (EOFError, KeyboardInterrupt) as exc:  # pragma: no cover - interactive
        raise ConfigError("Password entry aborted.") from exc
    if not password:
        raise ConfigError("An empty password is not permitted.")
    return password


def load_config(
    *,
    url: Optional[str] = None,
    username: Optional[str] = None,
    timeout: Optional[float] = None,
    catalogue_url: Optional[str] = None,
    password: Optional[str] = None,
    prompt_password: bool = True,
    getpass_func=getpass.getpass,
) -> Config:
    """Build a :class:`Config` from CLI overrides + environment + defaults.

    ``password`` is normally left as ``None`` so it is resolved via
    :func:`resolve_password`; tests may inject it directly.
    """

    resolved_url = (url or _env("QBT_URL") or DEFAULT_URL).rstrip("/")
    if not resolved_url:
        raise ConfigError("qBittorrent URL must not be empty.")

    resolved_username = username or _env("QBT_USERNAME") or DEFAULT_USERNAME

    if timeout is None:
        env_timeout = _env("QBT_TIMEOUT")
        timeout = float(env_timeout) if env_timeout else DEFAULT_TIMEOUT
    if timeout <= 0:
        raise ConfigError("Timeout must be a positive number of seconds.")

    if password is None:
        password = resolve_password(prompt=prompt_password, getpass_func=getpass_func)

    return Config(
        url=resolved_url,
        username=resolved_username,
        password=password,
        timeout=float(timeout),
        catalogue_url=catalogue_url or DEFAULT_CATALOGUE_URL,
    )
