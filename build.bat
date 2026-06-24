@echo off
REM ============================================================================
REM SecureVault v2.0 - Build Script for Windows
REM
REM This script automates the build process for SecureVault:
REM 1. Checks Python installation
REM 2. Installs required dependencies
REM 3. Builds standalone executable using PyInstaller
REM
REM Output: dist/SecureVault.exe (~20MB)
REM ============================================================================

echo ============================================================================
echo   SecureVault v2.0 - Build Script
echo ============================================================================
echo.

REM Check if Python is installed and accessible
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] Checking Python version...
python --version
echo.

REM Install project dependencies
echo [2/5] Installing dependencies...
echo Installing cryptography and ttkbootstrap...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

REM Install PyInstaller for building executable
echo [3/5] Installing PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    pause
    exit /b 1
)
echo.

REM Clean up previous build artifacts
echo [4/5] Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__
echo Cleaned previous build artifacts
echo.

REM Build the standalone executable
echo [5/5] Building executable...
echo This may take 2-3 minutes...
echo.
python -m PyInstaller SecureVault.spec
if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo   BUILD SUCCESSFUL!
echo ============================================================================
echo.
echo Executable created: dist\SecureVault.exe
echo.
echo File size:
dir dist\SecureVault.exe | find "SecureVault.exe"
echo.
echo You can now run the application:
echo   dist\SecureVault.exe
echo.
echo To create an MSI installer (requires WiX Toolset):
echo   1. Install WiX Toolset v3.14 from https://wixtoolset.org/
echo   2. Run: build_msi.bat
echo.
echo ============================================================================
pause
