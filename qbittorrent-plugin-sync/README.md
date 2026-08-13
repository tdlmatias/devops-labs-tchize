# qBittorrent Search Plugin Automatic Synchroniser

A conservative, auditable, idempotent command-line tool that keeps the
unofficial **Plugins for Public Sites** qBittorrent search plugins in sync with
the plugins installed in a running qBittorrent instance — over the WebUI API,
never by touching qBittorrent's plugin directories directly.

> **Safe by default.** Running the tool with no flags performs a **DRY RUN**:
> it connects, scans, downloads and inspects candidate sources, and prints the
> actions it *would* take — but changes nothing. Modifications require
> `--apply`.

---

## 1. Purpose

* Detect the qBittorrent application and Web API versions.
* Retrieve the installed search plugins via the WebUI API.
* Download and parse the canonical unofficial-plugins catalogue (MediaWiki
  source), reading **only** the *Plugins for Public Sites* table.
* Reconcile the two: current / outdated / missing / local-only / incompatible /
  flagged / ambiguous.
* Optionally update existing plugins and install missing ones, verifying every
  change by re-querying qBittorrent.
* Produce a clear console summary and an optional JSON report.

It is a **plugin manager**, not a torrent client. It never searches, downloads
torrents, or touches torrent jobs.

## 2. Security warning

**Unofficial qBittorrent search plugins are arbitrary, executable Python code.**
This tool therefore never blindly installs a discovered URL. Before a URL is
handed to qBittorrent it:

* validates the URL (HTTPS only; no `file://`, localhost, private/internal IPs,
  or redirects into private networks);
* downloads the source into memory with a **2 MB** size cap;
* confirms it looks like Python and parses it with `ast` **without executing
  it**;
* statically flags dangerous constructs (`subprocess`, `os.system`, `eval`,
  `exec`, `pickle`, `ctypes`, dynamic imports, socket usage, filesystem
  mutation, …);
* records the **SHA-256** of the exact bytes inspected.

This is a **heuristic** safety net, **not** a guarantee. A malicious plugin can
pass these checks, and a benign plugin can trip them. Review anything flagged,
and only use `--include-suspicious` / `--include-discouraged` deliberately.

## 3. Architecture

```
qbt_plugin_sync.py            # thin entry point
qbt_sync/
├── cli.py            # argparse + orchestration (reconcile→plan→apply→verify)
├── config.py         # env + CLI resolution; password via env or getpass
├── qbittorrent.py    # WebUI API client (persistent Session, SID cookie)
├── catalogue.py      # MediaWiki state-machine parser (Public Sites only)
├── matcher.py        # name normalisation + conservative matching signals
├── versions.py       # packaging.Version comparison (never lexicographic)
├── security.py       # URL validation + AST static inspection + SHA-256
├── httpclient.py     # retrying GETs + validated redirect following
├── models.py         # dataclasses + enums
├── report.py         # JSON report builder
└── logging_config.py # logging + secret redaction filter
```

Data flow: **connect → detect versions → list installed → fetch & parse
catalogue → reconcile → inspect candidates → plan → (apply) → verify → report.**

## 4. Requirements

* Python **3.11+**
* `requests`, `packaging` (runtime)
* `pytest`, `pytest-mock` (development)
* A running qBittorrent with the **WebUI enabled** and the **Search engine**
  available.

## 5. Installation

```bash
cd qbittorrent-plugin-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime only
# or, for development/testing:
pip install -r requirements-dev.txt
```

## 6. qBittorrent WebUI setup

In qBittorrent: **Tools → Options → Web UI**

* Enable the Web User Interface (Remote control).
* Set a username and a strong password.
* Note the address/port (default `http://localhost:8080`).
* The Search engine must be functional (qBittorrent bundles the Python-based
  search subsystem; install Python if prompted).

## 7. Configuration

Environment variables (a `.env` you create from `.env.example`, or your shell):

| Variable       | Default                  | Meaning                         |
| -------------- | ------------------------ | ------------------------------- |
| `QBT_URL`      | `http://localhost:8080`  | WebUI base URL                  |
| `QBT_USERNAME` | `admin`                  | WebUI username                  |
| `QBT_PASSWORD` | *(prompted)*             | WebUI password                  |
| `QBT_TIMEOUT`  | `30`                     | HTTP timeout (seconds)          |

CLI flags `--url`, `--username`, `--timeout` override the environment.

**The password is never accepted as a command-line argument** (so it cannot
leak into shell history or a process list). It comes from `QBT_PASSWORD` or an
interactive `getpass()` prompt, and is never written to logs or the report.

```bash
cp .env.example .env      # then edit .env — never commit it (it is gitignored)
```

## 8. Dry-run usage

```bash
# Fully safe: shows intended actions, changes nothing.
export QBT_URL=http://localhost:8080 QBT_USERNAME=admin
python3 qbt_plugin_sync.py                       # prompts for password
```

## 9. Apply usage

```bash
# Update installed plugins and install missing Public-Site plugins.
python3 qbt_plugin_sync.py --apply --install-missing

# Also enable the plugins this tool newly installs.
python3 qbt_plugin_sync.py --apply --install-missing --enable-new
```

## 10. CLI reference

| Flag                     | Effect                                                        |
| ------------------------ | ------------------------------------------------------------- |
| `--url URL`              | qBittorrent WebUI base URL.                                   |
| `--username NAME`        | WebUI username.                                               |
| `--apply`                | Perform changes (otherwise DRY RUN).                          |
| `--install-missing`      | Install Public-Site plugins that are absent.                 |
| `--no-update-existing`   | Skip updating already-installed plugins.                     |
| `--enable-new`           | Enable newly installed plugins (needs `--apply`).            |
| `--include-discouraged`  | Consider plugins flagged `❗`/`✖` in the catalogue.           |
| `--include-suspicious`   | Consider plugins the scanner rates HIGH risk.                |
| `--only NAME`            | Only plugins whose name contains `NAME` (repeatable).        |
| `--exclude NAME`         | Exclude plugins whose name contains `NAME` (repeatable).     |
| `--json-report PATH`     | Write a JSON report.                                          |
| `--log-file PATH`        | Write a rotating log file.                                    |
| `--timeout SECONDS`      | HTTP timeout.                                                 |
| `--catalogue-url URL`    | Override the catalogue MediaWiki source.                     |
| `--verbose` / `--quiet`  | More / less console output.                                  |
| `--version`              | Print version and exit.                                       |

```bash
# Single plugin, dry run:
python3 qbt_plugin_sync.py --only "Academic Torrents"

# JSON report:
python3 qbt_plugin_sync.py --json-report qbt-plugin-report.json
```

## 11. Plugin warning behaviour

The catalogue marks entries with symbols in the Comments column:

| Symbol | Meaning                | Default behaviour                              |
| ------ | ---------------------- | ---------------------------------------------- |
| `✔`    | working                | eligible for automatic installation            |
| `❗`    | problematic            | **skipped**, with a reason reported            |
| `✖` `❌`| broken                 | **skipped**, with a reason reported            |
| (none) | unknown                | treated conservatively (installable, noted)    |

A `❗`/`✖` plugin is **never silently installed.** `--include-discouraged` makes
them *candidates*, but modification still requires `--apply`. Entries are also
skipped when they have no usable download URL, cannot be downloaded, fail to
parse as Python, score HIGH risk, or appear incompatible with your Python.

## 12. Security scanner limitations

The static scanner **does not execute** plugin code and cannot prove safety. It
catches *obvious* dangerous patterns via AST inspection only. Obfuscated or
novel malicious code may pass. Treat findings as a prompt to review, not a
verdict, and keep qBittorrent and its host appropriately sandboxed.

## 13. JSON reporting

`--json-report PATH` writes a structured, credential-free report:

```json
{
  "timestamp": "2026-08-10T12:00:00+00:00",
  "qbittorrent_version": "v5.0.3",
  "webapi_version": "2.11",
  "python_version": "3.11.15",
  "catalogue_source": "https://raw.githubusercontent.com/.../Unofficial-search-plugins.mediawiki",
  "dry_run": true,
  "summary": { "total": 75, "by_status": {"CURRENT": 40, "MISSING": 30, "...": 5},
               "actions_taken": 0, "failures": 0 },
  "plugins": [
    {
      "catalogue_name": "Academic Torrents",
      "qbittorrent_name": "academictorrents",
      "installed_version": "1.2",
      "catalogue_version": "1.2",
      "download_url": "https://.../academictorrents.py",
      "sha256": "…",
      "status": "CURRENT",
      "warning_level": "OK",
      "security_findings": [],
      "action_attempted": "NONE",
      "result": "NOT_ATTEMPTED",
      "error": null
    }
  ]
}
```

## 14. Cron / systemd examples

**cron** (daily 04:30; note `QBT_PASSWORD` must be provided non-interactively):

```cron
30 4 * * * QBT_URL=http://localhost:8080 QBT_USERNAME=admin QBT_PASSWORD=secret \
  /usr/bin/python3 /opt/qbt-plugin-sync/qbt_plugin_sync.py \
  --apply --install-missing \
  --json-report /var/log/qbt-plugin-sync/latest.json >> /var/log/qbt-plugin-sync/cron.log 2>&1
```

**systemd** — `/etc/systemd/system/qbt-plugin-sync.service`:

```ini
[Unit]
Description=qBittorrent search-plugin synchroniser
After=network-online.target

[Service]
Type=oneshot
User=qbt
EnvironmentFile=/etc/qbt-plugin-sync.env      # QBT_URL / QBT_USERNAME / QBT_PASSWORD
ExecStart=/usr/bin/python3 /opt/qbt-plugin-sync/qbt_plugin_sync.py \
  --apply --install-missing \
  --json-report /var/log/qbt-plugin-sync/latest.json
```

`/etc/systemd/system/qbt-plugin-sync.timer`:

```ini
[Unit]
Description=Run qBittorrent plugin sync daily

[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now qbt-plugin-sync.timer
```

> Do **not** add `--include-discouraged` (or `--include-suspicious`) to
> scheduled runs. Keep automated execution conservative.

Protect the environment file: `chmod 600 /etc/qbt-plugin-sync.env`.

## 15. Troubleshooting

| Symptom                                   | Likely cause / fix                                             |
| ----------------------------------------- | ------------------------------------------------------------- |
| exit 3, "Could not connect"               | qBittorrent not running / wrong `QBT_URL`.                     |
| exit 3, "invalid username or password"    | Bad credentials.                                              |
| exit 3, HTTP 403 on login                 | IP banned after failed attempts; wait / clear the ban.        |
| exit 3, "search plugins endpoint … unavailable" | Search engine not available in qBittorrent.            |
| exit 4, catalogue error                   | GitHub unreachable or catalogue format changed.               |
| A plugin stays `MANUAL_REVIEW`            | Name too ambiguous to match safely; handle it manually.       |
| A plugin stays `SKIPPED_WARNING`          | `❗`/`✖`, no URL, or invalid Python — see the report `notes`.  |

Exit codes: `0` success/dry-run · `1` partial plugin failures · `2` config
error · `3` qBittorrent connection/auth · `4` catalogue retrieval/parsing.

## 16. Development / testing

```bash
pip install -r requirements-dev.txt
python3 -m compileall .
pytest -v
```

Tests are fully offline: every qBittorrent mutation is mocked and **no test
ever installs a real plugin**. Coverage includes catalogue parsing, public-table
detection, warning detection, URL validation, version comparison, name
normalisation, ambiguous matching, the security scanner, authentication,
installed-plugin retrieval, dry-run, installation verification, partial failure
and malformed catalogue rows.

## 17. Cleanup and uninstall

This tool is deliberately light-footed, but a full run (and especially the
scheduled-automation setup) can leave a few artefacts on your machine. This
section explains exactly what may be left behind and how to remove it.

> **Important:** cleanup here means removing *this tool's own* files, caches,
> logs, and credentials. It does **not** remove the search plugins the tool
> installed **inside qBittorrent** — those live in qBittorrent and keep working.
> See [Reverting qBittorrent plugin changes](#reverting-qbittorrent-plugin-changes)
> if you also want to undo the plugin installs.

### What the tool leaves behind

| Artefact | When it is created | Location (default) |
| -------- | ------------------ | ------------------ |
| Candidate plugin source | Only in memory during inspection | *nothing on disk* |
| JSON report | With `--json-report PATH` | the path you gave |
| Log file (rotating) | With `--log-file PATH` | the path you gave (`*.log`, plus `.1`/`.2`/`.3`) |
| Python bytecode cache | On any run | `qbt_sync/__pycache__/`, `tests/__pycache__/` |
| Virtual environment | If you created one | `.venv/` |
| pytest cache | After running tests | `.pytest_cache/` |
| Environment variables | If you exported them | your shell session (`QBT_URL`, `QBT_USERNAME`, `QBT_PASSWORD`, `QBT_TIMEOUT`) |
| `.env` file | If you created one | `qbittorrent-plugin-sync/.env` (git-ignored) |

Plugin sources are downloaded into memory only — the tool never writes plugin
`.py` files to a temporary directory, so there is no scratch/temp state to clear.

### Local (one-off run) cleanup

A helper script is provided that is **safe by default** (it prints what it would
remove and does nothing unless you pass `--yes`), mirroring the tool's own
dry-run philosophy:

```bash
# From the project directory:
bash scripts/cleanup.sh            # dry run — shows what would be removed
bash scripts/cleanup.sh --yes      # actually remove local artefacts
```

Or do it by hand:

```bash
# Byte-code and test caches
find . -type d -name '__pycache__' -exec rm -rf {} +
rm -rf .pytest_cache

# Virtual environment
rm -rf .venv

# Reports and logs you generated (adjust paths to what you used)
rm -f qbt-plugin-report.json
rm -f qbt-plugin-sync.log qbt-plugin-sync.log.*
```

### Clear credentials from your environment

The password is the most sensitive artefact. Remove it from your shell and
delete any local `.env`:

```bash
# Unset for the current shell session
unset QBT_PASSWORD QBT_USERNAME QBT_URL QBT_TIMEOUT

# Remove a local .env if you created one
rm -f .env
```

If you exported these in a shell profile (`~/.bashrc`, `~/.profile`, …), edit
that file to remove the lines as well. If the password was ever typed on a
command line or stored in history, clear it:

```bash
history -d <line-number>     # or trim ~/.bash_history, then: history -c
```

### Scheduled automation cleanup

If you followed [§14](#14-cron--systemd-examples) to run the tool on a schedule,
remove those pieces too.

**systemd timer + service:**

```bash
sudo systemctl disable --now qbt-plugin-sync.timer
sudo rm -f /etc/systemd/system/qbt-plugin-sync.timer \
           /etc/systemd/system/qbt-plugin-sync.service
sudo systemctl daemon-reload
```

**cron entry:** remove the line you added with `crontab -e` (or `sudo crontab -e`).

**Log directory and the credentials env file** (the env file contains your
password — remove it securely):

```bash
sudo rm -rf /var/log/qbt-plugin-sync/
sudo shred -u /etc/qbt-plugin-sync.env   # or: sudo rm -f /etc/qbt-plugin-sync.env
```

### Reverting qBittorrent plugin changes

The tool never uninstalls plugins, so undoing installs is a manual, deliberate
step. Use the JSON report to see exactly what was installed
(`action_attempted: "INSTALL"`, `result: "SUCCESS"`), then in qBittorrent:

> **View → Search Engine** (enable the Search tab) **→ Search plugins…** →
> right-click a plugin → **Uninstall**.

Only remove plugins you intended to; leave anything reported as `LOCAL_ONLY`
(plugins that were already there and are not part of this catalogue).

### Full uninstall

To remove the tool entirely, delete its directory (after the automation and
credential cleanup above):

```bash
cd ..
rm -rf qbittorrent-plugin-sync
```

No system-wide packages are installed by the tool itself; if you installed the
Python dependencies into a global environment rather than a `.venv`, uninstall
them with `pip uninstall requests packaging` (only if nothing else needs them).

---

### Design guarantees

* **Idempotent** — a second run on a synced instance reports "no changes".
* **Non-destructive** — never uninstalls or replaces `LOCAL_ONLY` plugins;
  updates prefer qBittorrent's own updater and only reinstall from a *safe,
  inspected* source when still behind.
* **Auditable** — every inspected source has a recorded SHA-256; every action
  has a logged, verified result.

_Licensed under GPL-3.0-or-later (see `LICENSE`)._
