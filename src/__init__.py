"""SurLab <-> NWB conversion and validation.

Distribution name (pip): ``surlab-nwb-conversion``
Import package name: ``src`` (rename deferred until Tasks 1–5 settle).
"""

from src.nwb_validation import (
    NWBValidationResult,
    validate_nwb_file,
    validate_nwb_files_in_dataset,
    write_dataset_validation_summary,
)
from src.package_paths import default_conversion_table_path
from src.sur_to_nwb import ConversionConfig, ConversionResult, convert_surlab_session_to_nwb
from src.validator import (
    ValidationConfig,
    build_session_validation_matrix,
    validate_session_format,
)

__version__ = "0.1.0"

__all__ = [
    "ConversionConfig",
    "ConversionResult",
    "NWBValidationResult",
    "ValidationConfig",
    "build_session_validation_matrix",
    "convert_surlab_session_to_nwb",
    "default_conversion_table_path",
    "validate_nwb_file",
    "validate_nwb_files_in_dataset",
    "validate_session_format",
    "write_dataset_validation_summary",
    "__version__",
]
