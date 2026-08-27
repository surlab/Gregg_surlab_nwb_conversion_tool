@echo off
setlocal

REM Task 4: Reverse convert NWB files to SurLab under roundtrip_surformat/
REM Log: demo_data\...\runlog.txt

set DATASET_DIR=demo_data\SeqBias_AstroBlock_NPX
set CONVERSION_TABLE=sur_nwb_conversion_table.csv
set REPO_DIR=%~dp0..
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool

python scripts\run_task4_reverse_conversion.py ^
  --dataset-dir "%DATASET_DIR%" ^
  --conversion-table "%CONVERSION_TABLE%"

if %ERRORLEVEL% NEQ 0 (
  echo Task 4 reverse conversion failed with code %ERRORLEVEL%.
  popd
  exit /b %ERRORLEVEL%
)

echo Task 4 reverse conversion completed.
popd
endlocal
