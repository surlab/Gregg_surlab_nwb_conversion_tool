"""Write SurLab optical traces streams into NWB ophys containers.

Placement follows sur_nwb_conversion_table.csv stage-3 rows and the
Per-stream SurLabSchema LabMetaData policy: core attributes first, leftovers
in ``lab_meta_data['SurLabSchema_<datatypeID>']``, layout fields skipped
(validate_only).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from src.data_io import (
    load_json,
    load_numeric_array,
    normalize_metadata_row,
    normalize_schema_keys,
    parse_coordinate_list,
    parse_coordinate_value,
)
from src.nwb_surlab_schema import SurLabSchemaMeta
from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext, record_table_gap, record_warning

logger = logging.getLogger(__name__)

MISSING_MARKER = "MISSING_REQUIRED_FOR_NWB"

# Fallback when no center or coordinate lists are available.
FALLBACK_PIXEL_MASK = [[0, 0, 1]]

# Schema / sessionInfo keys that map to core NWB attributes (not LabMetaData).
CORE_SCALAR_FIELDS = {
    "data_unit_measurement",
    "sample_frequency__Hz",
    "indicator",
    "wavelength__nm",
}

# Keys written into SurLabSchema_<datatypeID> LabMetaData when present.
LABMETA_SCALAR_FIELDS = {
    "detection_software",
    "objectives",
    "laser_name",
    "pixel_size__um",
    "pixel_size__au",
    "pixel_size_calibration",
    "fov_width__pixels",
    "fov_height__pixels",
    "fov_depth__um",
}

LAYOUT_FIELDS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}

MICROSCOPE_SCALAR_FIELDS = {
    "microscope",
    "microscope_description",
}

ROI_COLUMN_MAP = {
    "roi_x_coordinates": "roi_x",
    "roi_y_coordinates": "roi_y",
    "area": "area",
    "depth__um": "depth__um",
    "roi_center_x": "roi_center_x",
    "roi_center_y": "roi_center_y",
}

LEGACY_SCHEMA_ALIASES = {
    "pixel_size": "pixel_size__um",
}


def apply_traces(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    discovered_datatypes: set[str],
) -> None:
    """Add all discovered ``*_traces`` streams to the NWB file."""
    trace_ids = sorted(dtype for dtype in discovered_datatypes if dtype.endswith("_traces"))
    if not trace_ids:
        return

    for datatype_id in trace_ids:
        try:
            _add_one_traces_stream(
                nwbfile,
                context,
                dataset_dir,
                session_dir,
                datatype_id,
            )
        except Exception as exc:
            record_table_gap(
                context,
                f"traces handler failed for {datatype_id}: {exc}",
            )
            logger.exception("Failed converting traces stream %s", datatype_id)


def _add_one_traces_stream(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    datatype_id: str,
) -> None:
    from pynwb.ophys import OpticalChannel, RoiResponseSeries

    data_file = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_data.{{mat|npz}}",
        context.session_record,
        datatype_id=datatype_id,
    )
    timestamps_file = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_timestamps.{{mat|npz}}",
        context.session_record,
        datatype_id=datatype_id,
    )
    if data_file is None or timestamps_file is None:
        record_warning(
            context,
            f"Skipping {datatype_id}: missing data and/or timestamps file.",
        )
        return

    data = np.asarray(load_numeric_array(data_file.path), dtype=float)
    timestamps = np.asarray(load_numeric_array(timestamps_file.path), dtype=float).ravel()
    schema = _load_schema(session_dir, dataset_dir, context.session_record, datatype_id)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record, datatype_id)
    scalars = _resolve_stream_scalars(context, datatype_id, schema)
    microscope_scalars = _resolve_microscope_scalars(context, datatype_id, schema)

    data = _ensure_time_by_roi(data, metadata_rows, context, datatype_id, schema)
    if data.shape[0] != timestamps.shape[0]:
        raise ValueError(
            f"{datatype_id}: timestamps length {timestamps.shape[0]} != data time axis {data.shape[0]}"
        )
    if metadata_rows and data.shape[1] != len(metadata_rows):
        raise ValueError(
            f"{datatype_id}: metadata rows {len(metadata_rows)} != data ROI axis {data.shape[1]}"
        )

    device = _ensure_microscope_device(nwbfile, context, datatype_id, microscope_scalars)
    indicator = str(scalars.get("indicator") or MISSING_MARKER)
    wavelength = scalars.get("wavelength__nm")
    emission = float(wavelength) if _is_number(wavelength) else float("nan")
    optical_channel = OpticalChannel(
        name=indicator if indicator != MISSING_MARKER else f"{datatype_id}_channel",
        description=MISSING_MARKER if indicator == MISSING_MARKER else f"indicator={indicator}",
        emission_lambda=emission if not np.isnan(emission) else float("nan"),
    )
    rate = scalars.get("sample_frequency__Hz")
    imaging_plane = nwbfile.create_imaging_plane(
        name=f"{datatype_id}_imaging_plane",
        optical_channel=optical_channel,
        imaging_rate=float(rate) if _is_number(rate) else float("nan"),
        description=MISSING_MARKER,
        device=device,
        excitation_lambda=float("nan"),
        indicator=indicator,
        location=MISSING_MARKER,
    )

    ophys = _ensure_ophys_module(nwbfile)
    img_seg = _ensure_image_segmentation(ophys)
    plane_seg = img_seg.create_plane_segmentation(
        name=f"{datatype_id}_plane_segmentation",
        description=(
            f"ROIs for {datatype_id}; pixel_mask marks roi_center (1 pixel) or full "
            f"roi_x_coordinates/roi_y_coordinates lists when provided"
        ),
        imaging_plane=imaging_plane,
    )
    _add_rois(plane_seg, metadata_rows, data.shape[1], context, datatype_id)

    region_indices = list(range(data.shape[1]))
    roi_table_region = plane_seg.create_roi_table_region(
        description=f"all ROIs for {datatype_id}",
        region=region_indices,
    )

    fluorescence = _ensure_fluorescence(ophys)
    unit = str(scalars.get("data_unit_measurement") or MISSING_MARKER)
    roi_response = RoiResponseSeries(
        name=datatype_id,
        data=data,
        rois=roi_table_region,
        unit=unit,
        timestamps=timestamps,
        description=f"SurLab traces stream {datatype_id}",
    )
    fluorescence.add_roi_response_series(roi_response)

    _add_surlab_schema_labmetadata(nwbfile, datatype_id, scalars, schema)
    logger.info(
        "Added traces stream %s: data%s timestamps=%d rois=%d",
        datatype_id,
        data.shape,
        timestamps.shape[0],
        data.shape[1],
    )


def _ensure_time_by_roi(
    data: np.ndarray,
    metadata_rows: List[Dict[str, str]],
    context: PlacementContext,
    datatype_id: str,
    schema: Dict[str, object],
) -> np.ndarray:
    """Return array shaped (n_time, n_roi); transpose on clear mismatch."""
    if data.ndim != 2:
        raise ValueError(f"{datatype_id}: expected 2-D traces array, got shape {data.shape}")

    n_meta = len(metadata_rows)
    y_size = schema.get("Y_size")
    x_dim = str(schema.get("X_dim", "")).strip().lower()
    y_dim = str(schema.get("Y_dim", "")).strip().lower()

    if x_dim == "time" and y_dim in {"roi", "rois"}:
        return data
    if y_dim == "time" and x_dim in {"roi", "rois"}:
        record_warning(context, f"{datatype_id}: transposing traces from ROI x time to time x ROI")
        return data.T

    if n_meta and data.shape[1] == n_meta:
        return data
    if n_meta and data.shape[0] == n_meta:
        record_warning(
            context,
            f"{datatype_id}: transposing traces so ROI axis matches metadata row count",
        )
        return data.T
    if _is_number(y_size):
        y_size_int = int(y_size)
        if data.shape[1] == y_size_int:
            return data
        if data.shape[0] == y_size_int:
            record_warning(context, f"{datatype_id}: transposing traces to match Y_size={y_size_int}")
            return data.T

    # Default canonical assumption.
    return data


def _load_schema(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
    datatype_id: str,
) -> Dict[str, object]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_schema.json",
        session_record,
        datatype_id=datatype_id,
    )
    if resolved is None:
        return {}
    schema = normalize_schema_keys(load_json(resolved.path))
    for legacy_key, canonical_key in LEGACY_SCHEMA_ALIASES.items():
        if canonical_key not in schema and legacy_key in schema:
            schema[canonical_key] = schema[legacy_key]
    return schema


def _load_metadata_rows(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
    datatype_id: str,
) -> List[Dict[str, str]]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_metadata.csv",
        session_record,
        datatype_id=datatype_id,
    )
    if resolved is None:
        return []
    return [normalize_metadata_row(dict(row)) for row in read_csv_rows(resolved.path)]


def _resolve_stream_scalars(
    context: PlacementContext,
    datatype_id: str,
    schema: Dict[str, object],
) -> Dict[str, object]:
    """sessionInfo-first; optional schema mirror; fail if both disagree."""
    resolved: Dict[str, object] = {}
    interested = CORE_SCALAR_FIELDS.union(LABMETA_SCALAR_FIELDS)
    for field_name in sorted(interested):
        session_key = f"{datatype_id}_{field_name}"
        session_value = context.session_record.get(session_key, "")
        schema_value = schema.get(field_name, "")

        session_present = field_non_empty(session_value)
        schema_present = field_non_empty(schema_value)

        if session_present and schema_present:
            left = str(session_value).strip()
            right = str(schema_value).strip()
            if left != right and not _numeric_equal(left, right):
                raise ValueError(
                    f"{datatype_id}: sessionInfo {session_key}={left!r} disagrees with "
                    f"schema {field_name}={right!r}"
                )
            resolved[field_name] = _maybe_number(session_value)
        elif session_present:
            resolved[field_name] = _maybe_number(session_value)
        elif schema_present:
            resolved[field_name] = _maybe_number(schema_value)
    return resolved


def _resolve_microscope_scalars(
    context: PlacementContext,
    datatype_id: str,
    schema: Dict[str, object],
) -> Dict[str, object]:
    """sessionInfo-first for {datatypeID}_microscope (+ optional description)."""
    resolved: Dict[str, object] = {}
    for field_name in sorted(MICROSCOPE_SCALAR_FIELDS):
        session_key = f"{datatype_id}_{field_name}"
        session_value = context.session_record.get(session_key, "")
        schema_value = schema.get(field_name, "")

        session_present = field_non_empty(session_value)
        schema_present = field_non_empty(schema_value)

        if session_present and schema_present:
            left = str(session_value).strip()
            right = str(schema_value).strip()
            if left != right and not _numeric_equal(left, right):
                raise ValueError(
                    f"{datatype_id}: sessionInfo {session_key}={left!r} disagrees with "
                    f"schema {field_name}={right!r}"
                )
            resolved[field_name] = left
        elif session_present:
            resolved[field_name] = str(session_value).strip()
        elif schema_present:
            resolved[field_name] = str(schema_value).strip()
    return resolved


def _ensure_microscope_device(nwbfile, context: PlacementContext, datatype_id: str, scalars: Dict[str, object]):
    """Create or reuse NWB Device from microscope identity; placeholder when absent."""
    microscope_name = str(scalars.get("microscope") or "").strip()
    if not microscope_name:
        record_warning(
            context,
            f"{datatype_id}: missing {datatype_id}_microscope; using placeholder Device name",
        )
        placeholder_name = f"{datatype_id}_device"
        if placeholder_name in nwbfile.devices:
            return nwbfile.devices[placeholder_name]
        return nwbfile.create_device(name=placeholder_name, description=MISSING_MARKER)

    description = str(scalars.get("microscope_description") or "").strip() or None
    if microscope_name in nwbfile.devices:
        device = nwbfile.devices[microscope_name]
        if description:
            existing = str(getattr(device, "description", "") or "").strip()
            if existing and existing != description:
                record_warning(
                    context,
                    f"{datatype_id}: shared microscope Device {microscope_name!r} already has "
                    f"description {existing!r}; ignoring {description!r} from this stream",
                )
        logger.info("Reusing microscope Device %s for %s", microscope_name, datatype_id)
        return device

    device = nwbfile.create_device(name=microscope_name, description=description)
    logger.info("Registered microscope Device %s for %s", microscope_name, datatype_id)
    return device


def _add_rois(
    plane_seg,
    metadata_rows: List[Dict[str, str]],
    n_rois: int,
    context: PlacementContext,
    datatype_id: str,
) -> None:
    known = {"roi_ID"}
    known.update(ROI_COLUMN_MAP.keys())
    extra_cols: List[str] = []
    if metadata_rows:
        for key in metadata_rows[0].keys():
            if key not in known and key not in extra_cols:
                extra_cols.append(key)

    for source_name, target_name in ROI_COLUMN_MAP.items():
        if metadata_rows and any(field_non_empty(row.get(source_name, "")) for row in metadata_rows):
            if target_name not in plane_seg.colnames:
                plane_seg.add_column(name=target_name, description=f"SurLab {source_name}")

    for extra_name in extra_cols:
        if extra_name not in plane_seg.colnames:
            plane_seg.add_column(name=extra_name, description=f"SurLab dataset_specific {extra_name}")

    for index in range(n_rois):
        row = metadata_rows[index] if index < len(metadata_rows) else {}
        roi_id = row.get("roi_ID", str(index))
        try:
            kwargs = {
                "pixel_mask": _build_roi_pixel_mask(row, context, datatype_id, index),
                "id": _coerce_id(roi_id),
            }
            for source_name, target_name in ROI_COLUMN_MAP.items():
                if target_name not in plane_seg.colnames:
                    continue
                raw = row.get(source_name, "")
                kwargs[target_name] = _roi_cell_value(raw, source_name)
            for extra_name in extra_cols:
                kwargs[extra_name] = str(row.get(extra_name, "")).strip()
            plane_seg.add_roi(**kwargs)
        except Exception as exc:
            record_warning(
                context,
                f"{datatype_id}: ROI row {index} failed ({exc}); using center/fallback mask",
            )
            plane_seg.add_roi(
                pixel_mask=_build_roi_pixel_mask(row, context, datatype_id, index),
                id=index,
            )


def _build_roi_pixel_mask(
    row: Dict[str, str],
    context: PlacementContext,
    datatype_id: str,
    index: int,
) -> List[List[float]]:
    """Build NWB pixel_mask: full outline from coordinate lists, else 1 px at center."""
    xs = parse_coordinate_list(row.get("roi_x_coordinates", ""))
    ys = parse_coordinate_list(row.get("roi_y_coordinates", ""))
    if xs and ys and len(xs) > 1:
        if len(xs) != len(ys):
            raise ValueError(
                f"roi_x_coordinates length {len(xs)} != roi_y_coordinates length {len(ys)}"
            )
        return [[float(x), float(y), 1.0] for x, y in zip(xs, ys)]

    center_x = parse_coordinate_list(row.get("roi_center_x", ""))
    center_y = parse_coordinate_list(row.get("roi_center_y", ""))
    if center_x and center_y:
        return [[float(center_x[0]), float(center_y[0]), 1.0]]

    if xs and ys:
        if len(xs) != len(ys):
            raise ValueError(
                f"roi_x_coordinates length {len(xs)} != roi_y_coordinates length {len(ys)}"
            )
        return [[float(xs[0]), float(ys[0]), 1.0]]

    record_warning(
        context,
        f"{datatype_id}: ROI row {index} has no center or coordinate lists; "
        f"using fallback pixel_mask {FALLBACK_PIXEL_MASK}",
    )
    return list(FALLBACK_PIXEL_MASK)


def _roi_cell_value(raw: object, source_name: str):
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "na", "n/a"}:
        if source_name in {"area"}:
            return ""
        return float("nan")
    if source_name == "area":
        return text
    if source_name in {"roi_x_coordinates", "roi_y_coordinates"}:
        values = parse_coordinate_list(raw)
        if len(values) > 1:
            return json.dumps(values)
        if len(values) == 1:
            return values[0]
        return float("nan")
    if source_name in {"roi_center_x", "roi_center_y", "depth__um"}:
        parsed = parse_coordinate_value(raw)
        if isinstance(parsed, str):
            return parsed
        return parsed
    try:
        return float(text)
    except ValueError:
        return text


def _coerce_id(value: object):
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        return text


def _add_surlab_schema_labmetadata(
    nwbfile,
    datatype_id: str,
    scalars: Dict[str, object],
    schema: Dict[str, object],
) -> None:
    payload: Dict[str, object] = {}
    for field_name in LABMETA_SCALAR_FIELDS:
        if field_name in scalars and field_non_empty(scalars[field_name]):
            payload[field_name] = scalars[field_name]

    reserved = (
        CORE_SCALAR_FIELDS.union(LABMETA_SCALAR_FIELDS)
        .union(LAYOUT_FIELDS)
        .union(MICROSCOPE_SCALAR_FIELDS)
        .union(set(LEGACY_SCHEMA_ALIASES.keys()))
    )
    for key, value in schema.items():
        if key in reserved:
            continue
        if key in payload:
            continue
        if field_non_empty(value):
            payload[key] = value

    if not payload:
        return

    container_name = f"SurLabSchema_{datatype_id}"
    schema_json = json.dumps(payload, sort_keys=True, default=str)
    if container_name in getattr(nwbfile, "lab_meta_data", {}):
        nwbfile.lab_meta_data[container_name].schema_json = schema_json
        return

    nwbfile.add_lab_meta_data(SurLabSchemaMeta(name=container_name, schema_json=schema_json))


def _ensure_ophys_module(nwbfile):
    if "ophys" in nwbfile.processing:
        return nwbfile.processing["ophys"]
    return nwbfile.create_processing_module(name="ophys", description="optical physiology")


def _ensure_image_segmentation(ophys_module):
    from pynwb.ophys import ImageSegmentation

    if "ImageSegmentation" in ophys_module.data_interfaces:
        return ophys_module.data_interfaces["ImageSegmentation"]
    image_segmentation = ImageSegmentation(name="ImageSegmentation")
    ophys_module.add(image_segmentation)
    return image_segmentation


def _ensure_fluorescence(ophys_module):
    from pynwb.ophys import Fluorescence

    if "Fluorescence" in ophys_module.data_interfaces:
        return ophys_module.data_interfaces["Fluorescence"]
    fluorescence = Fluorescence(name="Fluorescence")
    ophys_module.add(fluorescence)
    return fluorescence


def _is_number(value: object) -> bool:
    if value is None:
        return False
    try:
        float(value)
        return str(value).strip() != ""
    except (TypeError, ValueError):
        return False


def _maybe_number(value: object):
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer() and "." not in text and "e" not in text.lower():
            return int(number)
        return number
    except ValueError:
        return text


def _numeric_equal(left: str, right: str) -> bool:
    try:
        return float(left) == float(right)
    except ValueError:
        return False
