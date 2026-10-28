# SurLab data format documentation

This page has moved. Use the doc that matches what you need:

- [Format basics](docs/surlab_format_basics.md) — folders, filenames, the session clock, and which modalities exist
- [Field catalog](docs/surlab_field_catalog.md) — `sessionInfo`, metadata, schema, and `trialInfo` field names
- [NWB conversion notes](docs/nwb_conversion_notes.md) — how those fields are written to and read from NWB

The converter still treats `sur_nwb_conversion_table.csv` as the machine-readable spec. If a human doc and the CSV disagree about a field the tools enforce, the CSV wins.
