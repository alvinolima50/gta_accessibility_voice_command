@echo off
setlocal
cd /d "%~dp0"

if not exist "brain\.env" (
  echo [setup] brain\.env nao existe. Copiando .env.example...
  copy /y "brain\.env.example" "brain\.env" >nul
  echo [setup] Abra brain\.env e preencha DEEPGRAM_API_KEY antes de continuar.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Criando virtualenv em .venv ...
  python -m venv .venv || goto :fail
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r brain\requirements.txt || goto :fail
) else (
  call .venv\Scripts\activate.bat
)

start "" http://127.0.0.1:8765

cd brain
python main.py
set EXITCODE=%ERRORLEVEL%

echo.
echo [run] processo encerrado (exit %EXITCODE%).
echo Pressione qualquer tecla para fechar.
pause >nul
goto :eof

:fail
echo [setup] Falhou. Confira a mensagem acima.
pause
exit /b 1
