"""Tests for version normalisation and comparison."""

from __future__ import annotations

from qbt_sync.models import VersionComparison
from qbt_sync.versions import compare_versions, normalize_version, parse_version


def test_normalize_strips_v_prefix():
    assert normalize_version("v1.2.3") == "1.2.3"
    assert normalize_version("V2") == "2"
    assert normalize_version("  1.0 ") == "1.0"
    assert normalize_version("") is None
    assert normalize_version(None) is None


def test_parse_version_handles_suffix():
    # packaging understands PEP 440 pre-release forms directly.
    assert parse_version("1.2.3-beta") is not None
    # A non-PEP440 trailer falls back to the leading numeric prefix.
    assert str(parse_version("2.0 (stable build)")) == "2.0"
    assert parse_version("not-a-version") is None


def test_compare_equal_is_current():
    assert compare_versions("1.2", "1.2") is VersionComparison.CURRENT
    assert compare_versions("v1.2", "1.2") is VersionComparison.CURRENT


def test_compare_outdated_and_newer():
    assert compare_versions("1.0", "1.3") is VersionComparison.OUTDATED
    assert compare_versions("2.0", "1.3") is VersionComparison.NEWER_LOCAL


def test_no_lexicographic_ordering_bug():
    # "9" must be considered older than "10", not newer.
    assert compare_versions("9", "10") is VersionComparison.OUTDATED
    assert compare_versions("10", "9") is VersionComparison.NEWER_LOCAL


def test_missing_side_is_unknown():
    assert compare_versions(None, "1.0") is VersionComparison.UNKNOWN
    assert compare_versions("1.0", None) is VersionComparison.UNKNOWN


def test_unparseable_versions():
    # Both present but unparseable and unequal -> UNKNOWN_VERSION.
    assert compare_versions("alpha", "beta") is VersionComparison.UNKNOWN_VERSION
    # Present, unparseable, but exactly equal -> CURRENT.
    assert compare_versions("weird-rev", "weird-rev") is VersionComparison.CURRENT
