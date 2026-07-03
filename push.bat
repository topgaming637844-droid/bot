@echo off
echo ==============================================
echo   Git Auto-Push Script for Windows
echo ==============================================
echo.

:: Check if git is initialized in this folder
git status >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git is not initialized or not found on PATH.
    echo Please make sure Git is installed and you ran 'git init' and set up a remote origin.
    pause
    exit /b
)

echo Adding all modified and new files...
git add -A

echo.
set /p commit_msg="Enter commit message (or press ENTER for 'Update bot files'): "
if "%commit_msg%"=="" (
    set commit_msg=Update bot files
)

echo.
echo Committing changes...
git commit -m "%commit_msg%"

echo.
echo Pushing changes to GitHub...
git push -u origin main

echo.
echo ==============================================
echo   Push completed!
echo ==============================================
pause
