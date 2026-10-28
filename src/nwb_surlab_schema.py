"""Load SurLabSchemaMeta LabMetaData extension (ndx-surlab-schema).

Task 1 policy: leftovers live on ``NWBFile.lab_meta_data['SurLabSchema_<id>']``.
Custom fields require a registered neurodata type so ``schema_json`` round-trips.
"""

from __future__ import annotations

from pathlib import Path

from pynwb import get_class, load_namespaces

NAMESPACE = "ndx-surlab-schema"
_NAMESPACE_PATH = Path(__file__).resolve().parent / f"{NAMESPACE}.namespace.yaml"

load_namespaces(str(_NAMESPACE_PATH))
SurLabSchemaMeta = get_class("SurLabSchemaMeta", NAMESPACE)
