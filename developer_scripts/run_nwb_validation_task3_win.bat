@echo off
setlocal

REM Task 3: Validate all NWB files found under one dataset directory.
REM Reports are saved in each session directory (next to each NWB file),
REM and a dataset-level summary CSV is saved in the dataset directory root.

set DATASET_DIR=demo_data\SeqBias_AstroBlock_NPX
set REPO_DIR=%~dp0..
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool
call conda info --envs

python scripts\validate_nwb_dataset.py --dataset-dir "%DATASET_DIR%"

if %ERRORLEVEL% NEQ 0 (
  echo Task 3 NWB validation failed with code %ERRORLEVEL%.
  echo Press any key to close this window.
  pause >nul
  popd
  exit /b %ERRORLEVEL%
)

echo Task 3 NWB validation completed.
echo Press any key to close this window.
pause >nul
popd
endlocal
