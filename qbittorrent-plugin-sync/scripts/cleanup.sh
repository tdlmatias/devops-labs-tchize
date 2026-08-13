#!/usr/bin/env bash
#
# cleanup.sh — remove local artefacts left by qbt_plugin_sync.
#
# Safe by default: with no arguments it performs a DRY RUN and only prints what
# it would remove. Pass --yes (or -y) to actually delete. This mirrors the
# tool's own dry-run-by-default philosophy.
#
# It removes LOCAL artefacts only:
#   - Python byte-code caches (__pycache__)
#   - the pytest cache (.pytest_cache)
#   - a local virtual environment (.venv)
#   - generated reports (qbt-plugin-report.json)
#   - generated logs (*.log and rotated *.log.N)
#   - a local .env file (contains credentials — you are asked to confirm)
#
# It does NOT touch qBittorrent, scheduled systemd/cron jobs, /var/log, or any
# system-wide files. See the "Cleanup and uninstall" section of README.md for
# those steps.

set -euo pipefail

APPLY=0
REMOVE_ENV=0

usage() {
    cat <<'USAGE'
Usage: cleanup.sh [--yes] [--include-env] [--help]

  (no flags)     Dry run: print what would be removed, delete nothing.
  --yes, -y      Actually remove the local artefacts.
  --include-env  Also remove a local .env file (contains credentials).
  --help, -h     Show this help.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --yes|-y) APPLY=1 ;;
        --include-env) REMOVE_ENV=1 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

# Resolve the project root (the parent directory of this script's dir).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ "$APPLY" -eq 1 ]; then
    echo "MODE: APPLY — removing local artefacts under $PROJECT_ROOT"
else
    echo "MODE: DRY RUN — nothing will be removed (pass --yes to apply)"
fi
echo

# Build the list of targets that actually exist.
targets=()

while IFS= read -r -d '' d; do
    targets+=("$d")
done < <(find . -type d -name '__pycache__' -print0 2>/dev/null)

for path in .pytest_cache .venv qbt-plugin-report.json; do
    [ -e "$path" ] && targets+=("$path")
done

# Log files (including rotated .1/.2/.3), if any.
while IFS= read -r -d '' f; do
    targets+=("$f")
done < <(find . -maxdepth 2 -type f \( -name '*.log' -o -name '*.log.*' \) -print0 2>/dev/null)

# .env is only included when explicitly requested (it holds credentials).
if [ "$REMOVE_ENV" -eq 1 ] && [ -e ".env" ]; then
    targets+=(".env")
fi

if [ "${#targets[@]}" -eq 0 ]; then
    echo "Nothing to clean — no local artefacts found."
    exit 0
fi

for t in "${targets[@]}"; do
    if [ "$APPLY" -eq 1 ]; then
        rm -rf -- "$t"
        echo "removed:      $t"
    else
        echo "would remove: $t"
    fi
done

echo
if [ "$APPLY" -eq 1 ]; then
    echo "Done. Remember to also clear credentials from your shell:"
    echo "    unset QBT_PASSWORD QBT_USERNAME QBT_URL QBT_TIMEOUT"
    if [ "$REMOVE_ENV" -eq 0 ] && [ -e ".env" ]; then
        echo "A .env file was kept (use --include-env to remove it)."
    fi
else
    echo "Dry run complete. Re-run with --yes to remove the above."
    echo "Add --include-env to also remove a local .env credentials file."
fi
