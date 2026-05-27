This "demo_data" folder should include shared data for the purposes of demonstrating the code.
Ideally it will include all the files needed for a complete end to end run of 1 "instance"
(maybe one cell, session, or dataset).
It should be able to demonstrate all of the functions in src, but not necessarily looping or
parallelization included in scripts/main.

Large SurLab `.mat` array files are **gitignored** (GitHub limit is 100 MB per file). Keep them
locally under `demo_data/` or point `config.py` at your lab data path. The repo ships smaller
artifacts (CSV, JSON schemas, PDF, NWB) for demos and tests.

Your real data should be stored elsewhere and pointed to with a path variable in repo/src/config.py
