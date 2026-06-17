@echo off
title Oil Spill Segmentation Viewer
color 0A

echo ============================================
echo   Oil Spill Segmentation - UNet Model
echo   Glodal Inc., Japan
echo ============================================
echo.

:: ── Credentials + Config ─────────────────────────────────────
set AWS_ACCESS_KEY_ID=PB1VCH7O58UFUM53PTBT
set AWS_SECRET_ACCESS_KEY=vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj
set AWS_DEFAULT_REGION=us-east-1
set AWS_REQUEST_CHECKSUM_CALCULATION=when_required
set S3_ENDPOINT=https://rgw.glodal-inc.net
set S3_BUCKET=Inference_Oil_Spill_segmentation
set S3_MASK_ROOT=oil_spill_brazil/Output/Oil_Spill_Postprocessed_v15
set S3_SAR_ROOT=oil_spill_brazil/Output/Preprocess_After_SNAP_
set PORT=8050
set USE_S3_CACHE=true
set S3_CACHE_ROOT=oil_spill_brazil/Output/Viewer_Cache

:: ── Fix PROJ conflict with PostgreSQL/PostGIS ────────────────
:: PostgreSQL 16 installs an old proj.db that breaks rasterio.
:: Force PROJ to use Anaconda's correct version instead.
if exist "C:\ProgramData\anaconda3\Library\share\proj\proj.db" (
    set PROJ_DATA=C:\ProgramData\anaconda3\Library\share\proj
    set PROJ_LIB=C:\ProgramData\anaconda3\Library\share\proj
    echo [OK] PROJ pointing to Anaconda: %PROJ_DATA%
) else (
    echo [WARN] Could not find Anaconda proj.db - app.py will try to fix this
)
echo.

:: ── Navigate to backend ───────────────────────────────────────
cd /d "%~dp0backend"

:: ── Find Python ───────────────────────────────────────────────
set PYTHON_EXE=
if exist "C:\ProgramData\anaconda3\python.exe"          set PYTHON_EXE=C:\ProgramData\anaconda3\python.exe
if "%PYTHON_EXE%"=="" if exist "%USERPROFILE%\anaconda3\python.exe" set PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe
if "%PYTHON_EXE%"=="" if exist "C:\ProgramData\miniconda3\python.exe" set PYTHON_EXE=C:\ProgramData\miniconda3\python.exe
if "%PYTHON_EXE%"=="" where python >nul 2>&1 && set PYTHON_EXE=python

if "%PYTHON_EXE%"=="" (
    echo ERROR: Python not found. Open Anaconda Prompt and run:
    echo   cd /d "%~dp0backend"
    echo   set AWS_ACCESS_KEY_ID=PB1VCH7O58UFUM53PTBT
    echo   set AWS_SECRET_ACCESS_KEY=vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj
    echo   set PROJ_DATA=C:\ProgramData\anaconda3\Library\share\proj
    echo   python app.py
    pause
    exit /b 1
)
echo [OK] Python: %PYTHON_EXE%
echo.

:: ── Install deps if missing ───────────────────────────────────
"%PYTHON_EXE%" -c "import fastapi, uvicorn, boto3, rasterio, PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing packages...
    "%PYTHON_EXE%" -m pip install fastapi "uvicorn[standard]" boto3 rasterio Pillow numpy --quiet
)
echo [OK] Dependencies ready.
echo.

:: ── Open browser ─────────────────────────────────────────────
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:%PORT%"

echo Starting server at http://localhost:%PORT%
echo Keep this window open. Close it to stop the server.
echo ============================================
echo.
"%PYTHON_EXE%" app.py

echo.
echo Server stopped.
pause
