# Contributing to devops-labs-tchize

Thanks for your interest in contributing! This repository is a DevOps
learning-and-sharing monorepo, and improvements — bug fixes, new projects,
documentation, and tests — are all welcome.

Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Repository layout](#repository-layout)
- [Development workflow](#development-workflow)
- [Branch naming](#branch-naming)
- [Commit messages](#commit-messages)
- [Coding standards](#coding-standards)
- [Testing](#testing)
- [Pull requests](#pull-requests)
- [Adding a new project](#adding-a-new-project)
- [Reporting bugs & requesting features](#reporting-bugs--requesting-features)

## Ways to contribute

- **Report a bug** or **request a feature** via the
  [issue templates](.github/ISSUE_TEMPLATE).
- **Improve documentation** — READMEs, architecture notes, examples.
- **Fix a bug** or **add a feature** to an existing project.
- **Add a new project** under its own top-level directory.

## Repository layout

This is a monorepo. Each project is self-contained in its own top-level
directory with its own `README.md`, dependency manifest, and tests. Keep changes
scoped to the project you are working on unless you are intentionally updating
repository-wide documentation or conventions.

## Development workflow

1. **Fork** the repository (external contributors) or create a branch (with
   write access).
2. **Create a feature branch** from `master` (see [branch naming](#branch-naming)).
3. **Make your changes**, keeping commits focused and logically grouped.
4. **Add or update tests** so the change is covered.
5. **Run the project's checks** locally (see [testing](#testing)).
6. **Open a pull request** against `master` and fill in the template.

```bash
git checkout master
git pull origin master
git checkout -b feat/my-change
# ... work, commit ...
git push -u origin feat/my-change
```

## Branch naming

Use a short, descriptive, kebab-case branch name prefixed with the change type:

| Prefix     | Use for                                  |
| ---------- | ---------------------------------------- |
| `feat/`    | A new feature or project                 |
| `fix/`     | A bug fix                                |
| `docs/`    | Documentation-only changes               |
| `test/`    | Adding or improving tests                |
| `refactor/`| Internal changes with no behaviour change|
| `chore/`   | Tooling, dependencies, housekeeping      |

Example: `feat/qbt-enable-private-sites`, `docs/root-readme`.

## Commit messages

Write clear, imperative-mood subject lines, following a
[Conventional Commits](https://www.conventionalcommits.org/)-style convention:

```text
<type>: <short summary in the imperative mood>

<optional body explaining what and why, wrapped at ~72 columns>
```

- Keep the subject under ~72 characters.
- Explain **why** in the body when the change isn't self-evident.
- One logical change per commit where practical.

## Coding standards

- **Python:** target **3.11+**. Prefer the standard library and a minimal set of
  well-known dependencies. Use type hints, docstrings on public functions, and
  clear names. Match the style of the surrounding code.
- **Safety first:** any operation that mutates external state must default to a
  dry run / no-op and require an explicit flag to act.
- **No secrets in code or history:** read credentials from environment variables
  or interactive prompts. Never commit a real `.env`; provide a `.env.example`
  template instead. Never log passwords, tokens, cookies, or auth headers.
- **Deterministic, offline tests:** tests must not perform real network
  mutations or touch live systems.

## Testing

Each project documents its own test commands. For the Python projects:

```bash
cd <project-dir>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m compileall .
pytest -v
```

All tests must pass before a pull request is merged. New code should come with
new tests.

## Pull requests

- Target the `master` branch.
- Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md).
- Keep PRs focused; smaller PRs are reviewed faster.
- Describe **what** changed and **why**, and note how you tested it.
- Ensure `compileall`/`pytest` (or the project's equivalent checks) pass.
- Update the relevant `README.md` and [CHANGELOG.md](CHANGELOG.md) when your
  change is user-visible.

## Adding a new project

When adding a new project:

1. Create a new top-level directory named after the project.
2. Include, at minimum: a `README.md`, a dependency manifest (e.g.
   `requirements.txt`), tests, and — if the project handles secrets — a
   `.env.example` and appropriate `.gitignore` entries.
3. Add a row to the **Projects** table in the [root README](README.md).
4. Add a short design note to [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Reporting bugs & requesting features

Use the [issue templates](.github/ISSUE_TEMPLATE). For bugs, include steps to
reproduce, expected vs. actual behaviour, and your environment. For security
issues, **do not** open a public issue — follow [SECURITY.md](SECURITY.md).
