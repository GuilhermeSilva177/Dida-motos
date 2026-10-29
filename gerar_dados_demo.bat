@echo off
REM Popula o Dida Motos com dados de exemplo para apresentacao
REM (pecas, clientes, fornecedores, movimentacoes e ordens de servico).
REM Pode ser rodado de novo sem duplicar nada. Para limpar os dados de
REM demo antes de recriar, rode:  gerar_dados_demo.bat --limpar
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
echo === Gerando dados de demonstracao ===
python manage.py dados_demo %*
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao gerar os dados de demonstracao. Veja a mensagem acima.
    pause
    exit /b 1
)

echo.
echo === Pronto! ===
echo Contas de funcionario de exemplo (senha para as duas: Demo@1234):
echo   gerente.demo   (grupo Gerentes)
echo   mecanico.demo  (grupo Mecanicos)
echo.
pause
