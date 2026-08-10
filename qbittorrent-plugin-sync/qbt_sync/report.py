"""JSON report generation.

Serialises the reconciled plugin resolutions into a structured, auditable
report. Credentials are never included.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .models import ActionResult, PluginResolution, SyncStatus


def _plugin_entry(res: PluginResolution) -> dict:
    security = res.security
    return {
        "catalogue_name": res.catalogue.display_name if res.catalogue else None,
        "qbittorrent_name": res.installed.name if res.installed else None,
        "installed_version": res.local_version,
        "catalogue_version": res.remote_version,
        "download_url": res.download_url,
        "sha256": security.sha256 if security else None,
        "status": res.status.value,
        "version_comparison": res.version_comparison.value,
        "warning_level": (
            res.catalogue.warning_level.value if res.catalogue else None
        ),
        "match_confidence": round(res.match_confidence, 3),
        "match_signal": res.match_signal,
        "security_findings": (
            [
                {"category": f.category, "detail": f.detail, "lineno": f.lineno}
                for f in security.findings
            ]
            if security
            else []
        ),
        "security_risk": security.risk if security else None,
        "action_attempted": res.action.value,
        "result": res.result.value,
        "error": res.error,
        "notes": list(res.notes),
    }


def build_report(
    *,
    qbittorrent_version: str,
    webapi_version: str,
    catalogue_source: str,
    dry_run: bool,
    resolutions: list[PluginResolution],
    python_version: str,
) -> dict:
    """Assemble the full report structure as a plain dict."""

    summary: dict[str, int] = {}
    for status in SyncStatus:
        count = sum(1 for r in resolutions if r.status is status)
        if count:
            summary[status.value] = count

    actions_taken = sum(
        1
        for r in resolutions
        if r.result in (ActionResult.SUCCESS, ActionResult.VERIFY_FAILED)
    )
    failures = sum(
        1
        for r in resolutions
        if r.result in (ActionResult.FAILED, ActionResult.VERIFY_FAILED)
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "qbittorrent_version": qbittorrent_version,
        "webapi_version": webapi_version,
        "python_version": python_version,
        "catalogue_source": catalogue_source,
        "dry_run": dry_run,
        "summary": {
            "total": len(resolutions),
            "by_status": summary,
            "actions_taken": actions_taken,
            "failures": failures,
        },
        "plugins": [_plugin_entry(r) for r in resolutions],
    }


def write_report(report: dict, path: str) -> None:
    """Write the report as pretty-printed JSON to ``path``."""

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=False)
        handle.write("\n")
