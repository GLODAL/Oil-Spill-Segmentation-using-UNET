@echo off
title S3 Connection Test
color 0E

echo ============================================
echo   S3 Connection Test
echo ============================================
echo.

set AWS_ACCESS_KEY_ID=PB1VCH7O58UFUM53PTBT
set AWS_SECRET_ACCESS_KEY=vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj

cd /d "%~dp0backend"

:: Find Python
set PYTHON_EXE=
if exist "C:\ProgramData\anaconda3\python.exe" set PYTHON_EXE=C:\ProgramData\anaconda3\python.exe
if "%PYTHON_EXE%"=="" if exist "%USERPROFILE%\anaconda3\python.exe" set PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe
if "%PYTHON_EXE%"=="" set PYTHON_EXE=python

echo Using: %PYTHON_EXE%
echo.
echo Testing S3 connection to rgw.glodal-inc.net...
echo (If this hangs, you need VPN)
echo.

"%PYTHON_EXE%" -c "
import boto3, sys
try:
    s3 = boto3.client('s3',
        endpoint_url='https://rgw.glodal-inc.net',
        aws_access_key_id='PB1VCH7O58UFUM53PTBT',
        aws_secret_access_key='vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj',
        region_name='us-east-1')
    pag = s3.get_paginator('list_objects_v2')
    keys = []
    for pg in pag.paginate(Bucket='Inference_Oil_Spill_segmentation',
                           Prefix='oil_spill_brazil/Output/Oil_Spill_Postprocessed_v15'):
        for obj in pg.get('Contents', []):
            if obj['Key'].endswith('_clean.tif'):
                keys.append(obj['Key'])
    print(f'SUCCESS: Found {len(keys)} clean.tif files')
    for k in keys[:5]:
        print(f'  {k.split(\"/\")[-1]}')
    if len(keys) > 5:
        print(f'  ... and {len(keys)-5} more')
except Exception as e:
    print(f'FAILED: {e}')
    print()
    print('Common causes:')
    print('  - Not connected to company VPN/network')
    print('  - Wrong credentials')
    print('  - Firewall blocking rgw.glodal-inc.net')
    sys.exit(1)
"

echo.
pause
