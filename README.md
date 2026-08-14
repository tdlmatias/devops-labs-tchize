# devops-labs-tchize

> A personal DevOps learning-and-sharing monorepo — a curated collection of
> production-quality automation tools, configurations, and experiments built
> while exploring DevOps, Linux automation, and API integration.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![CI](https://github.com/tdlmatias/devops-labs-tchize/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/tdlmatias/devops-labs-tchize/actions/workflows/ci.yml)

---

## Table of contents

- [Overview](#overview)
- [Repository structure](#repository-structure)
- [Projects](#projects)
  - [qBittorrent Search Plugin Synchroniser](#qbittorrent-search-plugin-synchroniser)
  - [Ansible / Vagrant lab](#ansible--vagrant-lab)
- [Getting started](#getting-started)
- [Conventions](#conventions)
- [Continuous integration and security](#continuous-integration-and-security)
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
│
├── qbittorrent-plugin-sync/      # Project: qBittorrent plugin synchroniser
│   ├── README.md                 #   ↳ full project documentation
│   ├── qbt_plugin_sync.py
│   ├── qbt_sync/                 #   ↳ package modules
│   ├── tests/                    #   ↳ offline test suite
│   └── requirements*.txt
│
│   # Ansible / Vagrant lab (currently at the repository root)
├── Vagrantfile                   #   ↳ 3 CentOS 8 VMs (tower + 2 deploy envs)
├── scripts/updateCentos.sh       #   ↳ VM bootstrap provisioner
├── group_vars/all.yml            #   ↳ shared Ansible variables
├── inventories/hosts/hosts       #   ↳ static inventory
├── towerinstall.yml              #   ↳ playbook: install Ansible Tower
├── test_connection.yml           #   ↳ playbook: connectivity check (ping)
├── reboot_Application.yml        #   ↳ playbook: group-based reboot workflow
├── reboot_Application-v2.yml     #   ↳ playbook: rolling-reboot variant
└── manage_app_services.yml       #   ↳ tasks: start/stop app services (parameterized)
```

Each project directory is the source of truth for that project's own setup,
usage, and tests. This root document is the **map**; the project READMEs are the
**territory**.

> **Note:** the Ansible / Vagrant lab currently lives as a set of files at the
> repository root rather than in a dedicated project directory. It is an evolving
> learning scaffold; consolidating it under its own directory is a known future
> cleanup.

## Projects

| Project | Language | Status | Description |
| ------- | -------- | ------ | ----------- |
| [`qbittorrent-plugin-sync`](qbittorrent-plugin-sync/) | Python 3.11+ | ✅ Stable | Safely synchronises the unofficial "Public Sites" qBittorrent search plugins with a running qBittorrent instance via the WebUI API. |
| [Ansible / Vagrant lab](#ansible--vagrant-lab) | Vagrant · Ansible · Bash | 🧪 Experimental | Local multi-VM CentOS 8 lab (Vagrant) with Ansible playbooks for installing Ansible Tower, checking connectivity, and orchestrating application-aware reboots. |

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

### Ansible / Vagrant lab

A local, disposable lab for practising **Ansible** against real virtual
machines. [Vagrant](https://www.vagrantup.com/) brings up three CentOS 8 VMs on
a host-only network — one Ansible Tower control node and two deployment
environments — and a set of playbooks install Tower, verify connectivity, and
orchestrate application-aware reboots.

**Components**

| File | Purpose |
| ---- | ------- |
| `Vagrantfile` | Defines the three VMs (`ansible_tower`, `deploy_env1`, `deploy_env2`) on the `centos/8` box, each with a private-network IP (`192.168.56.10–12`), a bridged public interface (pin the NIC with `VAGRANT_BRIDGE`), and a shell provisioner. |
| `scripts/updateCentos.sh` | VM bootstrap: repoints CentOS 8 repos at the `vault.centos.org` mirror (CentOS 8 is EOL), updates packages, and installs `net-tools` and `python3` with `dnf`. |
| `group_vars/all.yml` | Shared variables: Vagrant user, environment names, private-key paths derived from `playbook_dir`, and the `frontend_services` / `backend_services` lists consumed by the reboot workflow. |
| `inventories/hosts/hosts` | Static inventory grouping the hosts into `instance_group`, `tower`, `workernodes`, and the role groups `frontend` (`deploy_env1`) and `backend` (`deploy_env2`), with per-host private keys. |
| `towerinstall.yml` | Installs EPEL and Ansible, downloads the Ansible Tower setup tarball, unpacks it under `/opt`, and runs the installer. |
| `test_connection.yml` | Pings the `instance_group` hosts to confirm connectivity. |
| `reboot_Application.yml` | Reboot orchestration keyed on inventory group membership (`frontend` / `backend`): stop → reboot → start, via the parameterized task file below. |
| `reboot_Application-v2.yml` | Alternative rolling reboot (`serial: 1`) that reboots hosts one at a time and health-checks each before continuing. |
| `manage_app_services.yml` | Single parameterized task list (`include_tasks` with `app_services` + `app_state` vars) that sets the given services to `started`/`stopped`; used for both frontend and backend, with the relevant `*_services` list passed in. |

> 🧪 **Experimental learning lab.** The playbooks and task files are wired up
> end to end — `reboot_Application.yml` stops, reboots, and restarts each host
> using the `frontend` / `backend` inventory groups. The service lists
> (`frontend_services` / `backend_services` in `group_vars/all.yml`) default to
> empty, so the stop/start steps are no-ops until you populate them with your
> real service names. Prerequisites: [Vagrant](https://www.vagrantup.com/) and a
> provider such as [VirtualBox](https://www.virtualbox.org/).

```bash
# From the repository root
vagrant up                          # bring up the three CentOS 8 VMs
ansible-playbook -i inventories/hosts/hosts test_connection.yml

# Reboot workflow (populate frontend_services / backend_services first to
# actually stop/start apps; otherwise those steps are no-ops):
ansible-playbook -i inventories/hosts/hosts reboot_Application.yml
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

## Continuous integration and security

Pull requests to `master`, pushes to `master`, and manual workflow runs test
`qbittorrent-plugin-sync` on Python 3.11, 3.12, and 3.13. CI compiles the
sources, runs the complete offline test suite, and runs Ruff plus coverage on
Python 3.11. The workflow never starts qBittorrent, executes downloaded plugin
code, or uses repository secrets.

CodeQL runs through GitHub's default code scanning setup, and a separate
workflow audits Python dependencies. Pull requests also use GitHub's dependency
review when that feature is available for the repository. Dependabot proposes controlled weekly updates for Python packages
and GitHub Actions; updates are never merged automatically.

See [`CONTRIBUTING.md`](CONTRIBUTING.md#local-ci-equivalent) for local commands
and the [project README](qbittorrent-plugin-sync/README.md#16-development--testing)
for troubleshooting.

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
