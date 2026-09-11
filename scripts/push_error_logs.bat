@echo off
REM ============================================================
REM  push_error_logs.bat
REM  Manually run this on the Windows server AFTER an error occurs,
REM  to collect a sanitized diagnostic log and push it to GitHub
REM  so it can be pulled and inspected locally.
REM
REM  This script does NOT run automatically. You must run it
REM  yourself every time you want to share error logs.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%
set TIMESTAMP=%TIMESTAMP: =0%
set OUTDIR=diagnostics
set OUTFILE=%OUTDIR%\error_log_%TIMESTAMP%.txt

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

echo Collecting sanitized diagnostics from backend\logs\error.log ...

REM Strip lines that look like they might contain secrets/credentials
REM (DATABASE_URL, password=, api_key=, token=) before writing the
REM diagnostic file. This is a best-effort filter - always review the
REM output file yourself before pushing.
powershell -NoProfile -Command ^
  "Get-Content 'backend\logs\error.log' -Tail 500 | " ^
  "Where-Object { $_ -notmatch '(?i)(password|secret|api[_-]?key|token|DATABASE_URL)' } | " ^
  "Set-Content '%OUTFILE%'"

if not exist "%OUTFILE%" (
  echo No error.log found or nothing to collect.
  pause
  exit /b 1
)

echo.
echo Wrote sanitized diagnostic log to %OUTFILE%
echo Review this file BEFORE pushing - it must not contain invoice
echo content, credentials, or secrets.
echo.
set /p CONFIRM=Push this file to GitHub now? (y/n):
if /i not "%CONFIRM%"=="y" (
  echo Aborted. Nothing was pushed.
  pause
  exit /b 0
)

git add "%OUTFILE%"
git commit -m "Add sanitized diagnostic log %TIMESTAMP%"
git push

echo Done. Pull this on your local machine with: git pull origin main
pause
