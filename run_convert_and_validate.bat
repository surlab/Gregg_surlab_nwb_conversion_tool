@echo off
setlocal

REM General Task 3 entry point: convert all implemented data to NWB, then validate.
REM Usage: run_convert_and_validate.bat PATH_TO_DATASET_DIR

set REPO_DIR=%~dp0
pushd "%REPO_DIR%"

if "%~1"=="" (
  echo Usage: run_convert_and_validate.bat PATH_TO_DATASET_DIR
  echo Example: run_convert_and_validate.bat demo_data\SeqBias_AstroBlock_NPX
  popd
  exit /b 1
)

set DATASET_DIR=%~1
call conda activate surlab_nwb_conversion_tool

python scripts\run_convert_and_validate.py --dataset-dir "%DATASET_DIR%"

set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% NEQ 0 (
  echo Convert + validate failed with code %EXIT_CODE%.
  echo See log: %DATASET_DIR%\runlog_convert_and_validate.txt
  popd
  exit /b %EXIT_CODE%
)

echo.
echo Done. Summary: %DATASET_DIR%\nwb_validation_summary.csv
echo Log: %DATASET_DIR%\runlog_convert_and_validate.txt
popd
endlocal
