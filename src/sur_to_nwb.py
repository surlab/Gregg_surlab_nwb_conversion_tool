"""Integrated SurLab -> NWB conversion driven by sur_nwb_conversion_table.csv.

Design (see for_cursor/task2_implementation_decisions_and_answers.txt section E):

- One integrated pass builds a single NWBFile in memory and writes once.
- The conversion table is the placement spec; ``nwb_location`` + ``nwb_fieldname``
  are read literally (Task 1 owns ambiguous targets).
- Datatype presence is inferred from session-dir filenames first; sessionInfo
  flags are secondary for validation.
- ``dev_max_stage`` (CLI ``--stage``) is a development filter only; default runs
  all implemented modality handlers.
- Unhandled table rows are reported as table gaps, never silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.conversion_table import (
    expand_rows_for_datatypes,
    filter_dev_stage,
    is_informational_row,
    parse_stage,
    read_conversion_table,
    row_applies_to_session,
)
from src.nwb_beh_events import apply_beh_events
from src.nwb_beh_tseries import apply_beh_tseries
from src.nwb_lfp import apply_lfp
from src.nwb_spike_times import apply_spike_times, warn_zero_time_reference
from src.nwb_spike_waves import apply_spike_waves
from src.nwb_traces import apply_traces
from src.nwb_trial_info import apply_trial_info
from src.session_record import load_session_record
from src.surlab_paths import discover_datatypes_from_files, dataset_id_from_dir
from src.table_placement import PlacementContext, create_nwbfile_from_table, record_table_gap

logger = logging.getLogger(__name__)

# Datatypes with dedicated forward handlers (conversion-table stage numbers are
# development labels only; default runs all of these when files are present).
IMPLEMENTED_DATATYPES = {"spikeTimes", "trialInfo", "lfp", "spikeWaves"}
IMPLEMENTED_DATATYPE_SUFFIXES = ("_traces", "_behTSeries", "_behEvents")


@dataclass
class ConversionConfig:
    """User-configurable settings for a conversion run."""

    dataset_dir: Path
    session_dir: Path
    conversion_table_path: Path
    output_nwb_path: Path
    dev_max_stage: Optional[int] = None
    timezone_name: str = "UTC"


@dataclass
class ConversionResult:
    """Summary of one conversion run."""

    output_nwb_path: Path
    table_gaps: List[str]
    warnings: List[str]


def _report_unimplemented_rows(context: PlacementContext, discovered_datatypes: set[str]) -> None:
    for row in context.table_rows:
        if is_informational_row(row):
            continue
        datatype_id = str(row.get("datatype_id", "")).strip() or None
        if not row_applies_to_session(row, discovered_datatypes, datatype_id=datatype_id):
            continue
        row_type = str(row.get("row_type", "")).strip()
        condition = str(row.get("requirement_condition", "")).strip()
        if row_type in {"data_array", "timestamps_array"}:
            token = condition.split(":", 1)[-1] if ":" in condition else ""
            if _datatype_handler_implemented(token):
                continue
            record_table_gap(
                context,
                f"No converter handler for row_type={row_type} condition={condition} "
                f"target={row.get('nwb_location')}/{row.get('nwb_fieldname')}",
            )


def convert_surlab_session_to_nwb(config: ConversionConfig) -> ConversionResult:
    """Convert one SurLab session into one integrated NWB file."""
    try:
        from pynwb import NWBHDF5IO
    except ImportError as exc:
        raise ImportError(
            "PyNWB is required for SurLab->NWB conversion. Install with "
            "`pip install pynwb hdmf` or recreate environment from "
            "`environment_cross_platform.yml`."
        ) from exc

    table_rows = read_conversion_table(config.conversion_table_path)
    table_rows = filter_dev_stage(table_rows, config.dev_max_stage)

    dataset_id = dataset_id_from_dir(config.dataset_dir)
    session_record = load_session_record(config.dataset_dir, config.session_dir, dataset_id)
    discovered_datatypes = discover_datatypes_from_files(
        config.session_dir,
        dataset_id,
        session_record,
    )
    expanded_rows = expand_rows_for_datatypes(table_rows, discovered_datatypes)

    context = PlacementContext(session_record=session_record, table_rows=expanded_rows)
    nwbfile = create_nwbfile_from_table(context, timezone_name=config.timezone_name)

    if "spikeTimes" in discovered_datatypes and _modality_enabled(config.dev_max_stage, 2):
        apply_spike_times(nwbfile, context, config.dataset_dir, config.session_dir)

    if any(dtype.endswith("_traces") for dtype in discovered_datatypes) and _modality_enabled(
        config.dev_max_stage, 3
    ):
        apply_traces(
            nwbfile,
            context,
            config.dataset_dir,
            config.session_dir,
            discovered_datatypes,
        )

    if any(dtype.endswith("_behTSeries") for dtype in discovered_datatypes) and _modality_enabled(
        config.dev_max_stage, 4
    ):
        apply_beh_tseries(
            nwbfile,
            context,
            config.dataset_dir,
            config.session_dir,
            discovered_datatypes,
        )

    if "trialInfo" in discovered_datatypes and _modality_enabled(config.dev_max_stage, 5):
        apply_trial_info(nwbfile, context, config.dataset_dir, config.session_dir)

    if "lfp" in discovered_datatypes and _modality_enabled(config.dev_max_stage, 6):
        apply_lfp(nwbfile, context, config.dataset_dir, config.session_dir, discovered_datatypes)

    if "spikeWaves" in discovered_datatypes and _modality_enabled(config.dev_max_stage, 7):
        apply_spike_waves(nwbfile, context, config.dataset_dir, config.session_dir)

    if any(dtype.endswith("_behEvents") for dtype in discovered_datatypes) and _modality_enabled(
        config.dev_max_stage, 8
    ):
        apply_beh_events(
            nwbfile,
            context,
            config.dataset_dir,
            config.session_dir,
            discovered_datatypes,
        )

    warn_zero_time_reference(context, config.session_dir, config.dataset_dir)
    _report_unimplemented_rows(context, discovered_datatypes)

    config.output_nwb_path.parent.mkdir(parents=True, exist_ok=True)
    with NWBHDF5IO(str(config.output_nwb_path), mode="w") as io_handle:
        io_handle.write(nwbfile)

    if context.table_gaps:
        logger.warning("Conversion completed with %d table gap(s).", len(context.table_gaps))
    logger.info("Wrote NWB file: %s", config.output_nwb_path)
    return ConversionResult(
        output_nwb_path=config.output_nwb_path,
        table_gaps=context.table_gaps,
        warnings=context.warnings,
    )


def _modality_enabled(dev_max_stage: Optional[int], table_stage: int) -> bool:
    if dev_max_stage is None:
        return True
    return dev_max_stage >= table_stage


def _datatype_handler_implemented(token: str) -> bool:
    if token in IMPLEMENTED_DATATYPES:
        return True
    return any(token.endswith(suffix) for suffix in IMPLEMENTED_DATATYPE_SUFFIXES)
