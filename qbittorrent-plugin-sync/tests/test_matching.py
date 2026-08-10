"""Tests for name normalisation and conservative matching."""

from __future__ import annotations

from qbt_sync.matcher import (
    filename_stem,
    hostname_token,
    is_confident,
    match_installed,
    normalize_name,
)
from qbt_sync.models import CataloguePlugin, InstalledPlugin


def make_catalogue(name, download_url=None, site_url=None, version="1.0"):
    return CataloguePlugin(
        display_name=name,
        normalized_name=normalize_name(name),
        repository_url=None,
        version=version,
        last_update=None,
        download_url=download_url,
        comments="",
        status="OK",
        site_url=site_url,
    )


def make_installed(name, full_name=None, version="1.0", site_url=None):
    return InstalledPlugin(
        name=name,
        full_name=full_name or name,
        version=version,
        site_url=site_url,
        enabled=True,
    )


def test_normalize_name_basics():
    assert normalize_name("Academic Torrents") == "academic_torrents"
    assert normalize_name("The Pirate-Bay") == "the_pirate_bay"
    # A recognised TLD suffix is stripped on single-token names.
    assert normalize_name("thepiratebay.org") == "thepiratebay"
    # A non-TLD dot becomes a separator (conservative).
    assert normalize_name("acg.rip") == "acg_rip"
    assert normalize_name("") == ""


def test_normalize_keeps_multiword_tld_like():
    # A multi-word name must not have ".com" stripped mid-phrase.
    assert normalize_name("my site .com plugin") == "my_site_com_plugin"


def test_filename_stem_and_hostname():
    assert filename_stem("https://x/y/academictorrents.py") == "academictorrents"
    assert hostname_token("https://www.example.com/") == "example"


def test_exact_filename_match_is_confident():
    cat = make_catalogue(
        "Academic Torrents",
        download_url="https://x/academictorrents.py",
    )
    installed = [make_installed("academictorrents")]
    plugin, conf, signal = match_installed(cat, installed)
    assert plugin is installed[0]
    assert is_confident(conf)
    assert "filename" in signal


def test_hostname_match():
    cat = make_catalogue("Example Search", site_url="https://example.com/")
    installed = [make_installed("examplesearch", site_url="https://example.com/")]
    plugin, conf, _ = match_installed(cat, installed)
    assert plugin is installed[0]
    assert is_confident(conf)


def test_ambiguous_substring_is_below_threshold():
    cat = make_catalogue("Torrent", download_url="https://x/torrent.py")
    installed = [make_installed("bigtorrentsearch")]
    plugin, conf, _ = match_installed(cat, installed)
    # A weak substring hint is returned but must not be "confident".
    assert plugin is installed[0]
    assert not is_confident(conf)


def test_no_match_returns_none():
    cat = make_catalogue("Totally Unique", download_url="https://x/uniqueplugin.py")
    installed = [make_installed("something_else")]
    plugin, conf, _ = match_installed(cat, installed)
    assert plugin is None
    assert conf == 0.0
