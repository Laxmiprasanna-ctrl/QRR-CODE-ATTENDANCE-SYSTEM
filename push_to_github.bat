@echo off
echo ========================================
echo QRR - GitHub Setup Script
echo ========================================
echo.

REM Check if git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git is not installed!
    echo Please download from: https://git-scm.com/download/win
    pause
    exit /b 1
)

echo [1/6] Git is installed ✓
echo.

REM Initialize git repository
if not exist ".git" (
    echo [2/6] Initializing Git repository...
    git init
    echo Git repository initialized ✓
) else (
    echo [2/6] Git repository already initialized ✓
)
echo.

REM Add all files
echo [3/6] Adding files to Git...
git add .
echo Files added ✓
echo.

REM Show status
echo [4/6] Current status:
git status --short
echo.

REM Commit
echo [5/6] Creating commit...
set /p commit_msg="Enter commit message (or press Enter for default): "
if "%commit_msg%"=="" set commit_msg=Initial commit - QR Attendance System
git commit -m "%commit_msg%"
echo Commit created ✓
echo.

REM Remote repository
echo [6/6] Adding remote repository...
echo.
echo Please enter your GitHub repository URL
echo Example: https://github.com/username/repository-name.git
echo.
set /p repo_url="GitHub Repository URL: "

if "%repo_url%"=="" (
    echo [ERROR] Repository URL cannot be empty!
    pause
    exit /b 1
)

git remote remove origin >nul 2>&1
git remote add origin %repo_url%
git branch -M main

echo.
echo ========================================
echo Ready to push to GitHub!
echo ========================================
echo.
echo Repository: %repo_url%
echo Branch: main
echo.
set /p confirm="Push to GitHub now? (Y/N): "

if /i "%confirm%"=="Y" (
    echo.
    echo Pushing to GitHub...
    git push -u origin main
    echo.
    if errorlevel 1 (
        echo [ERROR] Push failed!
        echo.
        echo Common solutions:
        echo 1. Use Personal Access Token instead of password
        echo 2. Create token at: https://github.com/settings/tokens
        echo 3. Or use SSH key authentication
    ) else (
        echo ========================================
        echo SUCCESS! Project pushed to GitHub ✓
        echo ========================================
        echo.
        echo View at: %repo_url:.git=%
    )
) else (
    echo.
    echo Push cancelled. To push manually, run:
    echo   git push -u origin main
)

echo.
pause
