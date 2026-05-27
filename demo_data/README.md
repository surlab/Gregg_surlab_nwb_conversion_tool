This "demo_data" folder should include shared data for the purposes of demonstrating the code.
Ideally it will include all the files needed for a complete end to end run of 1 "instance"
(maybe one cell, session, or dataset).
It should be able to demonstrate all of the functions in src, but not necessarily looping or
parallelization included in scripts/main.

Only **`lfp_data_*.mat`** is gitignored (continuous LFP is ~GB; GitHub limit is 100 MB per file).
Keep that file locally under `demo_data/` or point `config.py` at your lab data path. Other demo
`.mat` files (timestamps, spike times, spike waves) are small enough to version in git.

Your real data should be stored elsewhere and pointed to with a path variable in repo/src/config.py
