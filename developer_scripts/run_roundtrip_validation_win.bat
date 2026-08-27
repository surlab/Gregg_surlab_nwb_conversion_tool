@echo off
setlocal

REM Task 5: full round-trip validation (forward + PyNWB validate + reverse + compare).

set REPO_DIR=%~dp0..
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool
call conda info --envs

set DATASET_DIR=demo_data\SeqBias_AstroBlock_NPX
set CONVERSION_TABLE=sur_nwb_conversion_table.csv
set LOG_FILE=%DATASET_DIR%\runlog_roundtrip_validation.txt

python scripts\run_roundtrip_validation.py ^
  --dataset-dir "%DATASET_DIR%" ^
  --conversion-table "%CONVERSION_TABLE%" ^
  --log-file "%LOG_FILE%"

if %ERRORLEVEL% NEQ 0 (
  echo Task 5 round-trip validation failed with code %ERRORLEVEL%.
  echo See log: %LOG_FILE%
  popd
  exit /b %ERRORLEVEL%
)

echo Task 5 round-trip validation completed.
echo See log: %LOG_FILE%
popd
endlocal
