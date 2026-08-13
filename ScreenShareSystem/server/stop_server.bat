@echo off
echo Procurando servidor na porta 8765...

set found=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo Encerrando processo PID %%p...
    taskkill /F /PID %%p
    set found=1
)

if "%found%"=="0" (
    echo Nenhum servidor rodando na porta 8765.
) else (
    echo Servidor encerrado.
)
pause
