@echo off
REM ============================================================================
REM ZM Password Manager v2.0 - MSI Installer Build Script
REM Requires: WiX Toolset v3.14
REM ============================================================================

echo ============================================================================
echo   ZM Password Manager v2.0 - MSI Installer Build
echo ============================================================================
echo.

REM Check if executable exists
if not exist dist\ZMPasswordManager.exe (
    echo ERROR: Executable not found!
    echo Please run build.bat first to create the executable.
    pause
    exit /b 1
)

REM Check if WiX is installed
set WIXPATH=C:\Program Files (x86)\WiX Toolset v3.14\bin
if not exist "%WIXPATH%\candle.exe" (
    echo ERROR: WiX Toolset not found!
    echo Please install WiX Toolset v3.14 from https://wixtoolset.org/
    pause
    exit /b 1
)

echo [1/3] Compiling installer...
"%WIXPATH%\candle.exe" installer.wxs
if errorlevel 1 (
    echo ERROR: Compilation failed!
    pause
    exit /b 1
)
echo.

echo [2/3] Linking installer...
"%WIXPATH%\light.exe" installer.wixobj -o ZMPasswordManager.msi
if errorlevel 1 (
    echo ERROR: Linking failed!
    pause
    exit /b 1
)
echo.

echo [3/3] Cleaning up temporary files...
if exist installer.wixobj del installer.wixobj
if exist ZMPasswordManager.wixpdb del ZMPasswordManager.wixpdb
echo.

echo ============================================================================
echo   MSI INSTALLER CREATED!
echo ============================================================================
echo.
echo Installer: ZMPasswordManager.msi
echo.
dir ZMPasswordManager.msi | find "ZMPasswordManager.msi"
echo.
echo You can now distribute this MSI installer.
echo.
echo ============================================================================
pause
