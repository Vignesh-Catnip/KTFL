@echo off
echo Checking Ollama...
ollama --version
if errorlevel 1 (
  echo Ollama is not installed or not on PATH.
  echo Install from https://ollama.com/download/windows
  pause
  exit /b 1
)
echo Pulling vision model...
ollama pull llama3.2-vision:11b
echo Ollama setup complete.
pause
