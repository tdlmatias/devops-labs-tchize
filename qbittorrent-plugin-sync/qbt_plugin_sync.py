#!/usr/bin/env python3
"""Entry point for the qBittorrent Search Plugin Automatic Synchroniser.

Run ``python3 qbt_plugin_sync.py --help`` for usage. Safe by default: a DRY RUN
unless ``--apply`` is supplied.
"""

from __future__ import annotations

import sys

from qbt_sync.cli import main

if __name__ == "__main__":
    sys.exit(main())
