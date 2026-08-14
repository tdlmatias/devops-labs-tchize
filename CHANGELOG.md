# Changelog

All notable, repository-wide changes are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this repository aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for tagged releases.
Individual projects may additionally maintain their own history in their READMEs.

## [Unreleased]

### Added
- **Ansible / Vagrant lab:** a local multi-VM CentOS 8 environment
  (`Vagrantfile`) provisioning an Ansible Tower control node and two deployment
  targets, with playbooks for installing Tower (`towerinstall.yml`), checking
  connectivity (`test_connection.yml`), and orchestrating application-aware
  reboots (`reboot_Application.yml` and a rolling-reboot `reboot_Application-v2.yml`),
  plus shared `group_vars`, a static inventory, and a `dnf`-based VM bootstrap
  script.
- Documentation for the Ansible / Vagrant lab: a Projects entry and section in
  the root `README.md` and a design section in `docs/ARCHITECTURE.md` covering
  topology, file layout, and the reboot-orchestration approaches.
- GitHub Actions CI for Python 3.11, 3.12, and 3.13 with offline tests,
  compilation, focused Ruff linting, and baseline coverage reporting.
- Dependency-review and Python dependency-audit automation (with CodeQL via
  GitHub's default code scanning setup), plus grouped weekly Dependabot updates
  for Python and GitHub Actions.
- Contributor and security documentation for local CI reproduction, branch
  protection, workflow troubleshooting, and current release limitations.
- Repository-wide documentation set following common open-source best practices:
  a comprehensive root `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, this `CHANGELOG.md`, `docs/ARCHITECTURE.md`, and GitHub issue
  and pull-request templates under `.github/`.
- **`qbittorrent-plugin-sync`:** a "Cleanup and uninstall" section in the
  project README covering local artefacts, credential clearing, scheduled-
  automation teardown, reverting qBittorrent plugin installs, and full
  uninstall — plus a safe-by-default `scripts/cleanup.sh` helper (dry run
  unless `--yes`).

## [2026-08-10]

### Added
- **`qbittorrent-plugin-sync`** — a conservative, auditable, idempotent Python
  3.11+ CLI that synchronises the unofficial "Plugins for Public Sites"
  qBittorrent search plugins with a running qBittorrent instance via the WebUI
  API. Safe by default (dry run unless `--apply`), with static `ast`-based
  security inspection of candidate plugins, URL hardening, conservative version
  and name matching, JSON reporting, and a 73-test offline suite. (PR #1)

## [Initial commit]

### Added
- Repository initialised with a project description, GNU GPL v3.0 `LICENSE`, and
  a base `.gitignore`.

[Unreleased]: https://github.com/tdlmatias/devops-labs-tchize/compare/master...HEAD
