@echo off
setlocal

REM Round-trip validation on synthetic all-modalities kitchen_sink_demo.

set DATASET_DIR=demo_data\kitchen_sink_demo
set REPO_DIR=%~dp0
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool

python scripts\run_roundtrip_validation.py ^
  --dataset-dir "%DATASET_DIR%" ^
  --conversion-table sur_nwb_conversion_table.csv ^
  --log-file "%DATASET_DIR%\runlog_roundtrip_validation.txt"

set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% NEQ 0 (
  echo Kitchen sink round-trip failed with code %EXIT_CODE%.
  echo See log: %DATASET_DIR%\runlog_roundtrip_validation.txt
  echo Press any key to close...
  pause >nul
  popd
  exit /b %EXIT_CODE%
)

echo.
echo Kitchen sink round-trip complete.
echo Summary: %DATASET_DIR%\roundtrip_validation_summary.csv
echo Log: %DATASET_DIR%\runlog_roundtrip_validation.txt
echo Press any key to close...
pause >nul
popd
endlocal
