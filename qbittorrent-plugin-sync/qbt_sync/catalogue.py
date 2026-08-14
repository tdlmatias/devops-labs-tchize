"""Parser for the unofficial qBittorrent search-plugins catalogue.

We deliberately parse the canonical MediaWiki source rather than scraping
rendered GitHub HTML. A small state-machine walks the wiki table; light regex
is used only for extracting links and stripping inline markup within a cell,
never for structural table parsing.

Only the ``== Plugins for Public Sites ==`` section is parsed. Parsing stops at
the next level-2 section (e.g. ``== Plugins for Private Sites ==``).
"""

from __future__ import annotations

import re
from typing import Optional

import requests

from .httpclient import fetch_text
from .logging_config import get_logger
from .matcher import normalize_name
from .models import CataloguePlugin, WarningLevel

logger = get_logger()

PUBLIC_SECTION_TITLE = "Plugins for Public Sites"

# A level-2 heading like "== Title ==" (exactly two leading '=', not "===").
_HEADING_RE = re.compile(r"^==(?!=)\s*(.+?)\s*==\s*$")
# Image / internal links: [[ ... ]] (favicons, download-icon gifs).
_DOUBLE_BRACKET_RE = re.compile(r"\[\[[^\]]*\]\]")
# External link: [https://url optional label]
_EXTERNAL_LINK_RE = re.compile(r"\[(https?://[^\s\]]+)(?:\s+([^\]]*))?\]")
_BARE_URL_RE = re.compile(r"https?://[^\s\]|]+")

_EXPECTED_COLUMNS = 6  # Search Engine, Author, Version, Last update, Download, Comments


class CatalogueParseError(Exception):
    """Raised when the catalogue cannot be located or parsed (exit code 4)."""


class CatalogueFetchError(Exception):
    """Raised when the catalogue source cannot be retrieved (exit code 4)."""


# --------------------------------------------------------------------------- #
# Cell-level helpers
# --------------------------------------------------------------------------- #
def _strip_double_brackets(text: str) -> str:
    return _DOUBLE_BRACKET_RE.sub(" ", text)


def _external_links(cell: str) -> list[tuple[str, str]]:
    """Return ``(url, label)`` pairs from a cell, ignoring [[image]] links."""

    cleaned = _strip_double_brackets(cell)
    links = [
        (m.group(1), (m.group(2) or "").strip())
        for m in _EXTERNAL_LINK_RE.finditer(cleaned)
    ]
    if links:
        return links
    # Fall back to a bare URL if present.
    bare = _BARE_URL_RE.search(cleaned)
    return [(bare.group(0), "")] if bare else []


def _plain_text(cell: str) -> str:
    """Reduce a wiki cell to readable plain text."""

    text = _strip_double_brackets(cell)
    text = _EXTERNAL_LINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = text.replace("'''", "").replace("''", "").replace("**", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _detect_warning(*cells: str) -> WarningLevel:
    joined = " ".join(cells)
    if "✖" in joined or "❌" in joined:
        return WarningLevel.BROKEN
    if "❗" in joined:
        return WarningLevel.DISCOURAGED
    if "✔" in joined:
        return WarningLevel.OK
    return WarningLevel.UNKNOWN


def _pick_download_url(links: list[tuple[str, str]]) -> Optional[str]:
    """Prefer a direct ``.py`` link; otherwise the first available link."""

    for url, _label in links:
        if url.lower().endswith(".py"):
            return url
    return links[0][0] if links else None


# --------------------------------------------------------------------------- #
# Structural, state-machine table extraction
# --------------------------------------------------------------------------- #
def _extract_public_section(text: str) -> list[str]:
    """Return the lines belonging to the Public Sites section (heading excluded)."""

    lines = text.splitlines()
    start: Optional[int] = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and m.group(1).strip().lower() == PUBLIC_SECTION_TITLE.lower():
            start = i + 1
            break
    if start is None:
        raise CatalogueParseError(
            f"Section '== {PUBLIC_SECTION_TITLE} ==' not found in catalogue."
        )

    end = len(lines)
    for j in range(start, len(lines)):
        if _HEADING_RE.match(lines[j]):
            end = j
            break
    return lines[start:end]


def _split_inline_cells(cell_line: str, sep: str) -> list[str]:
    """Split a cell line on the MediaWiki inline separator (``||`` or ``!!``)."""

    body = cell_line[1:]  # drop the single leading '|' or '!'
    return [part.strip() for part in body.split(sep)]


def _parse_rows(section_lines: list[str]) -> list[list[str]]:
    """Walk the first wiki table in the section and return its data rows."""

    rows: list[list[str]] = []
    current: list[str] = []
    in_table = False
    saw_table = False

    def flush() -> None:
        nonlocal current
        if current:
            rows.append(current)
        current = []

    for raw in section_lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("{|"):
            in_table = True
            saw_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|}"):
            flush()
            break
        if line.startswith("|+"):  # table caption
            continue
        if line.startswith("|-"):  # row separator
            flush()
            continue
        if line.startswith("!"):  # header cells — skip, they define no data row
            continue
        if line.startswith("|"):
            current.extend(_split_inline_cells(line, "||"))
            continue
        # Continuation of a previous cell (wrapped line): append to last cell.
        if current:
            current[-1] = f"{current[-1]} {line}".strip()

    if not saw_table:
        raise CatalogueParseError("No wiki table found in the Public Sites section.")
    return rows


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse_catalogue(text: str) -> list[CataloguePlugin]:
    """Parse catalogue MediaWiki text into a list of :class:`CataloguePlugin`.

    Malformed rows are logged and skipped rather than aborting the whole parse.
    """

    section_lines = _extract_public_section(text)
    rows = _parse_rows(section_lines)

    plugins: list[CataloguePlugin] = []
    for index, cells in enumerate(rows):
        if len(cells) < _EXPECTED_COLUMNS:
            logger.warning(
                "Skipping malformed catalogue row %d (%d/%d columns): %r",
                index,
                len(cells),
                _EXPECTED_COLUMNS,
                cells,
            )
            continue

        engine_cell, author_cell, version_cell, update_cell, download_cell, comments_cell = (
            cells[0],
            cells[1],
            cells[2],
            cells[3],
            cells[4],
            cells[5],
        )

        engine_links = _external_links(engine_cell)
        display_name = ""
        site_url: Optional[str] = None
        if engine_links:
            site_url = engine_links[0][0]
            display_name = engine_links[0][1] or _plain_text(engine_cell)
        else:
            display_name = _plain_text(engine_cell)

        if not display_name:
            logger.warning("Skipping catalogue row %d with no engine name.", index)
            continue

        author_links = _external_links(author_cell)
        repository_url = author_links[0][0] if author_links else None

        version = _plain_text(version_cell) or None
        last_update = _plain_text(update_cell) or None

        download_url = _pick_download_url(_external_links(download_cell))

        warning = _detect_warning(comments_cell, engine_cell, version_cell)
        comments = _plain_text(comments_cell)

        plugins.append(
            CataloguePlugin(
                display_name=display_name,
                normalized_name=normalize_name(display_name),
                repository_url=repository_url,
                version=version,
                last_update=last_update,
                download_url=download_url,
                comments=comments,
                status=warning.value,
                site_url=site_url,
            )
        )

    logger.info("Parsed %d Public Sites catalogue entries.", len(plugins))
    return plugins


def fetch_catalogue(
    session: requests.Session, url: str, *, timeout: float
) -> list[CataloguePlugin]:
    """Download and parse the catalogue from ``url``."""

    try:
        text = fetch_text(session, url, timeout=timeout, max_bytes=8 * 1024 * 1024)
    except Exception as exc:  # noqa: BLE001 - normalise to a domain error
        raise CatalogueFetchError(f"Failed to retrieve catalogue: {exc}") from exc
    return parse_catalogue(text)
