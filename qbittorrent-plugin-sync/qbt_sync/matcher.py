"""Conservative matching between catalogue entries and installed plugins.

Plugin names rarely match across the two data sources verbatim, so we combine
several independent signals (exact name, normalised name, download-filename
stem, full name, website hostname). Each signal carries a confidence weight;
when nothing clears the acceptance threshold the pairing is deliberately left
for MANUAL_REVIEW rather than guessed at.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

# Confidence threshold below which a match must not drive automatic action.
MATCH_THRESHOLD = 0.75

_PUNCT_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACE_RE = re.compile(r"[\s-]+")
_TLD_SUFFIXES = (".com", ".org", ".net", ".io", ".to", ".cc", ".me", ".tv", ".eu")


def normalize_name(name: Optional[str]) -> str:
    """Normalise a plugin/site name for comparison.

    Lowercases, strips punctuation, collapses whitespace/hyphens to single
    underscores, and removes a trailing common TLD suffix only when doing so is
    unambiguous (i.e. the name is a single hostname-like token).
    """

    if not name:
        return ""
    text = name.strip().lower()
    # Drop a trailing TLD-like suffix on single-token names (e.g. "acg.rip").
    for suffix in _TLD_SUFFIXES:
        if text.endswith(suffix) and " " not in text:
            text = text[: -len(suffix)]
            break
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub("_", text.strip())
    return text.strip("_")


def filename_stem(url: Optional[str]) -> str:
    """Return the normalised filename stem of a download URL (e.g. ``acgrip``)."""

    if not url:
        return ""
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1]
    if base.endswith(".py"):
        base = base[:-3]
    return normalize_name(base)


def hostname_token(url: Optional[str]) -> str:
    """Return a normalised token derived from a URL hostname (sans ``www.``)."""

    if not url:
        return ""
    host = urlparse(url).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return normalize_name(host)


def _score_pair(catalogue, installed) -> tuple[float, str]:
    """Return the best ``(confidence, signal)`` for a catalogue/installed pair."""

    cat_norm = catalogue.normalized_name
    cat_stem = filename_stem(catalogue.download_url)
    cat_host = hostname_token(catalogue.site_url)

    inst_name = normalize_name(installed.name)
    inst_full = normalize_name(installed.full_name)
    inst_host = hostname_token(installed.site_url)

    candidates: list[tuple[float, str]] = []

    # 1. Exact qBittorrent plugin name vs. download filename stem (strongest).
    if cat_stem and inst_name and cat_stem == inst_name:
        candidates.append((1.0, "filename==name"))

    # 2. Normalised catalogue name vs. plugin name.
    if cat_norm and inst_name and cat_norm == inst_name:
        candidates.append((0.95, "normalized==name"))

    # 3. Normalised catalogue name vs. full name.
    if cat_norm and inst_full and cat_norm == inst_full:
        candidates.append((0.9, "normalized==fullname"))

    # 4. Filename stem vs. full name.
    if cat_stem and inst_full and cat_stem == inst_full:
        candidates.append((0.85, "filename==fullname"))

    # 5. Website hostname agreement.
    if cat_host and inst_host and cat_host == inst_host:
        candidates.append((0.9, "hostname==hostname"))
    if cat_host and inst_name and cat_host == inst_name:
        candidates.append((0.85, "hostname==name"))

    # 6. Substring containment as a weak, sub-threshold hint only.
    if cat_norm and inst_name and (cat_norm in inst_name or inst_name in cat_norm):
        candidates.append((0.6, "substring"))

    if not candidates:
        return (0.0, "")
    return max(candidates, key=lambda c: c[0])


def match_installed(
    catalogue, installed_plugins
) -> tuple[Optional[object], float, str]:
    """Find the best installed plugin for a catalogue entry.

    :returns: ``(installed_plugin_or_None, confidence, signal)``. The plugin is
        returned even below threshold so the caller can decide to route it to
        MANUAL_REVIEW; the confidence value carries that decision.
    """

    best_plugin = None
    best_score = 0.0
    best_signal = ""
    for installed in installed_plugins:
        score, signal = _score_pair(catalogue, installed)
        if score > best_score:
            best_plugin, best_score, best_signal = installed, score, signal
    return best_plugin, best_score, best_signal


def is_confident(confidence: float) -> bool:
    """Whether a confidence score is high enough to drive automatic action."""

    return confidence >= MATCH_THRESHOLD
