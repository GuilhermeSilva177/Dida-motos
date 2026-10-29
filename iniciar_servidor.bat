@echo off
REM Inicia o Dida Motos localmente: ativa o venv, aplica migracoes
REM pendentes e levanta o servidor de desenvolvimento do Django.
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [ERRO] Venv nao encontrado em "venv\Scripts". Rode primeiro:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo === Aplicando migracoes pendentes ===
python manage.py migrate
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao aplicar as migracoes. Verifique o .env ^(DB_ENGINE, MySQL ligado, etc.^).
    pause
    exit /b 1
)

echo.
echo === Iniciando o servidor em http://127.0.0.1:8000/ ===
echo ^(Deixe esta janela aberta. Feche-a ou aperte CTRL+C para parar o servidor.^)
echo.
python manage.py runserver

pause
