@echo off
chcp 65001 >nul
title PS2 to PS4 - Converter ISOs em fPKG
cd /d "%~dp0"

echo ======================================================================
echo    PS2 to PS4 - Conversor Automatico de ISOs em fPKG (Jak v2)
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

python src\convert_iso_to_pkg.py %*

echo.
echo ======================================================================
echo    Processo finalizado. Pressione qualquer tecla para sair.
echo ======================================================================
pause >nul
