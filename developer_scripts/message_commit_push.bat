REM comment: This script commits all changes and pushes with a default WIP (work in progress) message
call conda activate surlab_nwb_conversion_tool
call git status
set /p message=Please enter your commit message:
call git add --all
call git commit -m "%message%"
call git push
cmd /k
