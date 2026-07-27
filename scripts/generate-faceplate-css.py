#!/usr/bin/env python3
"""Generate semantic starter CSS from a Coldth faceplate document."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from coldth.themes import generate_faceplate_css


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate visual-only CSS hooks for a Coldth faceplate."
    )
    parser.add_argument("faceplate", type=Path, help="Input faceplate YAML")
    parser.add_argument("output", type=Path, help="Output CSS file")
    args = parser.parse_args()

    document = yaml.safe_load(args.faceplate.read_text(encoding="utf-8"))
    css = generate_faceplate_css(document)
    args.output.write_text(css, encoding="utf-8")


if __name__ == "__main__":
    main()
