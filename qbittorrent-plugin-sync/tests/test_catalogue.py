"""Tests for the MediaWiki catalogue parser."""

from __future__ import annotations

import pytest

from qbt_sync.catalogue import (
    CatalogueParseError,
    _detect_warning,
    _extract_public_section,
    _pick_download_url,
    parse_catalogue,
)
from qbt_sync.models import WarningLevel


def _by_name(plugins, name):
    for p in plugins:
        if p.display_name == name:
            return p
    raise AssertionError(f"{name!r} not found in parsed plugins")


def test_parses_only_public_sites_table(sample_catalogue_text):
    plugins = parse_catalogue(sample_catalogue_text)
    names = {p.display_name for p in plugins}
    # From the Public Sites table.
    assert "Academic Torrents" in names
    assert "acgrip" in names
    # From ignored/other tables — must NOT be present.
    assert "Ignore Me" not in names
    assert "PrivateOnly" not in names


def test_public_section_extraction_stops_at_next_heading(sample_catalogue_text):
    section = _extract_public_section(sample_catalogue_text)
    joined = "\n".join(section)
    assert "Academic Torrents" in joined
    assert "Plugins for Private Sites" not in joined
    assert "PrivateOnly" not in joined


def test_extracts_expected_fields(sample_catalogue_text):
    plugins = parse_catalogue(sample_catalogue_text)
    academic = _by_name(plugins, "Academic Torrents")
    assert academic.version == "1.2"
    assert academic.site_url == "https://academictorrents.com/"
    assert academic.repository_url == (
        "https://github.com/LightDestory/qBittorrent-Search-Plugins"
    )
    assert academic.download_url.endswith("/academictorrents.py")
    assert academic.last_update == "19/Mar 2023"
    assert academic.warning_level is WarningLevel.OK


def test_warning_detection_variants(sample_catalogue_text):
    plugins = parse_catalogue(sample_catalogue_text)
    assert _by_name(plugins, "LimeTorrents").warning_level is WarningLevel.DISCOURAGED
    assert _by_name(plugins, "DeadSite").warning_level is WarningLevel.BROKEN
    assert _by_name(plugins, "acgrip").warning_level is WarningLevel.OK


def test_missing_version_and_missing_url(sample_catalogue_text):
    plugins = parse_catalogue(sample_catalogue_text)
    noversion = _by_name(plugins, "NoVersion")
    assert noversion.version is None
    assert noversion.download_url.endswith("/noversion.py")

    nodownload = _by_name(plugins, "NoDownload")
    assert nodownload.download_url is None
    assert nodownload.version == "3.0"


def test_normalized_names(sample_catalogue_text):
    plugins = parse_catalogue(sample_catalogue_text)
    assert _by_name(plugins, "Academic Torrents").normalized_name == "academic_torrents"
    # "acg.rip" is a single hostname-like token: TLD stripped.
    assert _by_name(plugins, "acgrip").normalized_name == "acgrip"


def test_pick_download_url_prefers_py():
    links = [
        ("https://example.com/icon.png", ""),
        ("https://example.com/plugin.py", ""),
    ]
    assert _pick_download_url(links) == "https://example.com/plugin.py"
    assert _pick_download_url([]) is None


def test_detect_warning_precedence():
    assert _detect_warning("✔ ok but ✖ broken") is WarningLevel.BROKEN
    assert _detect_warning("❗ discouraged") is WarningLevel.DISCOURAGED
    assert _detect_warning("plain text") is WarningLevel.UNKNOWN


def test_missing_public_section_raises():
    with pytest.raises(CatalogueParseError):
        parse_catalogue("== Something Else ==\nno table here\n")


def test_malformed_rows_are_skipped():
    text = (
        "== Plugins for Public Sites ==\n"
        '{|class="sortable"\n'
        "|-\n! A\n! B\n! C\n! D\n! E\n! F\n"
        "|-\n| [https://ok.example/ Good]\n| \n| 1.0\n| x\n"
        "| [https://ok.example/good.py]\n| ✔\n"
        "|-\n| only one cell\n"  # malformed, should be skipped
        "|}\n"
    )
    plugins = parse_catalogue(text)
    assert len(plugins) == 1
    assert plugins[0].display_name == "Good"
