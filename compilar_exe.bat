@echo off
setlocal
echo ========================================================
echo  Compilando nuevo descargar_copel.exe con PyInstaller...
echo ========================================================

python -m PyInstaller --onefile --clean --name descargar_copel copel_scraper\descargar_copel.py

if exist dist\descargar_copel.exe (
    copy /Y dist\descargar_copel.exe .\descargar_copel.exe
    echo.
    echo ========================================================
    echo  [OK] Ejecutable generado y actualizado con exito!
    echo       Ubicacion: %~dp0descargar_copel.exe
    echo ========================================================
) else (
    echo.
    echo [ERROR] Hubo un problema al generar el ejecutable.
)

:: Limpiar carpetas temporales generadas por PyInstaller
if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist
if exist descargar_copel.spec del /Q descargar_copel.spec

echo.
pause
