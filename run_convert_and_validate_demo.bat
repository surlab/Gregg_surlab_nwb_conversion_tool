@echo off
setlocal

REM Dev double-click: demo dataset convert + validate, then open summary and reports.

set DATASET_DIR=demo_data\SeqBias_AstroBlock_NPX
set REPO_DIR=%~dp0
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool

python scripts\run_convert_and_validate.py --dataset-dir "%DATASET_DIR%" --open-results

set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% NEQ 0 (
  echo Demo convert + validate failed with code %EXIT_CODE%.
  echo See log: %DATASET_DIR%\runlog_convert_and_validate.txt
  echo Press any key to close...
  pause >nul
  popd
  exit /b %EXIT_CODE%
)

echo.
echo Demo run complete.
echo Summary: %DATASET_DIR%\nwb_validation_summary.csv
echo Log: %DATASET_DIR%\runlog_convert_and_validate.txt
echo Notebook: scripts\inspect_nwb.ipynb
echo Press any key to close...
pause >nul
popd
endlocal
