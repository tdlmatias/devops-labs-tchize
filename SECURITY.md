# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
pull requests, or discussions.**

Instead, report them privately through **GitHub Private Vulnerability
Reporting**: open the repository's **Security** tab and choose
**Report a vulnerability**
([direct link](https://github.com/tdlmatias/devops-labs-tchize/security/advisories/new)).
This routes the report privately to the maintainers.

When reporting, please include as much of the following as you can:

- A description of the vulnerability and its impact.
- Step-by-step instructions to reproduce it.
- The affected project/directory, version, or commit.
- Any proof-of-concept code, logs, or screenshots (with secrets redacted).

You can expect an initial acknowledgement of your report, an assessment of the
issue, and — where applicable — a coordinated fix and disclosure. Please give
maintainers reasonable time to address the issue before any public disclosure.

## Supported scope

This repository is a personal learning-and-sharing monorepo. Security fixes are
applied to the `master` branch. There is no long-term-support policy for older
commits; please test against the latest `master`.

## Project-specific security notes

### qbittorrent-plugin-sync

This tool deliberately interacts with **third-party, executable Python code**
(unofficial qBittorrent search plugins). Please keep the following in mind:

- The tool is **safe by default**: it performs a dry run and changes nothing
  unless `--apply` is supplied.
- Before a plugin is handed to qBittorrent, the tool validates its URL
  (HTTPS-only; rejects `file://`, localhost, and private/internal addresses,
  including per-redirect-hop checks), downloads it into memory under a size cap,
  and statically inspects it with Python's `ast` **without executing it**,
  flagging dangerous constructs and recording a SHA-256.
- **This static inspection is a heuristic, not a guarantee.** A malicious plugin
  can pass these checks, and a benign plugin can trip them. Review anything
  flagged, and use the `--include-discouraged` / `--include-suspicious`
  overrides deliberately and sparingly.
- Run qBittorrent and this tool in an appropriately sandboxed, least-privilege
  environment. Never run automated syncs with the discouraged/suspicious
  overrides enabled.

See the project's own
[README security section](qbittorrent-plugin-sync/README.md#2-security-warning)
for full details.

## Handling of secrets

Across this repository:

- Credentials are read from environment variables or interactive prompts, never
  hard-coded.
- Real `.env` files are git-ignored; only `.env.example` templates are tracked.
- Passwords, tokens, session cookies, and authentication headers are never
  written to logs or reports.

If you discover a committed secret, treat it as compromised: report it privately,
and rotate the credential immediately.
