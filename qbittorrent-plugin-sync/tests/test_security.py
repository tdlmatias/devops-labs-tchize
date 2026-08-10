"""Tests for URL validation and the static plugin security scanner."""

from __future__ import annotations

import pytest

from qbt_sync.security import (
    MAX_PLUGIN_SIZE,
    UrlValidationError,
    inspect_source,
    sha256_hex,
    validate_url,
)

SAFE_PLUGIN = b"""
import re
from novaprinter import prettyPrinter

class myplugin(object):
    url = 'https://example.com'
    name = 'Example'

    def search(self, what, cat='all'):
        # a harmless qBittorrent search plugin
        pass
"""

DANGEROUS_PLUGIN = b"""
import subprocess
import os

def search(what):
    os.system('rm -rf /')
    subprocess.call(['curl', 'evil'])
    eval(what)
"""


# --------------------------- URL validation --------------------------------- #
def test_validate_url_accepts_https_public():
    url = "https://raw.githubusercontent.com/x/y/master/plugin.py"
    assert validate_url(url, check_dns=False) == url


def test_validate_url_rejects_http_when_https_required():
    with pytest.raises(UrlValidationError):
        validate_url("http://example.com/plugin.py", check_dns=False)


def test_validate_url_rejects_file_scheme():
    with pytest.raises(UrlValidationError):
        validate_url("file:///etc/passwd", check_dns=False)


def test_validate_url_rejects_localhost():
    with pytest.raises(UrlValidationError):
        validate_url("https://localhost/plugin.py", check_dns=False)
    with pytest.raises(UrlValidationError):
        validate_url("https://127.0.0.1/plugin.py", check_dns=False)


def test_validate_url_rejects_private_ip():
    with pytest.raises(UrlValidationError):
        validate_url("https://192.168.1.10/plugin.py", check_dns=True)
    with pytest.raises(UrlValidationError):
        validate_url("https://10.0.0.5/plugin.py", check_dns=True)


def test_validate_url_rejects_malformed():
    with pytest.raises(UrlValidationError):
        validate_url("not a url", check_dns=False)
    with pytest.raises(UrlValidationError):
        validate_url("https://", check_dns=False)


# --------------------------- source inspection ------------------------------ #
def test_safe_plugin_is_low_risk():
    report = inspect_source(SAFE_PLUGIN)
    assert report.syntax_valid
    assert report.risk in ("LOW",)
    assert report.sha256 == sha256_hex(SAFE_PLUGIN)
    assert report.error is None


def test_dangerous_plugin_is_high_risk():
    report = inspect_source(DANGEROUS_PLUGIN)
    assert report.syntax_valid
    assert report.is_high_risk
    categories = {f.category for f in report.findings}
    assert "import" in categories or "call" in categories
    details = " ".join(f.detail for f in report.findings)
    assert "subprocess" in details
    assert "os.system" in details
    assert "eval" in details


def test_syntax_error_is_high_risk():
    report = inspect_source(b"def broken(:\n    pass\n")
    assert not report.syntax_valid
    assert report.is_high_risk
    assert report.error is not None


def test_non_python_payload_rejected():
    report = inspect_source(b"<!DOCTYPE html><html><body>not python</body></html>")
    assert report.is_high_risk
    assert not report.syntax_valid


def test_oversize_payload_rejected():
    big = b"# " + b"a" * (MAX_PLUGIN_SIZE + 10)
    report = inspect_source(big)
    assert report.is_high_risk
    assert "exceeds maximum size" in (report.error or "")


def test_sha256_recorded_even_on_reject():
    report = inspect_source(DANGEROUS_PLUGIN)
    assert report.sha256 == sha256_hex(DANGEROUS_PLUGIN)
    assert report.size_bytes == len(DANGEROUS_PLUGIN)
