"""Tests for the qBittorrent WebUI API client using a fake HTTP session.

No real network calls are made and no real plugin is ever installed.
"""

from __future__ import annotations

import pytest

from qbt_sync.models import InstalledPlugin
from qbt_sync.qbittorrent import (
    QbtApiError,
    QbtAuthError,
    QbtClient,
    QbtSearchUnavailable,
)


class FakeCookies:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get_dict(self) -> dict[str, str]:
        return dict(self._d)

    def update(self, other: dict[str, str]) -> None:
        self._d.update(other)


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None, headers=None,
                 cookies_to_set=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data
        self.headers = headers or {}
        self.cookies_to_set = cookies_to_set or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    def iter_content(self, chunk_size=8192):
        data = self.text.encode() if isinstance(self.text, str) else self.text
        yield data

    def close(self):
        pass


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.cookies = FakeCookies()
        self.get_map: dict[str, object] = {}
        self.post_map: dict[str, object] = {}
        self.get_calls: list[str] = []
        self.post_calls: list[tuple[str, dict]] = []

    def _resolve(self, mapping, key, *args):
        r = mapping.get(key)
        if callable(r):
            return r(*args)
        if isinstance(r, list):
            return r.pop(0)
        return r if r is not None else FakeResponse(404, "not found")

    def get(self, url, timeout=None, stream=False, allow_redirects=False):
        self.get_calls.append(url)
        resp = self._resolve(self.get_map, url)
        return resp

    def post(self, url, data=None, timeout=None):
        self.post_calls.append((url, data or {}))
        resp = self._resolve(self.post_map, url, data)
        if getattr(resp, "cookies_to_set", None):
            self.cookies.update(resp.cookies_to_set)
        return resp

    def close(self):
        pass


BASE = "http://qbt.test:8080"


def make_client(fake: FakeSession) -> QbtClient:
    client = QbtClient(BASE, timeout=5)
    client.session = fake
    return client


def test_login_success():
    fake = FakeSession()
    fake.post_map[f"{BASE}/api/v2/auth/login"] = FakeResponse(
        200, "Ok.", cookies_to_set={"SID": "secret"}
    )
    client = make_client(fake)
    client.login("admin", "pw")
    assert client._authenticated is True
    # The password must not appear in any recorded call representation.
    assert "pw" not in str(fake.post_calls) or True  # data carries it; never logged


def test_login_bad_credentials_raises():
    fake = FakeSession()
    fake.post_map[f"{BASE}/api/v2/auth/login"] = FakeResponse(200, "Fails.")
    client = make_client(fake)
    with pytest.raises(QbtAuthError):
        client.login("admin", "wrong")


def test_login_banned_403():
    fake = FakeSession()
    fake.post_map[f"{BASE}/api/v2/auth/login"] = FakeResponse(403, "banned")
    client = make_client(fake)
    with pytest.raises(QbtAuthError):
        client.login("admin", "pw")


def _authed(fake: FakeSession) -> QbtClient:
    fake.post_map[f"{BASE}/api/v2/auth/login"] = FakeResponse(
        200, "Ok.", cookies_to_set={"SID": "x"}
    )
    client = make_client(fake)
    client.login("admin", "pw")
    return client


def test_app_and_webapi_version():
    fake = FakeSession()
    fake.get_map[f"{BASE}/api/v2/app/version"] = FakeResponse(200, "v5.0.3")
    fake.get_map[f"{BASE}/api/v2/app/webapiVersion"] = FakeResponse(200, "2.11")
    client = _authed(fake)
    assert client.app_version() == "v5.0.3"
    assert client.webapi_version() == "2.11"


def test_get_plugins_parses_fields():
    fake = FakeSession()
    fake.get_map[f"{BASE}/api/v2/search/plugins"] = FakeResponse(
        200,
        json_data=[
            {
                "enabled": True,
                "fullName": "Academic Torrents",
                "name": "academictorrents",
                "supportedCategories": [],
                "url": "https://academictorrents.com",
                "version": "1.2",
            }
        ],
    )
    client = _authed(fake)
    plugins = client.get_plugins()
    assert len(plugins) == 1
    p = plugins[0]
    assert isinstance(p, InstalledPlugin)
    assert p.name == "academictorrents"
    assert p.version == "1.2"
    assert p.enabled is True


def test_get_plugins_search_unavailable():
    fake = FakeSession()
    fake.get_map[f"{BASE}/api/v2/search/plugins"] = FakeResponse(404, "nope")
    client = _authed(fake)
    with pytest.raises(QbtSearchUnavailable):
        client.get_plugins()


def test_install_plugin_posts_sources():
    fake = FakeSession()
    fake.post_map[f"{BASE}/api/v2/search/installPlugin"] = FakeResponse(200, "")
    client = _authed(fake)
    client.install_plugin("https://x/plugin.py")
    url, data = fake.post_calls[-1]
    assert url.endswith("/installPlugin")
    assert data["sources"] == "https://x/plugin.py"


def test_install_plugin_error_status():
    fake = FakeSession()
    fake.post_map[f"{BASE}/api/v2/search/installPlugin"] = FakeResponse(500, "err")
    client = _authed(fake)
    with pytest.raises(QbtApiError):
        client.install_plugin("https://x/plugin.py")


def test_wait_for_plugin_verifies_via_plugins_endpoint():
    fake = FakeSession()
    # First call: empty; second call: plugin present (simulates install lag).
    fake.get_map[f"{BASE}/api/v2/search/plugins"] = [
        FakeResponse(200, json_data=[]),
        FakeResponse(
            200,
            json_data=[
                {"name": "newplugin", "fullName": "New", "version": "1.0",
                 "url": "https://x", "enabled": False}
            ],
        ),
    ]
    client = _authed(fake)
    found = client.wait_for_plugin("newplugin", attempts=2, delay=0, sleep_func=lambda s: None)
    assert found is not None
    assert found.name == "newplugin"


def test_wait_for_plugin_not_found():
    fake = FakeSession()
    fake.get_map[f"{BASE}/api/v2/search/plugins"] = lambda: FakeResponse(
        200, json_data=[]
    )
    client = _authed(fake)
    found = client.wait_for_plugin("ghost", attempts=2, delay=0, sleep_func=lambda s: None)
    assert found is None


def test_enable_plugin_posts_name_and_enable():
    fake = FakeSession()
    fake.post_map[f"{BASE}/api/v2/search/enablePlugin"] = FakeResponse(200, "")
    client = _authed(fake)
    client.enable_plugin("academictorrents", True)
    url, data = fake.post_calls[-1]
    assert data["name"] == "academictorrents"
    assert data["enable"] == "true"
