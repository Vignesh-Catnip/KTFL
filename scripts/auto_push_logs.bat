@echo off
:: Auto push error logs to GitHub when called
:: This script is triggered automatically when a backend error occurs

cd /d "%~dp0.."

:: Add and commit the error log
git add backend/logs/error.log
git add backend/logs/app.log

git commit -m "Server error log update [auto] %date% %time%"

:: Push using corporate proxy
git -c http.proxy=http://bflwcg.kalyanicorp.com:8080 -c http.sslVerify=false push origin main

exit /b 0
