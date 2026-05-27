@echo off
setlocal

REM Stage-1 SurLab -> NWB demo run (Windows)
REM Update dataset path as needed. This loops over all session subfolders
REM and writes each NWB directly inside its own session directory.
set REPO_DIR=%~dp0..
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool
call conda info --envs

set DATASET_DIR=demo_data\SeqBias_AstroBlock_NPX
set CONVERSION_TABLE=conversion_table.csv
set OUTPUT_MATRIX=%DATASET_DIR%\session_validation_matrix.csv
set LOG_FILE=Runlog_stage1_conversion.log

echo Running stage-1 conversion... > "%LOG_FILE%"
echo Dataset: %DATASET_DIR% >> "%LOG_FILE%"
echo Conversion table: %CONVERSION_TABLE% >> "%LOG_FILE%"
echo Output matrix: %OUTPUT_MATRIX% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

python scripts\run_stage1_conversion.py ^
  --dataset-dir "%DATASET_DIR%" ^
  --conversion-table "%CONVERSION_TABLE%" ^
  --output-matrix "%OUTPUT_MATRIX%" ^
  --stage 1 >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
  echo Stage-1 conversion failed with code %ERRORLEVEL%.
  echo Stage-1 conversion failed with code %ERRORLEVEL%. >> "%LOG_FILE%"
  echo See log: %LOG_FILE%
  echo Press any key to close...
  pause > nul
  popd
  exit /b %ERRORLEVEL%
)

echo Stage-1 conversion completed.
echo Stage-1 conversion completed. >> "%LOG_FILE%"
echo See log: %LOG_FILE%
echo Press any key to close...
pause > nul
popd
endlocal

