from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_theme_package_data_includes_nested_assets():
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = configuration["tool"]["setuptools"]["package-data"]["coldth"]

    assert "static/themes/*/assets/fonts/*" in patterns
    assert (
        ROOT
        / "src/coldth/static/themes/black-1987/assets/fonts/"
        "bitcount-grid-single-latin.woff2"
    ).is_file()
