@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   ScreenShareSystem - Servidor
echo ============================================
echo.

echo Verificando se ja existe um servidor na porta 8765...
set killed=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo Encerrando instancia antiga - PID %%p - para evitar travamentos...
    taskkill /F /PID %%p >nul 2>&1
    set killed=1
)
if "%killed%"=="1" (
    timeout /t 1 /nobreak >nul
)

echo.
echo Verificando dependencias Python...
python -m pip show websockets >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias pela primeira vez, aguarde...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Falha ao instalar dependencias. Verifique se o Python esta instalado e no PATH.
        pause
        exit /b 1
    )
)

echo.
echo Iniciando servidor...
echo Para PARAR: feche esta janela ou pressione Ctrl+C.
echo (Fechar a janela encerra o processo corretamente, sem deixar nada travado.)
echo.
python server.py

echo.
echo Servidor encerrado.
pause
