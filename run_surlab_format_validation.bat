@echo off
setlocal

REM Validate SurLab format conventions for one dataset (presence, naming, types).

if "%~1"=="" (
  echo Usage: run_surlab_format_validation.bat ^<dataset-dir^>
  echo Example: run_surlab_format_validation.bat demo_data\SeqBias_AstroBlock_NPX
  exit /b 2
)

set DATASET_DIR=%~1
set REPO_DIR=%~dp0
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool

python scripts\run_surlab_format_validation.py --dataset-dir "%DATASET_DIR%" --conversion-table sur_nwb_conversion_table.csv
set EXIT_CODE=%ERRORLEVEL%

echo.
echo Summary: %DATASET_DIR%\surlab_format_validation_summary.csv
echo Log: %DATASET_DIR%\runlog_surlab_format_validation.txt
popd
endlocal
exit /b %EXIT_CODE%
