"""Command-line interface and synchronisation orchestration.

Implements the full workflow: connect -> scan -> fetch catalogue -> reconcile
-> inspect candidates -> plan -> (optionally) apply -> verify -> report. The
tool is a DRY RUN unless ``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import platform
import re
import sys
from typing import Optional

import requests

from . import __version__
from .catalogue import CatalogueFetchError, CatalogueParseError, fetch_catalogue
from .config import Config, ConfigError, load_config
from .httpclient import DownloadError, fetch_bytes
from .logging_config import configure_logging, get_logger
from .matcher import filename_stem, is_confident, match_installed
from .models import (
    ActionResult,
    ActionType,
    CataloguePlugin,
    InstalledPlugin,
    PluginResolution,
    SecurityReport,
    SyncStatus,
    VersionComparison,
    WarningLevel,
)
from .qbittorrent import (
    QbtApiError,
    QbtAuthError,
    QbtClient,
    QbtConnectionError,
    QbtSearchUnavailable,
)
from .report import build_report, write_report
from .security import MAX_PLUGIN_SIZE, UrlValidationError, inspect_source, validate_url
from .versions import compare_versions

logger = get_logger()

# Process exit codes (documented in the README).
EXIT_OK = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_CONFIG_ERROR = 2
EXIT_QBT_ERROR = 3
EXIT_CATALOGUE_ERROR = 4

_MIN_PY_RE = re.compile(r"python\s*3\.(\d+)\s*\+", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qbt_plugin_sync.py",
        description=(
            "Synchronise the unofficial 'Public Sites' qBittorrent search "
            "plugins with a running qBittorrent instance. Safe by default: a "
            "DRY RUN unless --apply is given."
        ),
    )
    parser.add_argument("--url", help="qBittorrent WebUI base URL (env: QBT_URL).")
    parser.add_argument(
        "--username", help="qBittorrent WebUI username (env: QBT_USERNAME)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform changes. Without it, nothing is modified.",
    )
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Install Public Sites plugins that are not currently present.",
    )
    parser.add_argument(
        "--no-update-existing",
        action="store_true",
        help="Do not attempt to update already-installed plugins.",
    )
    parser.add_argument(
        "--enable-new",
        action="store_true",
        help="Enable plugins that this tool newly installs (requires --apply).",
    )
    parser.add_argument(
        "--include-discouraged",
        action="store_true",
        help="Consider plugins flagged with ❗/✖ in the catalogue.",
    )
    parser.add_argument(
        "--include-suspicious",
        action="store_true",
        help="Consider plugins the static security scanner rates HIGH risk.",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="NAME",
        help="Only consider plugins whose name contains NAME (repeatable).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        metavar="NAME",
        help="Exclude plugins whose name contains NAME (repeatable).",
    )
    parser.add_argument("--json-report", metavar="PATH", help="Write a JSON report.")
    parser.add_argument("--log-file", metavar="PATH", help="Write a rotating log file.")
    parser.add_argument(
        "--timeout", type=float, metavar="SECONDS", help="HTTP timeout (env: QBT_TIMEOUT)."
    )
    parser.add_argument(
        "--catalogue-url", help="Override the catalogue MediaWiki source URL."
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose (DEBUG) output.")
    parser.add_argument(
        "--quiet", action="store_true", help="Only warnings and errors on console."
    )
    parser.add_argument(
        "--version", action="version", version=f"qbt_plugin_sync {__version__}"
    )
    return parser


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #
def _status_from_comparison(cmp: VersionComparison) -> SyncStatus:
    return {
        VersionComparison.CURRENT: SyncStatus.CURRENT,
        VersionComparison.OUTDATED: SyncStatus.OUTDATED,
        VersionComparison.NEWER_LOCAL: SyncStatus.NEWER_LOCAL,
        VersionComparison.UNKNOWN: SyncStatus.UNKNOWN_VERSION,
        VersionComparison.UNKNOWN_VERSION: SyncStatus.UNKNOWN_VERSION,
    }[cmp]


def reconcile(
    catalogue: list[CataloguePlugin], installed: list[InstalledPlugin]
) -> list[PluginResolution]:
    """Match catalogue entries to installed plugins and derive a base status."""

    resolutions: list[PluginResolution] = []
    matched_installed: set[int] = set()

    for cat in catalogue:
        candidate, confidence, signal = match_installed(cat, installed)
        res = PluginResolution(
            catalogue=cat,
            installed=None,
            status=SyncStatus.MISSING,
            match_confidence=confidence,
            match_signal=signal,
        )
        if candidate is not None and is_confident(confidence):
            res.installed = candidate
            matched_installed.add(id(candidate))
            cmp = compare_versions(candidate.version, cat.version)
            res.version_comparison = cmp
            res.status = _status_from_comparison(cmp)
        elif candidate is not None and confidence > 0:
            # A weak, ambiguous candidate exists: do not auto-act.
            res.status = SyncStatus.MANUAL_REVIEW
            res.notes.append(
                f"Ambiguous match to '{candidate.name}' "
                f"(confidence {confidence:.2f} < threshold)."
            )
        else:
            res.status = SyncStatus.MISSING
        resolutions.append(res)

    # Installed plugins that no catalogue entry claimed -> LOCAL_ONLY (kept).
    for plugin in installed:
        if id(plugin) not in matched_installed:
            resolutions.append(
                PluginResolution(
                    catalogue=None,
                    installed=plugin,
                    status=SyncStatus.LOCAL_ONLY,
                    notes=["Not present in the Public Sites catalogue; left untouched."],
                )
            )
    return resolutions


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #
def apply_filters(
    resolutions: list[PluginResolution],
    only: Optional[list[str]],
    exclude: Optional[list[str]],
) -> list[PluginResolution]:
    def name_of(res: PluginResolution) -> str:
        return res.display_name.lower()

    result = resolutions
    if only:
        needles = [o.lower() for o in only]
        result = [r for r in result if any(n in name_of(r) for n in needles)]
    if exclude:
        needles = [e.lower() for e in exclude]
        result = [r for r in result if not any(n in name_of(r) for n in needles)]
    return result


# --------------------------------------------------------------------------- #
# Compatibility heuristic
# --------------------------------------------------------------------------- #
def python_incompatibility(comments: str, running: tuple[int, int]) -> Optional[str]:
    """Return a reason string if the plugin declares a Python it clearly exceeds.

    Only triggers on an explicit minimum like "Python 3.10+"; conservative to
    avoid false positives that would block valid installs.
    """

    match = _MIN_PY_RE.search(comments or "")
    if not match:
        return None
    required_minor = int(match.group(1))
    if running[0] == 3 and running[1] < required_minor:
        return (
            f"Plugin requires Python 3.{required_minor}+, "
            f"running 3.{running[1]}."
        )
    return None


# --------------------------------------------------------------------------- #
# Candidate inspection (download + static security scan)
# --------------------------------------------------------------------------- #
def inspect_candidate(
    session: requests.Session,
    res: PluginResolution,
    *,
    timeout: float,
    check_dns: bool = True,
) -> SecurityReport:
    """Download and statically inspect a candidate plugin's source.

    Returns a :class:`SecurityReport`. On download/URL failure a HIGH-risk
    report describing the error is returned (never raises).
    """

    url = res.download_url
    if not url:
        report = SecurityReport(risk="HIGH", error="No usable download URL.")
        res.security = report
        return report

    try:
        validate_url(url, require_https=True, check_dns=check_dns)
    except UrlValidationError as exc:
        report = SecurityReport(risk="HIGH", error=f"URL rejected: {exc}")
        res.security = report
        return report

    try:
        data = fetch_bytes(
            session,
            url,
            timeout=timeout,
            max_bytes=MAX_PLUGIN_SIZE,
            validate=True,
            require_https=True,
            check_dns=check_dns,
        )
    except DownloadError as exc:
        report = SecurityReport(risk="HIGH", error=f"Download failed: {exc}")
        res.security = report
        return report

    report = inspect_source(data)
    res.security = report
    return report


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def plan_actions(
    session: requests.Session,
    resolutions: list[PluginResolution],
    args: argparse.Namespace,
    *,
    running_py: tuple[int, int],
    check_dns: bool = True,
) -> None:
    """Decide the action for each resolution, inspecting candidate sources.

    Mutates each :class:`PluginResolution` in place (status/action/security).
    """

    for res in resolutions:
        cat = res.catalogue

        # Updating an already-installed, outdated plugin.
        if res.status is SyncStatus.OUTDATED and cat is not None:
            if args.no_update_existing:
                res.action = ActionType.NONE
                res.notes.append("Update skipped (--no-update-existing).")
                continue
            res.action = ActionType.UPDATE
            if cat.download_url:
                inspect_candidate(
                    session, res, timeout=args.timeout, check_dns=check_dns
                )
            continue

        # Installing a missing plugin.
        if res.status is SyncStatus.MISSING and cat is not None:
            if not args.install_missing:
                res.action = ActionType.NONE
                res.notes.append("Missing; pass --install-missing to install.")
                continue

            warning = cat.warning_level
            if warning in (WarningLevel.DISCOURAGED, WarningLevel.BROKEN) and not (
                args.include_discouraged
            ):
                res.status = SyncStatus.SKIPPED_WARNING
                res.action = ActionType.SKIP
                res.notes.append(
                    f"Catalogue flags this plugin as {warning.value}; skipped "
                    f"(use --include-discouraged to override)."
                )
                continue

            if not cat.download_url:
                res.status = SyncStatus.SKIPPED_WARNING
                res.action = ActionType.SKIP
                res.notes.append("No usable download URL.")
                continue

            incompatible = python_incompatibility(cat.comments, running_py)
            if incompatible:
                res.status = SyncStatus.INCOMPATIBLE
                res.action = ActionType.SKIP
                res.notes.append(incompatible)
                continue

            report = inspect_candidate(
                session, res, timeout=args.timeout, check_dns=check_dns
            )
            if report.error or not report.syntax_valid:
                res.status = SyncStatus.SKIPPED_WARNING
                res.action = ActionType.SKIP
                res.notes.append(report.error or "Invalid Python source.")
                continue
            if report.is_high_risk and not args.include_suspicious:
                res.status = SyncStatus.SUSPICIOUS
                res.action = ActionType.SKIP
                res.notes.append(
                    "Static scanner rated HIGH risk (use --include-suspicious "
                    "to override)."
                )
                continue

            res.action = ActionType.INSTALL
            continue

        # Everything else: report only.
        res.action = ActionType.NONE


# --------------------------------------------------------------------------- #
# Applying
# --------------------------------------------------------------------------- #
def _expected_plugin_name(cat: CataloguePlugin) -> str:
    stem = filename_stem(cat.download_url)
    return stem or cat.normalized_name


def apply_actions(
    qbt: QbtClient, resolutions: list[PluginResolution], args: argparse.Namespace
) -> None:
    """Execute planned actions against qBittorrent, verifying each result."""

    updates = [r for r in resolutions if r.action is ActionType.UPDATE]
    installs = [r for r in resolutions if r.action is ActionType.INSTALL]

    # ---- Updates: use qBittorrent's own updater once, then verify ---- #
    if updates:
        logger.info("Requesting qBittorrent to update %d plugin(s).", len(updates))
        try:
            qbt.update_plugins()
        except QbtApiError as exc:
            for res in updates:
                res.result = ActionResult.FAILED
                res.error = f"updatePlugins failed: {exc}"
        else:
            after = {p.name: p for p in qbt.get_plugins()}
            for res in updates:
                assert res.catalogue is not None and res.installed is not None
                current = after.get(res.installed.name)
                if current is None:
                    res.result = ActionResult.VERIFY_FAILED
                    res.error = "Plugin disappeared after update."
                    continue
                cmp = compare_versions(current.version, res.catalogue.version)
                res.installed = current
                res.version_comparison = cmp
                if cmp in (VersionComparison.CURRENT, VersionComparison.NEWER_LOCAL):
                    res.result = ActionResult.SUCCESS
                    res.status = SyncStatus.CURRENT
                else:
                    # Still behind; consider a safe reinstall from catalogue source.
                    res.result = _reinstall_if_safe(qbt, res, args)

    # ---- Installs: one at a time, each verified individually ---- #
    for res in installs:
        assert res.catalogue is not None
        source = res.catalogue.download_url
        expected = _expected_plugin_name(res.catalogue)
        try:
            qbt.install_plugin(source)
        except (QbtApiError, QbtConnectionError) as exc:
            res.result = ActionResult.FAILED
            res.error = f"installPlugin failed: {exc}"
            continue

        installed = qbt.wait_for_plugin(expected)
        if installed is None:
            res.result = ActionResult.VERIFY_FAILED
            res.error = (
                f"Plugin '{expected}' not present after installation "
                "(verification via /search/plugins failed)."
            )
            continue

        res.installed = installed
        res.status = SyncStatus.CURRENT
        res.result = ActionResult.SUCCESS

        if args.enable_new and not installed.enabled:
            try:
                qbt.enable_plugin(installed.name, True)
                res.notes.append("Enabled newly installed plugin.")
            except (QbtApiError, QbtConnectionError) as exc:
                res.notes.append(f"Install ok but enable failed: {exc}")


def _reinstall_if_safe(
    qbt: QbtClient, res: PluginResolution, args: argparse.Namespace
) -> ActionResult:
    """Reinstall an outdated plugin from a safe catalogue source, then verify."""

    cat = res.catalogue
    assert cat is not None
    security = res.security
    safe = (
        cat.download_url
        and security is not None
        and security.syntax_valid
        and not security.error
        and (not security.is_high_risk or args.include_suspicious)
    )
    if not safe:
        res.error = "Still outdated after updatePlugins; no safe source to reinstall."
        res.notes.append(res.error)
        return ActionResult.VERIFY_FAILED

    try:
        qbt.install_plugin(cat.download_url)
    except (QbtApiError, QbtConnectionError) as exc:
        res.error = f"Reinstall failed: {exc}"
        return ActionResult.FAILED

    after = {p.name: p for p in qbt.get_plugins()}
    current = after.get(_expected_plugin_name(cat)) or after.get(res.installed.name)
    if current is None:
        res.error = "Plugin missing after reinstall."
        return ActionResult.VERIFY_FAILED
    res.installed = current
    cmp = compare_versions(current.version, cat.version)
    res.version_comparison = cmp
    if cmp in (VersionComparison.CURRENT, VersionComparison.NEWER_LOCAL):
        res.status = SyncStatus.CURRENT
        res.notes.append("Reinstalled from catalogue source.")
        return ActionResult.SUCCESS
    res.error = "Still outdated after reinstall."
    return ActionResult.VERIFY_FAILED


def mark_dry_run(resolutions: list[PluginResolution]) -> None:
    """Tag planned actions as DRY_RUN (no mutations performed)."""

    for res in resolutions:
        if res.action in (ActionType.INSTALL, ActionType.UPDATE, ActionType.ENABLE):
            res.result = ActionResult.DRY_RUN


# --------------------------------------------------------------------------- #
# Console rendering
# --------------------------------------------------------------------------- #
def render_console(
    resolutions: list[PluginResolution],
    *,
    qbt_version: str,
    webapi_version: str,
    installed_count: int,
    catalogue_count: int,
    dry_run: bool,
    stream=sys.stdout,
) -> None:
    py = platform.python_version()
    print("qBittorrent Search Plugin Synchroniser", file=stream)
    print("======================================", file=stream)
    print(file=stream)
    print(f"qBittorrent: {qbt_version}", file=stream)
    print(f"Web API:     {webapi_version}", file=stream)
    print(f"Python:      {py}", file=stream)
    print(file=stream)
    print(f"Installed plugins:      {installed_count}", file=stream)
    print(f"Public catalogue:       {catalogue_count}", file=stream)
    print(file=stream)
    print(f"{'STATUS':<17}{'PLUGIN':<26}{'LOCAL':<12}{'REMOTE':<12}", file=stream)
    print("-" * 67, file=stream)

    order = {
        SyncStatus.OUTDATED: 0,
        SyncStatus.MISSING: 1,
        SyncStatus.MANUAL_REVIEW: 2,
        SyncStatus.SUSPICIOUS: 3,
        SyncStatus.INCOMPATIBLE: 4,
        SyncStatus.SKIPPED_WARNING: 5,
        SyncStatus.UNKNOWN_VERSION: 6,
        SyncStatus.NEWER_LOCAL: 7,
        SyncStatus.CURRENT: 8,
        SyncStatus.LOCAL_ONLY: 9,
    }
    for res in sorted(resolutions, key=lambda r: (order.get(r.status, 99), r.display_name.lower())):
        local = res.local_version or "-"
        remote = res.remote_version or "-"
        name = res.display_name[:25]
        print(
            f"{res.status.value:<17}{name:<26}{local:<12}{remote:<12}", file=stream
        )

    installs = sum(1 for r in resolutions if r.action is ActionType.INSTALL)
    updates = sum(1 for r in resolutions if r.action is ActionType.UPDATE)
    skips = sum(1 for r in resolutions if r.action is ActionType.SKIP)
    reviews = sum(1 for r in resolutions if r.status is SyncStatus.MANUAL_REVIEW)

    print(file=stream)
    print("Proposed actions:", file=stream)
    print(f"  Install:  {installs}", file=stream)
    print(f"  Update:   {updates}", file=stream)
    print(f"  Skip:     {skips}", file=stream)
    print(f"  Review:   {reviews}", file=stream)
    print(file=stream)

    if dry_run:
        print("MODE: DRY RUN", file=stream)
        print(file=stream)
        print("No qBittorrent configuration was changed.", file=stream)
    else:
        print("MODE: APPLY", file=stream)
        print(file=stream)
        _render_apply_results(resolutions, stream=stream)


def _render_apply_results(resolutions: list[PluginResolution], *, stream) -> None:
    acted = [
        r
        for r in resolutions
        if r.result
        in (
            ActionResult.SUCCESS,
            ActionResult.FAILED,
            ActionResult.VERIFY_FAILED,
        )
    ]
    if not acted:
        print("No changes were required.", file=stream)
        return
    print("Results:", file=stream)
    for res in acted:
        line = f"  [{res.result.value}] {res.action.value} {res.display_name}"
        if res.error:
            line += f" — {res.error}"
        print(line, file=stream)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(args: argparse.Namespace) -> int:
    dry_run = not args.apply

    # ---- configuration ---- #
    try:
        config: Config = load_config(
            url=args.url, username=args.username, timeout=args.timeout,
            catalogue_url=args.catalogue_url,
        )
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return EXIT_CONFIG_ERROR

    running_py = sys.version_info[:2]

    # ---- connect + authenticate ---- #
    try:
        qbt = QbtClient(config.url, timeout=config.timeout)
        qbt.login(config.username, config.password)
        qbt_version = qbt.app_version()
        webapi_version = qbt.webapi_version()
        installed = qbt.get_plugins()
    except (QbtConnectionError, QbtAuthError, QbtSearchUnavailable) as exc:
        logger.error("qBittorrent error: %s", exc)
        return EXIT_QBT_ERROR
    except QbtApiError as exc:
        logger.error("qBittorrent API error: %s", exc)
        return EXIT_QBT_ERROR

    # ---- catalogue ---- #
    catalogue_session = requests.Session()
    catalogue_session.headers.update({"User-Agent": "qbt-plugin-sync/1.0"})
    try:
        catalogue = fetch_catalogue(
            catalogue_session, config.catalogue_url, timeout=config.timeout
        )
    except (CatalogueFetchError, CatalogueParseError) as exc:
        logger.error("Catalogue error: %s", exc)
        qbt.close()
        return EXIT_CATALOGUE_ERROR

    # ---- reconcile + plan ---- #
    resolutions = reconcile(catalogue, installed)
    resolutions = apply_filters(resolutions, args.only, args.exclude)
    plan_actions(catalogue_session, resolutions, args, running_py=running_py)

    # ---- apply or dry-run ---- #
    exit_code = EXIT_OK
    if dry_run:
        mark_dry_run(resolutions)
    else:
        if args.enable_new and not args.apply:  # pragma: no cover - guarded by dry_run
            pass
        apply_actions(qbt, resolutions, args)
        if any(
            r.result in (ActionResult.FAILED, ActionResult.VERIFY_FAILED)
            for r in resolutions
        ):
            exit_code = EXIT_PARTIAL_FAILURE

    # ---- output ---- #
    if not args.quiet:
        render_console(
            resolutions,
            qbt_version=qbt_version,
            webapi_version=webapi_version,
            installed_count=len(installed),
            catalogue_count=len(catalogue),
            dry_run=dry_run,
        )

    if args.json_report:
        report = build_report(
            qbittorrent_version=qbt_version,
            webapi_version=webapi_version,
            catalogue_source=config.catalogue_url,
            dry_run=dry_run,
            resolutions=resolutions,
            python_version=platform.python_version(),
        )
        try:
            write_report(report, args.json_report)
            logger.info("Wrote JSON report to %s", args.json_report)
        except OSError as exc:
            logger.error("Failed to write JSON report: %s", exc)

    qbt.close()
    catalogue_session.close()
    return exit_code


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(
        verbose=args.verbose, quiet=args.quiet, log_file=args.log_file
    )
    if args.enable_new and not args.apply:
        logger.warning("--enable-new has no effect without --apply (dry run).")
    try:
        return run(args)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        logger.error("Interrupted.")
        return EXIT_CONFIG_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
