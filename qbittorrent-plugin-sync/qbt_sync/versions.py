"""Version comparison utilities.

Community plugin versions are frequently non-PEP440 (dates, ``1.0a``, ``v2``,
empty strings). We therefore never fall back to lexicographic string ordering,
which silently produces wrong answers (e.g. ``"9" > "10"``). When a version
cannot be interpreted with confidence we return an explicit UNKNOWN result and
the caller avoids destructive action.
"""

from __future__ import annotations

import re
from typing import Optional

from packaging.version import InvalidVersion, Version

from .models import VersionComparison


def normalize_version(raw: Optional[str]) -> Optional[str]:
    """Trim decoration from a raw version string, returning ``None`` if empty."""

    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    # Strip a single leading 'v' / 'V' which is extremely common decoration.
    if value[0] in "vV" and len(value) > 1 and value[1].isdigit():
        value = value[1:]
    return value


def parse_version(raw: Optional[str]) -> Optional[Version]:
    """Best-effort parse into a :class:`packaging.version.Version`.

    Returns ``None`` when the string is missing or cannot be parsed as a real
    version. We do *not* try to coerce arbitrary strings into versions.
    """

    normalized = normalize_version(raw)
    if normalized is None:
        return None
    try:
        return Version(normalized)
    except InvalidVersion:
        # A very common community pattern is "1.2.3-something"; try the numeric
        # prefix, but only if it is unambiguous (digits and dots).
        match = re.match(r"^(\d+(?:\.\d+)*)", normalized)
        if match:
            try:
                return Version(match.group(1))
            except InvalidVersion:  # pragma: no cover - defensive
                return None
        return None


def compare_versions(
    installed: Optional[str], catalogue: Optional[str]
) -> VersionComparison:
    """Compare an installed version against a catalogue version.

    :returns: one of :class:`VersionComparison` members.

    * Both parse and equal            -> CURRENT
    * Installed < catalogue           -> OUTDATED
    * Installed > catalogue           -> NEWER_LOCAL
    * Either side is missing entirely -> UNKNOWN
    * A present-but-unparseable side  -> UNKNOWN_VERSION
    """

    installed_norm = normalize_version(installed)
    catalogue_norm = normalize_version(catalogue)

    # Missing information -> we simply do not know.
    if installed_norm is None or catalogue_norm is None:
        return VersionComparison.UNKNOWN

    installed_v = parse_version(installed_norm)
    catalogue_v = parse_version(catalogue_norm)

    if installed_v is None or catalogue_v is None:
        # At least one side is present but not interpretable. Fall back to an
        # exact, case-insensitive string equality check (safe, non-ordering).
        if installed_norm.lower() == catalogue_norm.lower():
            return VersionComparison.CURRENT
        return VersionComparison.UNKNOWN_VERSION

    if installed_v == catalogue_v:
        return VersionComparison.CURRENT
    if installed_v < catalogue_v:
        return VersionComparison.OUTDATED
    return VersionComparison.NEWER_LOCAL
