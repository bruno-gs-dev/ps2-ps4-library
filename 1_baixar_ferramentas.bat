@echo off
chcp 65001 >nul
title PS2 to PS4 - Baixar Ferramentas e FPKGi
cd /d "%~dp0"

echo ======================================================================
echo    PS2 to PS4 - Download do FPKGi e Configuracao de Ferramentas
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

python src\setup_tools.py

echo.
echo ======================================================================
echo    Processo finalizado. Pressione qualquer tecla para sair.
echo ======================================================================
pause >nul
