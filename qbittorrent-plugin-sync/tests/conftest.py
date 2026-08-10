"""Shared pytest fixtures and path setup."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure the project root (containing the qbt_sync package) is importable when
# tests are run from anywhere.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture
def fixtures_dir() -> str:
    return FIXTURES_DIR


@pytest.fixture
def sample_catalogue_text() -> str:
    path = os.path.join(FIXTURES_DIR, "sample_catalogue.mediawiki")
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()
