# Tricolor projections — global dataset variables

Values here apply to **all sessions** in `tricolor_projections` unless a session-specific source overrides them (e.g. Prairie View XML for imaging depth).

Edit `dataset_config.json` for machine-readable defaults used by the converter. This file is the human-readable reference.

| Field | Value | Source / notes |
|-------|--------|----------------|
| `datasetID` | `tricolor_projections` | Folder name |
| `institution` | MIT | Provenance |
| `lab` | Mriganka Sur | Provenance |
| `experimenter` | Sofie Ahrlund Richter | Provenance |
| `species` | `Mus musculus` | NCBI / NWB |
| `strain` | `flex-GCaMP8m x CamkII-Cre` | Transgenic line |
| `sex` | `U` | Unknown unless recorded per animal |
| `age__days` | *(empty)* | Fill per animal when known |
| `condition` | `passive visual grating` | Task type |
| `area` (session + ROI) | `VISp` | [Allen CCF](https://atlas.brain-map.org/) acronym — primary visual area (visual cortex) |
| `related_publication` | *(empty)* | Optional DOI |
| `fov_depth__um` fallback | *(null)* | Only used when set to a **non-zero** value; Prairie `positionCurrent` / `ZAxis` = **0** is omitted (operators zero the Z reference — not a real imaging depth) |

## Per-session imaging (from Prairie View XML when available)

| Schema field | XML keys | Rule |
|--------------|----------|------|
| `wavelength__nm` | `laserWavelength` | Index matching active `laserPower` (> 0) |
| `laser_name` | `laserPower` description | Description of active laser channel |
| `pixel_size` | `micronsPerPixel` X/Y | Mean of X and Y µm/px |
| `objectives` | `objectiveLensMag`, `objectiveLensNA` | `{mag}X_{na}NA` e.g. `16X_0.8NA` |
| `fov_width__pixels` | `pixelsPerLine` | |
| `fov_height__pixels` | `linesPerFrame` | |
| `fov_depth__um` | `positionCurrent` → `ZAxis` | Stage Z in µm; **omit** if 0 (zeroed reference). Set `fov_depth__um` in `dataset_config.json` only when a known depth should override |
