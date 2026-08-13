# Changelog

All notable, repository-wide changes are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this repository aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for tagged releases.
Individual projects may additionally maintain their own history in their READMEs.

## [Unreleased]

### Added
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
