@echo off
REM ============================================================================
REM CAICAT v2.24 - Script de Compilación con Nuitka (OPTIMIZADO)
REM Mantiene el cache de Nuitka para compilaciones incrementales
REM ============================================================================
echo ============================================================================
echo CAICAT v2.24 - Compilación con Nuitka (modo incremental)
echo ============================================================================
echo.

REM 🔹 SOLO limpiar el output final, NO el cache de Nuitka
echo [*] Limpiando output anterior...
if exist caicat.v.2.24 rmdir /s /q caicat.v.2.24
REM ❌ NO borrar caicat.build (es el cache de Nuitka)
echo [OK] Limpieza completada
echo.

REM 🔹 Detectar número de cores para paralelizar
for /f "tokens=2 delims==" %%I in ('wmic cpu get NumberOfLogicalProcessors /value 2^>nul') do set NUM_CORES=%%I
if "%NUM_CORES%"=="" set NUM_CORES=4
echo [*] Usando %NUM_CORES% cores para compilación paralela
echo.

REM Compilar con Nuitka (SIN --remove-output para mantener cache)
echo [*] Compilando con Nuitka...
echo [*] Primera compilación: ~20-30 minutos (con matplotlib)
echo [*] Compilaciones siguientes: ~3-8 minutos (solo archivos modificados)
echo.

python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --enable-plugin=tk-inter ^
    --assume-yes-for-downloads ^
    --jobs=%NUM_CORES% ^
    --lto=no ^
    --output-dir=caicat.v.2.24 ^
    --output-filename=caicat.2.24.exe ^
    --include-data-dir=config=config ^
    --include-data-dir=resources=resources ^
    --include-data-file=caicat_transparente.png=caicat_transparente.png ^
    --include-data-file=manual.pdf=manual.pdf ^
    --include-package=openpyxl ^
    --include-package=PIL ^
    --include-package=cv2 ^
    --include-package=numpy ^
    --include-package=requests ^
    --include-package=exifread ^
    --include-package=pandas ^
    --include-package=matplotlib ^
    --python-flag=no_site ^
    --python-flag=no_warnings ^
    --company-name="CAICAT Project" ^
    --product-name="CAICAT" ^
    --file-version=2.24.0.0 ^
    --product-version=2.24.0 ^
    main.py

if %errorlevel% equ 0 (
    echo.
    echo ============================================================================
    echo [SUCCESS] Compilación exitosa!
    echo ============================================================================
    echo.
    echo Output: caicat.v.2.24\caicat.2.24.exe
    echo.
    echo PRÓXIMOS PASOS:
    echo   1. Verificar que caicat.v.2.24\resources\ffmpeg\ tenga ffmpeg.exe y ffprobe.exe
    echo   2. Ejecutar: python create_dist_zip_v224.py
    echo.
    echo NOTA: manual.pdf y caicat_transparente.png ya están empaquetados dentro del .exe
    echo.
) else (
    echo.
    echo ============================================================================
    echo [ERROR] Compilación fallida!
    echo ============================================================================
    echo.
    echo Revisar los errores arriba y corregir antes de reintentar.
    echo.
)
pause