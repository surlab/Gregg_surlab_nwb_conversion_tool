@echo off
setlocal

REM Launch the NWB inspection notebook (edit nwb_path in the first code cell).

set REPO_DIR=%~dp0..
pushd "%REPO_DIR%"
call conda activate surlab_nwb_conversion_tool
jupyter notebook scripts\inspect_nwb.ipynb
popd
endlocal
