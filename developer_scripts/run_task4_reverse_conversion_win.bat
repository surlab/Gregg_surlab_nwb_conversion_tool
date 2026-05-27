@echo off
setlocal

REM Task 4: Reverse convert NWB files to SurLab sessionInfo CSV files.
REM For each NWB file found under the dataset directory:
REM   1) write sessionInfo_single_session.csv in that session directory
REM   2) concatenate rows into dataset-level sessionInfo_<datasetID>.csv

set DATASET_DIR=demo_data\SeqBias_AstroBlock_NPX
set CONVERSION_TABLE=conversion_table.csv
set REPO_DIR=%~dp0..
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool
call conda info --envs

python scripts\run_task4_reverse_conversion.py ^
  --dataset-dir "%DATASET_DIR%" ^
  --conversion-table "%CONVERSION_TABLE%" ^
  --stage 4

if %ERRORLEVEL% NEQ 0 (
  echo Task 4 reverse conversion failed with code %ERRORLEVEL%.
  popd
  exit /b %ERRORLEVEL%
)

echo Task 4 reverse conversion completed.
popd
endlocal
