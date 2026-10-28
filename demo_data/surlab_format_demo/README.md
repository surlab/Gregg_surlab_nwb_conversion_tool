# `surlab_format_demo` — canonical SurLab format demo

Small single-session demo that follows **current** SurLab naming and layout
(minimal filenames, dunder units, time×channels LFP, prefixed `lick_behEvents`).

Session folder: `AstroDREADD25_20240702/`

Built from a subset of `SeqBias_AstroBlock_NPX` plus synthetic LFP/behEvents.
The older `SeqBias_AstroBlock_NPX` tree remains as a **legacy** example only.

Rebuild:

```bat
python developer_scripts/build_surlab_format_demo.py
```
