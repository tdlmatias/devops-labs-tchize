"""qBittorrent WebUI API client.

Wraps the subset of the ``/api/v2`` API needed for search-plugin management.
A single persistent :class:`requests.Session` carries the ``SID`` auth cookie.
The correct ``Referer``/``Origin`` headers (which qBittorrent requires for
non-GET requests) are set on the session.

Only search-plugin endpoints are used. This client never searches, downloads
torrents, or touches torrent jobs.
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlparse

import requests

from .httpclient import DownloadError, get_with_retries
from .logging_config import get_logger
from .models import InstalledPlugin

logger = get_logger()


class QbtError(Exception):
    """Base error for qBittorrent client problems."""


class QbtConnectionError(QbtError):
    """Cannot reach qBittorrent (exit code 3)."""


class QbtAuthError(QbtError):
    """Authentication failed or was banned (exit code 3)."""


class QbtApiError(QbtError):
    """qBittorrent returned an unexpected API response."""


class QbtSearchUnavailable(QbtError):
    """The search subsystem/endpoint is not available on this instance."""


class QbtClient:
    """Minimal, defensive client for the qBittorrent WebUI search API."""

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        parsed = urlparse(self.base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        # qBittorrent validates Referer/Origin against its own host.
        self.session.headers.update(
            {
                "Referer": self.base_url,
                "Origin": origin,
                "User-Agent": "qbt-plugin-sync/1.0",
            }
        )
        self._authenticated = False

    # ----- context management ------------------------------------------- #
    def __enter__(self) -> "QbtClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.session.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    # ----- authentication ----------------------------------------------- #
    def login(self, username: str, password: str) -> None:
        """Authenticate; stores the SID cookie in the session on success.

        Auth is intentionally *not* retried (a duplicate failed login can push a
        client toward qBittorrent's ban threshold).
        """

        try:
            response = self.session.post(
                self._url("/api/v2/auth/login"),
                data={"username": username, "password": password},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise QbtConnectionError(
                f"Could not connect to qBittorrent at {self.base_url}: {exc}"
            ) from exc

        if response.status_code == 403:
            raise QbtAuthError(
                "Login rejected with HTTP 403 — the client IP may be banned "
                "for too many failed attempts."
            )
        if response.status_code != 200:
            raise QbtAuthError(
                f"Unexpected login status {response.status_code}."
            )

        body = (response.text or "").strip()
        if body.lower() != "ok.":
            # qBittorrent returns 'Fails.' with HTTP 200 on bad credentials.
            raise QbtAuthError("Authentication failed: invalid username or password.")

        if "SID" not in self.session.cookies.get_dict():
            raise QbtAuthError("Login succeeded but no SID cookie was issued.")

        self._authenticated = True
        logger.info("Authenticated with qBittorrent WebUI.")

    def _require_auth(self) -> None:
        if not self._authenticated:
            raise QbtAuthError("Client is not authenticated; call login() first.")

    # ----- read-only queries (idempotent GET, with retries) ------------- #
    def _get_text(self, path: str) -> str:
        self._require_auth()
        try:
            response = get_with_retries(
                self.session, self._url(path), timeout=self.timeout
            )
        except DownloadError as exc:
            raise QbtConnectionError(f"GET {path} failed: {exc}") from exc
        if response.status_code == 403:
            raise QbtAuthError(f"GET {path} forbidden (session expired?).")
        if response.status_code == 404:
            raise QbtSearchUnavailable(f"Endpoint {path} not found on this instance.")
        if response.status_code != 200:
            raise QbtApiError(f"GET {path} returned HTTP {response.status_code}.")
        return response.text

    def app_version(self) -> str:
        return self._get_text("/api/v2/app/version").strip()

    def webapi_version(self) -> str:
        return self._get_text("/api/v2/app/webapiVersion").strip()

    def get_plugins(self) -> list[InstalledPlugin]:
        """Return the installed search plugins."""

        self._require_auth()
        try:
            response = get_with_retries(
                self.session, self._url("/api/v2/search/plugins"), timeout=self.timeout
            )
        except DownloadError as exc:
            raise QbtConnectionError(f"Listing plugins failed: {exc}") from exc
        if response.status_code == 404:
            raise QbtSearchUnavailable(
                "The search plugins endpoint is unavailable; is the Search "
                "engine enabled in qBittorrent?"
            )
        if response.status_code == 403:
            raise QbtAuthError("Session forbidden while listing plugins.")
        if response.status_code != 200:
            raise QbtApiError(
                f"GET /search/plugins returned HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise QbtApiError("Search plugins response was not valid JSON.") from exc

        if not isinstance(payload, list):
            raise QbtApiError(
                f"Expected a JSON array of plugins, got {type(payload).__name__}."
            )

        plugins: list[InstalledPlugin] = []
        for item in payload:
            plugins.append(
                InstalledPlugin(
                    name=str(item.get("name", "")),
                    full_name=str(item.get("fullName", "")),
                    version=(str(item["version"]) if item.get("version") else None),
                    site_url=item.get("url"),
                    enabled=bool(item.get("enabled", False)),
                )
            )
        return plugins

    # ----- mutations (never auto-retried) ------------------------------- #
    def install_plugin(self, source: str) -> None:
        """Install a single plugin from ``source`` (installed one at a time).

        HTTP 200 here is necessary but not sufficient proof of success; callers
        MUST re-query :meth:`get_plugins` to verify.
        """

        self._require_auth()
        try:
            response = self.session.post(
                self._url("/api/v2/search/installPlugin"),
                data={"sources": source},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise QbtConnectionError(f"installPlugin request failed: {exc}") from exc
        if response.status_code != 200:
            raise QbtApiError(
                f"installPlugin returned HTTP {response.status_code}."
            )

    def update_plugins(self) -> None:
        """Ask qBittorrent to update all installed plugins."""

        self._require_auth()
        try:
            response = self.session.post(
                self._url("/api/v2/search/updatePlugins"), timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise QbtConnectionError(f"updatePlugins request failed: {exc}") from exc
        if response.status_code != 200:
            raise QbtApiError(
                f"updatePlugins returned HTTP {response.status_code}."
            )

    def enable_plugin(self, name: str, enable: bool = True) -> None:
        """Enable or disable an installed plugin by name."""

        self._require_auth()
        try:
            response = self.session.post(
                self._url("/api/v2/search/enablePlugin"),
                data={"name": name, "enable": "true" if enable else "false"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise QbtConnectionError(f"enablePlugin request failed: {exc}") from exc
        if response.status_code != 200:
            raise QbtApiError(
                f"enablePlugin returned HTTP {response.status_code}."
            )

    # ----- convenience --------------------------------------------------- #
    def wait_for_plugin(
        self, name: str, *, attempts: int = 3, delay: float = 1.0, sleep_func=time.sleep
    ) -> Optional[InstalledPlugin]:
        """Poll get_plugins() a few times for ``name`` to appear (post-install)."""

        for attempt in range(attempts):
            plugins = {p.name: p for p in self.get_plugins()}
            if name in plugins:
                return plugins[name]
            if attempt < attempts - 1:
                sleep_func(delay)
        return None
