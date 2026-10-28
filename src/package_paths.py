"""Resolve bundled package paths (conversion table, etc.)."""

from __future__ import annotations

from pathlib import Path


def default_conversion_table_path() -> Path:
    """Return path to ``sur_nwb_conversion_table.csv``.

    Resolution order (first existing file wins):

    1. Repo-root CSV next to the ``src/`` package directory (editable install /
       this checkout; Task 1 source of truth).
    2. CSV co-located with this package (wheel / non-editable install via
       hatch force-include).
    """
    package_dir = Path(__file__).resolve().parent
    repo_root_candidate = package_dir.parent / "sur_nwb_conversion_table.csv"
    if repo_root_candidate.is_file():
        return repo_root_candidate

    packaged_candidate = package_dir / "sur_nwb_conversion_table.csv"
    if packaged_candidate.is_file():
        return packaged_candidate

    raise FileNotFoundError(
        "Could not find sur_nwb_conversion_table.csv next to the repo root "
        "or inside the installed src package. Pass an explicit path, or "
        "reinstall the package so the table is included."
    )
