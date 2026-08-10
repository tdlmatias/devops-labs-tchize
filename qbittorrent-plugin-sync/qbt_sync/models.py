"""Data models and enumerations used across the synchroniser.

All models are plain dataclasses so they are trivial to construct in tests and
to serialise into the JSON report. Nothing here performs I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WarningLevel(str, Enum):
    """Warning flag associated with a catalogue entry.

    Derived from the wiki symbols in the "Comments" column:

    * ``✔``            -> :attr:`OK`         (eligible for automatic install)
    * ``❗``            -> :attr:`DISCOURAGED` (skip unless --include-discouraged)
    * ``✖`` / ``❌``    -> :attr:`BROKEN`      (never auto-installed)
    * (no symbol)      -> :attr:`UNKNOWN`     (treated conservatively)
    """

    OK = "OK"
    DISCOURAGED = "DISCOURAGED"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"


class SyncStatus(str, Enum):
    """The reconciled state of a plugin after comparing catalogue vs. installed."""

    CURRENT = "CURRENT"
    OUTDATED = "OUTDATED"
    NEWER_LOCAL = "NEWER_LOCAL"
    MISSING = "MISSING"
    LOCAL_ONLY = "LOCAL_ONLY"
    SKIPPED_WARNING = "SKIPPED_WARNING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    INCOMPATIBLE = "INCOMPATIBLE"
    SUSPICIOUS = "SUSPICIOUS"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"


class VersionComparison(str, Enum):
    """Result of comparing an installed version against a catalogue version."""

    CURRENT = "CURRENT"
    OUTDATED = "OUTDATED"
    NEWER_LOCAL = "NEWER_LOCAL"
    UNKNOWN = "UNKNOWN"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"


class ActionType(str, Enum):
    """The action the tool intends to take (or took) for a plugin."""

    NONE = "NONE"
    INSTALL = "INSTALL"
    UPDATE = "UPDATE"
    ENABLE = "ENABLE"
    SKIP = "SKIP"
    REVIEW = "REVIEW"


class ActionResult(str, Enum):
    """The outcome of an attempted action."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    DRY_RUN = "DRY_RUN"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    VERIFY_FAILED = "VERIFY_FAILED"


@dataclass
class CataloguePlugin:
    """A single plugin entry parsed from the "Plugins for Public Sites" table."""

    display_name: str
    normalized_name: str
    repository_url: Optional[str]
    version: Optional[str]
    last_update: Optional[str]
    download_url: Optional[str]
    comments: str
    status: Optional[str]  # raw status string, e.g. "OK", "DISCOURAGED"
    site_url: Optional[str] = None

    @property
    def warning_level(self) -> WarningLevel:
        try:
            return WarningLevel(self.status) if self.status else WarningLevel.UNKNOWN
        except ValueError:
            return WarningLevel.UNKNOWN


@dataclass
class InstalledPlugin:
    """A plugin as reported by ``GET /api/v2/search/plugins``."""

    name: str
    full_name: str
    version: Optional[str]
    site_url: Optional[str]
    enabled: bool


@dataclass
class SecurityFinding:
    """A single heuristic finding produced by the static plugin inspector."""

    category: str
    detail: str
    lineno: Optional[int] = None


@dataclass
class SecurityReport:
    """Aggregated result of statically inspecting a plugin's source code."""

    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    syntax_valid: bool = False
    findings: list[SecurityFinding] = field(default_factory=list)
    risk: str = "UNKNOWN"  # LOW | MEDIUM | HIGH | UNKNOWN
    error: Optional[str] = None

    @property
    def is_high_risk(self) -> bool:
        return self.risk == "HIGH"


@dataclass
class PluginResolution:
    """The fully reconciled record for one plugin, used for output and reporting."""

    catalogue: Optional[CataloguePlugin]
    installed: Optional[InstalledPlugin]
    status: SyncStatus
    version_comparison: VersionComparison = VersionComparison.UNKNOWN
    match_confidence: float = 0.0
    match_signal: str = ""
    security: Optional[SecurityReport] = None
    action: ActionType = ActionType.NONE
    result: ActionResult = ActionResult.NOT_ATTEMPTED
    error: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    # ----- convenience accessors used by the console/report layers -----

    @property
    def display_name(self) -> str:
        if self.catalogue is not None:
            return self.catalogue.display_name
        if self.installed is not None:
            return self.installed.full_name or self.installed.name
        return "<unknown>"

    @property
    def local_version(self) -> Optional[str]:
        return self.installed.version if self.installed else None

    @property
    def remote_version(self) -> Optional[str]:
        return self.catalogue.version if self.catalogue else None

    @property
    def download_url(self) -> Optional[str]:
        return self.catalogue.download_url if self.catalogue else None
