@echo off
setlocal
chcp 65001 >nul 2>&1

:: 1. Check if 'py' (Windows Python Launcher) is available
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=py -3"
    goto :RUN
)

:: 2. Check if 'python' is in PATH
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=python"
    goto :RUN
)

:: 3. Check if 'python3' is in PATH
where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=python3"
    goto :RUN
)

:: 4. Fallback to user's LocalAppData Python without hardcoding username
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :RUN
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :RUN
)

echo [ERROR] Python 3.10+ is required to launch Tour of Nyx.
echo Please install Python from https://www.python.org/ or ensure it is added to your PATH.
exit /b 1

:RUN
if "%~1"=="" (
    %PY_EXE% "%~dp0tour\tour.py" core
) else (
    %PY_EXE% "%~dp0tour\tour.py" %*
)
