@echo off
cd /d "%~dp0backend"
call .venv\Scripts\activate
uvicorn app.main:app --reload --port 8070
