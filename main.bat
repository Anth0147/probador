@echo off
title 🚀 Validador Masivo Teletrabajo Movistar
color 0B
cd /d "%~dp0"

echo ======================================================
echo   🚀 Iniciando entorno del validador Teletrabajo
echo ======================================================
echo.

:: Verificar si Python está instalado
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ No se encontró Python instalado.
    echo 🔗 Descarga e instala desde https://www.python.org/downloads/
    pause
    exit /b
)

echo 🧩 Paso 1: Verificando e instalando librerías necesarias...
python utl.py
if %errorlevel% neq 0 (
    echo ❌ Error durante la instalación de librerías.
    pause
    exit /b
)

echo.
echo 🚀 Paso 2: Ejecutando script principal...
python probar.py

echo.
echo ======================================================
echo 🧹 Ejecución finalizada. Presiona una tecla para salir.
echo ======================================================
pause >nul
