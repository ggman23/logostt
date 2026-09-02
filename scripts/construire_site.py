#!/usr/bin/env python3
"""Génère les données du site à partir de data/clubs.csv."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttlogos import catalogue, site  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    clubs = catalogue.charger()
    stats = site.construire(clubs)
    logging.info(
        "site généré : %s clubs, %s avec site web, %s avec logo",
        stats["clubs"], stats["sites"], stats["logos"],
    )
    for ligue in stats["ligues"]:
        if ligue["clubs"]:
            logging.info("  %-4s %-28s %4s clubs  %4s logos", ligue["code"], ligue["nom"], ligue["clubs"], ligue["logos"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
