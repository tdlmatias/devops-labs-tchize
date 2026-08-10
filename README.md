# devops-labs-tchize

> A personal DevOps learning-and-sharing monorepo — a curated collection of
> production-quality automation tools, configurations, and experiments built
> while exploring DevOps, Linux automation, and API integration.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## Table of contents

- [Overview](#overview)
- [Repository structure](#repository-structure)
- [Projects](#projects)
  - [qBittorrent Search Plugin Synchroniser](#qbittorrent-search-plugin-synchroniser)
- [Getting started](#getting-started)
- [Conventions](#conventions)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

---

## Overview

This repository stores configurations and code produced as part of a DevOps
learning-and-sharing journey. It is organised as a **monorepo**: each
self-contained tool or experiment lives in its own top-level directory with its
own README, dependencies, and tests, so projects can evolve independently while
sharing a single set of repository-wide conventions and documentation.

The aim is that everything here is **maintainable, conservative, auditable, and
reproducible** — code that is safe to read from, learn from, and run.

## Repository structure

```text
devops-labs-tchize/
├── README.md                     # You are here — repository index & guide
├── LICENSE                       # GNU GPL v3.0
├── CONTRIBUTING.md               # How to propose changes
├── CODE_OF_CONDUCT.md            # Community expectations
├── SECURITY.md                   # How to report vulnerabilities
├── CHANGELOG.md                  # Notable changes, repository-wide
├── .github/                      # Issue/PR templates
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
├── docs/
│   └── ARCHITECTURE.md           # Repo layout + per-project design notes
└── qbittorrent-plugin-sync/      # Project: qBittorrent plugin synchroniser
    ├── README.md                 #   ↳ full project documentation
    ├── qbt_plugin_sync.py
    ├── qbt_sync/                 #   ↳ package modules
    ├── tests/                    #   ↳ offline test suite
    └── requirements*.txt
```

Each project directory is the source of truth for that project's own setup,
usage, and tests. This root document is the **map**; the project READMEs are the
**territory**.

## Projects

| Project | Language | Status | Description |
| ------- | -------- | ------ | ----------- |
| [`qbittorrent-plugin-sync`](qbittorrent-plugin-sync/) | Python 3.11+ | ✅ Stable | Safely synchronises the unofficial "Public Sites" qBittorrent search plugins with a running qBittorrent instance via the WebUI API. |

### qBittorrent Search Plugin Synchroniser

A conservative, auditable, idempotent CLI that keeps the unofficial
**Plugins for Public Sites** qBittorrent search plugins in sync with the plugins
installed in a running qBittorrent instance — over the WebUI API, never by
editing qBittorrent's plugin directories directly.

**Highlights**

- 🛡️ **Safe by default** — a dry run unless `--apply` is given.
- 🔍 **Static security inspection** — downloads candidate plugins into memory,
  parses them with `ast` (never executing), flags dangerous constructs, and
  records a SHA-256 of every inspected source.
- 🌐 **URL hardening** — HTTPS-only, rejects `file://`, localhost, and
  private/internal addresses (including per-redirect-hop validation).
- ♻️ **Idempotent** — a second run on a synced instance reports "no changes".
- 🧪 **73 offline tests** — every qBittorrent mutation is mocked; no test ever
  installs a real plugin.

➡️ **Full documentation:** [`qbittorrent-plugin-sync/README.md`](qbittorrent-plugin-sync/README.md)

```bash
cd qbittorrent-plugin-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 qbt_plugin_sync.py          # dry run — changes nothing
```

## Getting started

Clone the repository and change into the project you want to work with; each
project documents its own prerequisites and setup.

```bash
git clone https://github.com/tdlmatias/devops-labs-tchize.git
cd devops-labs-tchize

# Explore a project
cd qbittorrent-plugin-sync
cat README.md
```

**General prerequisites** vary per project, but most Python projects here target
**Python 3.11+** and isolate dependencies with a virtual environment.

## Conventions

Repository-wide conventions keep every project consistent:

- **One project per top-level directory**, each self-contained with its own
  `README.md`, dependency manifest, and tests.
- **Safe-by-default tooling** — anything that can change external state defaults
  to a dry run / no-op and requires an explicit flag to act.
- **Secrets never committed** — credentials come from environment variables or
  interactive prompts; `.env` files are git-ignored and only `.env.example`
  templates are tracked.
- **Tests are offline and deterministic** — no test performs real network
  mutations or touches a live system.
- **Branch naming:** `type/short-description` (e.g. `feat/...`, `fix/...`,
  `docs/...`). See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Conventional-style commit subjects** — short, imperative mood.

## Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — repository layout and the
  design of each project.
- **Per-project READMEs** — setup, usage, and reference for each tool.
- **[CHANGELOG.md](CHANGELOG.md)** — notable, repository-wide changes.

## Contributing

Contributions, issues, and suggestions are welcome. Please read
**[CONTRIBUTING.md](CONTRIBUTING.md)** for the workflow (branching, commits,
tests, and PR expectations) and **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** for
community expectations. Bug reports and feature requests can be filed using the
[issue templates](.github/ISSUE_TEMPLATE).

## Security

Please **do not** open public issues for security vulnerabilities. See
**[SECURITY.md](SECURITY.md)** for how to report them responsibly. Note that the
qBittorrent plugin tool deliberately handles third-party executable Python code;
read that project's security section before using it.

## License

This repository is licensed under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) for the full text.

`SPDX-License-Identifier: GPL-3.0-or-later`
