"""Table-driven NWB -> SurLab reverse conversion (Task 4)."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from src.conversion_table import (
    condition_datatype_id,
    filter_dev_stage,
    is_informational_row,
    read_conversion_table,
    row_applies_to_session,
)
from src.nwb_keyword_map import (
    discover_datatypes_from_keywords,
    keywords_from_nwb,
    load_keyword_rules,
)
from src.nwb_reverse_spike_times import export_spike_times_from_nwb
from src.nwb_reverse_trial_info import export_trial_info_from_nwb
from src.nwb_table_reader import (
    parse_experiment_description,
    read_legacy_lab_meta_extras,
    read_nwb_value_for_row,
)
from src.nwb_triangulation import find_session_nwb
from src.session_record import LEGACY_TO_CANONICAL_FIELD_MAP, field_non_empty
from src.surlab_paths import dataset_id_from_dir

logger = logging.getLogger(__name__)

ROUNDTRIP_OUTPUT_DIRNAME = "roundtrip_surformat"
SKIP_SESSIONINFO_FIELDS = {
    "",
    "NA",
    "N/A",
    "(derived_file_identifier)",
    "(all columns above)",
    "dataset_specific",
}


@dataclass
class ReverseConversionConfig:
    """Settings for reverse conversion."""

    dataset_dir: Path
    conversion_table_path: Path
    session_dir: Optional[Path] = None
    dev_max_stage: Optional[int] = None
    output_subdir: str = ROUNDTRIP_OUTPUT_DIRNAME
    output_session_info_name: str = "sessionInfo_single_session.csv"
    log_path: Optional[Path] = None


@dataclass
class ReverseConversionResult:
    dataset_sessioninfo_csv: Path
    session_csv_files: List[Path]
    nwb_files_processed: List[Path]
    roundtrip_output_dirs: List[Path]
    files_written: List[Path]
    warnings: List[str] = field(default_factory=list)
    report_csv: Optional[Path] = None


def setup_reverse_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[
                logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )


def _is_sessioninfo_row(row: Dict[str, str]) -> bool:
    filename = str(row.get("surlab_filename", "")).strip().lower()
    row_type = str(row.get("row_type", "")).strip().lower()
    return "sessioninfo" in filename and row_type == "metadata_field"


def _is_unbound_template_field(field_name: str) -> bool:
    return "<datatypeID>" in field_name or "<datatypeid>" in field_name.lower()


def _discover_present_datatypes(nwbfile, table_rows: List[Dict[str, str]]) -> Set[str]:
    rules = load_keyword_rules(table_rows)
    present = discover_datatypes_from_keywords(keywords_from_nwb(nwbfile), rules)
    if nwbfile.units is not None and len(nwbfile.units) > 0:
        present.add("spikeTimes")
    if getattr(nwbfile, "trials", None) is not None and len(nwbfile.trials) > 0:
        present.add("trialInfo")
    return present


def _ordered_sessioninfo_columns(
    stage_rows: List[Dict[str, str]],
    present_datatypes: Optional[Set[str]] = None,
) -> List[str]:
    required: List[str] = []
    optional: List[str] = []
    seen: Set[str] = set()
    for row in stage_rows:
        if not _is_sessioninfo_row(row):
            continue
        if is_informational_row(row):
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if field_name in SKIP_SESSIONINFO_FIELDS or field_name.startswith("("):
            continue
        if _is_unbound_template_field(field_name):
            continue
        condition = str(row.get("requirement_condition", "always")).strip() or "always"
        if condition != "always":
            datatype = condition_datatype_id(condition)
            if datatype is None:
                # Unbound <datatypeID> template — skip until expanded.
                continue
            if present_datatypes is not None and datatype not in present_datatypes:
                # Keep modality flag columns even when off; skip stream scalars.
                if str(row.get("nwb_fieldname", "")).strip() != "keywords":
                    continue
        if field_name in seen:
            continue
        seen.add(field_name)
        level = str(row.get("requirement_level", "")).strip().lower()
        if level == "required":
            required.append(field_name)
        else:
            optional.append(field_name)
    return required + optional


def _all_headers(explicit_columns: Sequence[str], session_rows: Iterable[Dict[str, str]]) -> List[str]:
    headers = list(explicit_columns)
    extras: List[str] = []
    for row in session_rows:
        for key in row.keys():
            if key in headers or key in extras:
                continue
            if _is_unbound_template_field(key):
                continue
            extras.append(key)
    return headers + sorted(extras)


def _write_single_row_csv(output_csv: Path, row: Dict[str, str], headers: Sequence[str]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers))
        writer.writeheader()
        writer.writerow({header: row.get(header, "") for header in headers})


def _find_session_nwb_files(
    dataset_dir: Path,
    session_dir: Optional[Path] = None,
) -> List[Path]:
    """Return one canonical NWB per session directory (skip legacy stage-suffixed duplicates)."""
    from src.session_record import discover_session_dirs, load_session_record

    dataset_id = dataset_id_from_dir(dataset_dir)
    if session_dir is not None:
        session_dirs = [session_dir.resolve()]
    else:
        session_dirs = discover_session_dirs(dataset_dir)

    selected: List[Path] = []
    for one_session_dir in session_dirs:
        try:
            session_record = load_session_record(dataset_dir, one_session_dir, dataset_id)
        except (FileNotFoundError, ValueError):
            session_record = {}
        nwb_path = find_session_nwb(one_session_dir, session_record)
        if nwb_path is not None:
            selected.append(nwb_path)
    if selected:
        return sorted(selected)
    if session_dir is not None:
        return sorted(session_dir.resolve().glob("*.nwb"))
    return sorted(dataset_dir.rglob("*.nwb"))


def build_session_row_from_nwb(
    nwbfile,
    stage_rows: List[Dict[str, str]],
) -> tuple[Dict[str, str], List[str], Set[str]]:
    """Build one sessionInfo row from NWB using conversion table rows."""
    present_datatypes = _discover_present_datatypes(nwbfile, stage_rows)
    ordered_columns = _ordered_sessioninfo_columns(stage_rows, present_datatypes)
    row = {column: "" for column in ordered_columns}
    warnings: List[str] = []

    for table_row in stage_rows:
        if not _is_sessioninfo_row(table_row):
            continue
        if is_informational_row(table_row):
            continue
        field_name = str(table_row.get("fieldname_surlab", "")).strip()
        if field_name in SKIP_SESSIONINFO_FIELDS or field_name.startswith("("):
            continue
        if _is_unbound_template_field(field_name):
            continue

        is_keyword = str(table_row.get("nwb_fieldname", "")).strip() == "keywords"
        condition = str(table_row.get("requirement_condition", "always")).strip() or "always"
        if condition != "always" and not is_keyword:
            if not row_applies_to_session(table_row, present_datatypes):
                continue

        value = read_nwb_value_for_row(nwbfile, table_row)
        if is_keyword:
            # Fixed modality flags: always write 0/1 when the column is in scope.
            if field_name in ordered_columns or field_name in row:
                row[field_name] = value if value != "" else "0"
            elif value == "1":
                row[field_name] = "1"
            continue

        if field_non_empty(value):
            row[field_name] = value

    extras = parse_experiment_description(getattr(nwbfile, "experiment_description", ""))
    extras.update(read_legacy_lab_meta_extras(nwbfile))
    legacy_keys = set(LEGACY_TO_CANONICAL_FIELD_MAP.keys())
    for key, value in extras.items():
        if key in legacy_keys:
            continue
        if _is_unbound_template_field(key):
            continue
        if key in row and field_non_empty(row.get(key, "")):
            continue
        row[key] = value

    return row, warnings, present_datatypes


def _dataset_sessioninfo_name(dataset_dir: Path) -> str:
    return f"sessionInfo_{dataset_id_from_dir(dataset_dir)}.csv"


def _write_report_csv(output_path: Path, report_rows: List[Dict[str, str]]) -> None:
    if not report_rows:
        return
    fieldnames = sorted({key for row in report_rows for key in row.keys()})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)


def convert_dataset_nwb_to_surlab(config: ReverseConversionConfig) -> ReverseConversionResult:
    """Reverse-convert all NWB files in one dataset into SurLab files."""
    from pynwb import NWBHDF5IO

    log_path = config.log_path or (config.dataset_dir / "runlog.txt")
    setup_reverse_logging(log_path)
    logger.info("Task 4 reverse conversion starting for dataset: %s", config.dataset_dir)

    conversion_rows = read_conversion_table(config.conversion_table_path)
    stage_rows = filter_dev_stage(conversion_rows, config.dev_max_stage)
    dataset_id = dataset_id_from_dir(config.dataset_dir)

    nwb_files = _find_session_nwb_files(config.dataset_dir, session_dir=config.session_dir)
    if not nwb_files:
        raise FileNotFoundError(f"No NWB files found under dataset directory: {config.dataset_dir}")

    session_outputs: List[Path] = []
    session_rows: List[Dict[str, str]] = []
    roundtrip_dirs: List[Path] = []
    files_written: List[Path] = []
    all_warnings: List[str] = []
    report_rows: List[Dict[str, str]] = []

    for nwb_path in nwb_files:
        logger.info("Processing NWB file: %s", nwb_path)
        with NWBHDF5IO(str(nwb_path), mode="r", load_namespaces=True) as io_handle:
            nwbfile = io_handle.read()
            row, warnings, present_datatypes = build_session_row_from_nwb(nwbfile, stage_rows)
            all_warnings.extend(warnings)

            output_dir = nwb_path.parent / config.output_subdir
            output_dir.mkdir(parents=True, exist_ok=True)
            roundtrip_dirs.append(output_dir)

            headers_for_session = _all_headers(
                _ordered_sessioninfo_columns(stage_rows, present_datatypes),
                [row],
            )
            session_csv = output_dir / config.output_session_info_name
            _write_single_row_csv(session_csv, row, headers_for_session)
            session_outputs.append(session_csv)
            files_written.append(session_csv)
            session_rows.append(row)

            if config.dev_max_stage is None or config.dev_max_stage >= 2:
                if "spikeTimes" in present_datatypes:
                    spike_files = export_spike_times_from_nwb(
                        nwbfile,
                        output_dir,
                        dataset_id,
                        row,
                        conversion_rows,
                        dev_max_stage=config.dev_max_stage or 99,
                    )
                    files_written.extend(spike_files)
                    for path in spike_files:
                        report_rows.append(
                            {
                                "nwb_file": str(nwb_path),
                                "output_file": str(path),
                                "status": "written",
                                "datatype": "spikeTimes",
                            }
                        )

            if config.dev_max_stage is None or config.dev_max_stage >= 5:
                if "trialInfo" in present_datatypes:
                    trial_files = export_trial_info_from_nwb(
                        nwbfile,
                        output_dir,
                        dataset_id,
                        row,
                        conversion_rows,
                        dev_max_stage=config.dev_max_stage or 99,
                    )
                    files_written.extend(trial_files)
                    for path in trial_files:
                        report_rows.append(
                            {
                                "nwb_file": str(nwb_path),
                                "output_file": str(path),
                                "status": "written",
                                "datatype": "trialInfo",
                            }
                        )

            for warning in warnings:
                report_rows.append(
                    {
                        "nwb_file": str(nwb_path),
                        "output_file": "",
                        "status": "warning",
                        "datatype": warning,
                    }
                )

    # Dataset-level headers: union of columns that applied to any session.
    all_present: Set[str] = set()
    for row in session_rows:
        all_present.update(k for k, v in row.items() if k in {"lfp", "spikeTimes", "spikeWaves", "trialInfo", "behEvents"} and v == "1")
        if row.get("spikeTimes") == "1":
            all_present.add("spikeTimes")
    ordered_columns = _ordered_sessioninfo_columns(stage_rows, all_present or None)
    # Prefer union of actual written headers so per-session stream scalars are kept.
    dataset_headers = _all_headers(ordered_columns, session_rows)
    dataset_roundtrip_dir = config.dataset_dir / config.output_subdir
    dataset_roundtrip_dir.mkdir(parents=True, exist_ok=True)
    dataset_csv = dataset_roundtrip_dir / _dataset_sessioninfo_name(config.dataset_dir)
    with dataset_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=dataset_headers)
        writer.writeheader()
        for row in session_rows:
            writer.writerow({header: row.get(header, "") for header in dataset_headers})
    files_written.append(dataset_csv)

    report_path = dataset_roundtrip_dir / "reverse_conversion_report.csv"
    _write_report_csv(report_path, report_rows)

    logger.info("Wrote dataset sessionInfo: %s", dataset_csv)
    logger.info("Wrote %d session file(s); %d total outputs", len(session_outputs), len(files_written))

    return ReverseConversionResult(
        dataset_sessioninfo_csv=dataset_csv,
        session_csv_files=session_outputs,
        nwb_files_processed=nwb_files,
        roundtrip_output_dirs=roundtrip_dirs,
        files_written=files_written,
        warnings=all_warnings,
        report_csv=report_path,
    )


# Backward-compatible helpers for unit tests
def _age_duration_to_days(age_value: str) -> str:
    from src.nwb_table_reader import age_duration_to_days

    return age_duration_to_days(age_value)
