"""Tests for the reconciliation/planning/apply engine in qbt_sync.cli.

All qBittorrent mutations are mocked; no real plugin is ever installed.
"""

from __future__ import annotations

import argparse

import pytest

from qbt_sync import cli
from qbt_sync.models import (
    ActionResult,
    ActionType,
    CataloguePlugin,
    InstalledPlugin,
    SecurityReport,
    SyncStatus,
)


def cat(name, download_url=None, version="1.0", status="OK", comments="", site_url=None):
    from qbt_sync.matcher import normalize_name

    return CataloguePlugin(
        display_name=name,
        normalized_name=normalize_name(name),
        repository_url=None,
        version=version,
        last_update=None,
        download_url=download_url,
        comments=comments,
        status=status,
        site_url=site_url,
    )


def inst(name, version="1.0", full_name=None, enabled=True, site_url=None):
    return InstalledPlugin(
        name=name, full_name=full_name or name, version=version,
        site_url=site_url, enabled=enabled,
    )


def make_args(**overrides):
    defaults = dict(
        url=None, username=None, apply=False, install_missing=False,
        no_update_existing=False, enable_new=False, include_discouraged=False,
        include_suspicious=False, only=None, exclude=None, json_report=None,
        log_file=None, timeout=5.0, catalogue_url=None, verbose=False, quiet=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ------------------------------- reconcile ---------------------------------- #
def test_reconcile_statuses():
    catalogue = [
        cat("Academic Torrents", download_url="https://x/academictorrents.py", version="1.2"),
        cat("OldPlugin", download_url="https://x/oldplugin.py", version="2.0"),
        cat("MissingPlugin", download_url="https://x/missingplugin.py", version="1.0"),
    ]
    installed = [
        inst("academictorrents", version="1.2"),
        inst("oldplugin", version="1.0"),
        inst("localonly", version="5.0"),
    ]
    resolutions = cli.reconcile(catalogue, installed)
    by_name = {r.display_name: r for r in resolutions}
    assert by_name["Academic Torrents"].status is SyncStatus.CURRENT
    assert by_name["OldPlugin"].status is SyncStatus.OUTDATED
    assert by_name["MissingPlugin"].status is SyncStatus.MISSING
    # localonly is not in catalogue -> LOCAL_ONLY, kept.
    local = [r for r in resolutions if r.status is SyncStatus.LOCAL_ONLY]
    assert len(local) == 1
    assert local[0].installed.name == "localonly"


def test_reconcile_ambiguous_is_manual_review():
    catalogue = [cat("Torrent", download_url="https://x/torrent.py")]
    installed = [inst("bigtorrentsearch")]
    resolutions = cli.reconcile(catalogue, installed)
    assert resolutions[0].status is SyncStatus.MANUAL_REVIEW


# ------------------------------- filters ------------------------------------ #
def test_apply_filters_only_and_exclude():
    catalogue = [cat("Alpha", "https://x/alpha.py"), cat("Beta", "https://x/beta.py")]
    resolutions = cli.reconcile(catalogue, [])
    only = cli.apply_filters(resolutions, ["alpha"], None)
    assert {r.display_name for r in only} == {"Alpha"}
    excl = cli.apply_filters(resolutions, None, ["beta"])
    assert {r.display_name for r in excl} == {"Alpha"}


# --------------------------- compatibility ---------------------------------- #
def test_python_incompatibility_detects_minimum():
    assert cli.python_incompatibility("qbt 5.0.x / Python 3.10+", (3, 8))
    assert cli.python_incompatibility("Python 3.10+", (3, 11)) is None
    assert cli.python_incompatibility("no version info", (3, 8)) is None


# ----------------------------- planning ------------------------------------- #
def _safe_report():
    r = SecurityReport(sha256="abc", size_bytes=10, syntax_valid=True, risk="LOW")
    return r


def test_plan_skips_discouraged(monkeypatch):
    monkeypatch.setattr(cli, "inspect_candidate", lambda *a, **k: _safe_report())
    catalogue = [cat("Bad", "https://x/bad.py", status="DISCOURAGED")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(None, resolutions, make_args(install_missing=True), running_py=(3, 11))
    assert resolutions[0].status is SyncStatus.SKIPPED_WARNING
    assert resolutions[0].action is ActionType.SKIP


def test_plan_installs_missing_when_flagged(monkeypatch):
    monkeypatch.setattr(cli, "inspect_candidate",
                        lambda session, res, **k: setattr(res, "security", _safe_report()) or _safe_report())
    catalogue = [cat("Good", "https://x/good.py", status="OK")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(None, resolutions, make_args(install_missing=True), running_py=(3, 11))
    assert resolutions[0].action is ActionType.INSTALL


def test_plan_missing_without_flag_is_no_action():
    catalogue = [cat("Good", "https://x/good.py")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(None, resolutions, make_args(install_missing=False), running_py=(3, 11))
    assert resolutions[0].action is ActionType.NONE


def test_plan_high_risk_is_suspicious(monkeypatch):
    def fake_inspect(session, res, **k):
        rep = SecurityReport(sha256="x", syntax_valid=True, risk="HIGH")
        res.security = rep
        return rep

    monkeypatch.setattr(cli, "inspect_candidate", fake_inspect)
    catalogue = [cat("Risky", "https://x/risky.py")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(None, resolutions, make_args(install_missing=True), running_py=(3, 11))
    assert resolutions[0].status is SyncStatus.SUSPICIOUS
    assert resolutions[0].action is ActionType.SKIP


def test_plan_include_discouraged_allows_install(monkeypatch):
    monkeypatch.setattr(cli, "inspect_candidate", lambda s, r, **k: _safe_report())
    catalogue = [cat("Bad", "https://x/bad.py", status="DISCOURAGED")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(
        None, resolutions,
        make_args(install_missing=True, include_discouraged=True), running_py=(3, 11),
    )
    assert resolutions[0].action is ActionType.INSTALL


def test_plan_include_suspicious_allows_install(monkeypatch):
    def fake_inspect(session, res, **k):
        rep = SecurityReport(sha256="x", syntax_valid=True, risk="HIGH")
        res.security = rep
        return rep

    monkeypatch.setattr(cli, "inspect_candidate", fake_inspect)
    catalogue = [cat("Risky", "https://x/risky.py")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(
        None, resolutions,
        make_args(install_missing=True, include_suspicious=True), running_py=(3, 11),
    )
    assert resolutions[0].action is ActionType.INSTALL


def test_plan_incompatible_python_is_skipped():
    catalogue = [
        cat("Fancy", "https://x/fancy.py", comments="qbt 5 / Python 3.99+")
    ]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(None, resolutions, make_args(install_missing=True), running_py=(3, 11))
    assert resolutions[0].status is SyncStatus.INCOMPATIBLE
    assert resolutions[0].action is ActionType.SKIP


def test_plan_missing_download_url_is_skipped():
    catalogue = [cat("NoUrl", download_url=None, status="OK")]
    resolutions = cli.reconcile(catalogue, [])
    cli.plan_actions(None, resolutions, make_args(install_missing=True), running_py=(3, 11))
    assert resolutions[0].status is SyncStatus.SKIPPED_WARNING
    assert resolutions[0].action is ActionType.SKIP


# ------------------------------- apply -------------------------------------- #
class FakeQbt:
    def __init__(self, plugins=None, install_result=None, update_bumps=None):
        self.plugins = list(plugins or [])
        # map source_url -> InstalledPlugin to add on install (None = fail verify)
        self.install_result = install_result or {}
        self.update_bumps = update_bumps or {}
        self.install_calls = []
        self.enable_calls = []
        self.update_called = False

    def get_plugins(self):
        return list(self.plugins)

    def install_plugin(self, source):
        self.install_calls.append(source)
        added = self.install_result.get(source, "MISSING")
        if added != "MISSING" and added is not None:
            self.plugins.append(added)

    def wait_for_plugin(self, name, **kwargs):
        for p in self.plugins:
            if p.name == name:
                return p
        return None

    def update_plugins(self):
        self.update_called = True
        for name, newver in self.update_bumps.items():
            for p in self.plugins:
                if p.name == name:
                    p.version = newver

    def enable_plugin(self, name, enable=True):
        self.enable_calls.append((name, enable))
        for p in self.plugins:
            if p.name == name:
                p.enabled = enable


def test_apply_install_success_and_verify():
    c = cat("New", "https://x/newplugin.py", version="1.0")
    res = cli.reconcile([c], [])[0]
    res.action = ActionType.INSTALL
    res.security = _safe_report()

    installed = inst("newplugin", version="1.0", enabled=False)
    qbt = FakeQbt(install_result={"https://x/newplugin.py": installed})
    args = make_args(apply=True, install_missing=True, enable_new=True)

    cli.apply_actions(qbt, [res], args)

    assert res.result is ActionResult.SUCCESS
    assert res.status is SyncStatus.CURRENT
    assert qbt.install_calls == ["https://x/newplugin.py"]
    assert ("newplugin", True) in qbt.enable_calls


def test_apply_install_verify_failure_is_partial():
    c = cat("Ghost", "https://x/ghost.py", version="1.0")
    res = cli.reconcile([c], [])[0]
    res.action = ActionType.INSTALL
    res.security = _safe_report()

    # install_plugin "succeeds" (HTTP 200) but plugin never appears.
    qbt = FakeQbt(install_result={"https://x/ghost.py": None})
    args = make_args(apply=True, install_missing=True)

    cli.apply_actions(qbt, [res], args)
    assert res.result is ActionResult.VERIFY_FAILED
    assert res.error is not None


def test_apply_update_advances_version():
    c = cat("Old", "https://x/oldplugin.py", version="2.0")
    installed = inst("oldplugin", version="1.0")
    res = cli.reconcile([c], [installed])[0]
    assert res.status is SyncStatus.OUTDATED
    res.action = ActionType.UPDATE
    res.security = _safe_report()

    qbt = FakeQbt(plugins=[installed], update_bumps={"oldplugin": "2.0"})
    args = make_args(apply=True)
    cli.apply_actions(qbt, [res], args)
    assert qbt.update_called
    assert res.result is ActionResult.SUCCESS
    assert res.status is SyncStatus.CURRENT


def test_apply_update_falls_back_to_safe_reinstall():
    # updatePlugins leaves the plugin behind; a safe source triggers reinstall.
    c = cat("Old", "https://x/oldplugin.py", version="2.0")
    installed = inst("oldplugin", version="1.0")
    res = cli.reconcile([c], [installed])[0]
    res.action = ActionType.UPDATE
    res.security = _safe_report()

    qbt = FakeQbt(
        plugins=[installed],
        update_bumps={"oldplugin": "1.0"},               # update does not advance
        install_result={"https://x/oldplugin.py": inst("oldplugin", version="2.0")},
    )
    cli.apply_actions(qbt, [res], make_args(apply=True))
    assert qbt.update_called
    assert qbt.install_calls == ["https://x/oldplugin.py"]
    assert res.result is ActionResult.SUCCESS
    assert res.status is SyncStatus.CURRENT


def test_apply_update_no_safe_source_is_verify_failed():
    c = cat("Old", "https://x/oldplugin.py", version="2.0")
    installed = inst("oldplugin", version="1.0")
    res = cli.reconcile([c], [installed])[0]
    res.action = ActionType.UPDATE
    res.security = None  # no inspected source -> reinstall must not proceed

    qbt = FakeQbt(plugins=[installed], update_bumps={"oldplugin": "1.0"})
    cli.apply_actions(qbt, [res], make_args(apply=True))
    assert qbt.update_called
    assert qbt.install_calls == []  # never reinstalled without a safe source
    assert res.result is ActionResult.VERIFY_FAILED
    assert "no safe source" in (res.error or "")


def test_dry_run_marks_planned_actions():
    c = cat("New", "https://x/newplugin.py")
    res = cli.reconcile([c], [])[0]
    res.action = ActionType.INSTALL
    cli.mark_dry_run([res])
    assert res.result is ActionResult.DRY_RUN
