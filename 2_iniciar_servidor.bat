@echo off
chcp 65001 >nul
title Servidor PS2-PS4 FPKGi
cd /d "%~dp0"

echo ======================================================================
echo    Iniciando Servidor HTTP PS2 to PS4 (FPKGi / GoldHEN)
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python 3 nao foi encontrado no sistema!
    echo Instale o Python 3 marcando a opcao "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

:: Abre o navegador padrao no painel de controle
start "" http://localhost:8080

:: Inicia o servidor Python
python src\server.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] O servidor foi encerrado com codigo de erro %ERRORLEVEL%.
    pause
)
