@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "CARGO_BIN=%USERPROFILE%\.cargo\bin"
set "WINLIBS_BIN="

for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT.LLVM*") do (
  if exist "%%~fD\mingw64\bin\x86_64-w64-mingw32-gcc.exe" (
    set "WINLIBS_BIN=%%~fD\mingw64\bin"
    goto :winlibs_found
  )
)

if exist "%ProgramFiles%\WinLibs\mingw64\bin\x86_64-w64-mingw32-gcc.exe" (
  set "WINLIBS_BIN=%ProgramFiles%\WinLibs\mingw64\bin"
  goto :winlibs_found
)

echo [ERROR] WinLibs GNU toolchain not found.
echo         Install it first, for example:
echo         winget install --id BrechtSanders.WinLibs.POSIX.UCRT.LLVM -e
exit /b 1

:winlibs_found
set "PATH=%WINLIBS_BIN%;%CARGO_BIN%;%PATH%"
set "CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=x86_64-w64-mingw32-gcc"
set "CC_x86_64_pc_windows_gnu=x86_64-w64-mingw32-gcc"
set "AR_x86_64_pc_windows_gnu=x86_64-w64-mingw32-gcc-ar"

where npm >nul 2>nul || (
  echo [ERROR] npm not found in PATH.
  exit /b 1
)

where rustup >nul 2>nul || (
  echo [ERROR] rustup not found in PATH.
  exit /b 1
)

where x86_64-w64-mingw32-gcc >nul 2>nul || (
  echo [ERROR] x86_64-w64-mingw32-gcc not found in PATH.
  exit /b 1
)

rustup target list --installed | findstr /I /C:"x86_64-pc-windows-gnu" >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing Rust target x86_64-pc-windows-gnu...
  call rustup target add x86_64-pc-windows-gnu
  if errorlevel 1 exit /b 1
)

if not exist "node_modules" (
  echo [INFO] Installing npm dependencies...
  call npm ci
  if errorlevel 1 exit /b 1
)

echo [INFO] Building frontend...
call npm run build
if errorlevel 1 exit /b 1

echo [INFO] Building Windows executable...
call cargo build --release --manifest-path src-tauri\Cargo.toml --target x86_64-pc-windows-gnu
if errorlevel 1 exit /b 1

set "EXE_PATH=src-tauri\target\x86_64-pc-windows-gnu\release\work-pulse-checker.exe"
set "WEBVIEW2_LOADER=src-tauri\target\x86_64-pc-windows-gnu\release\WebView2Loader.dll"
if not exist "%EXE_PATH%" (
  echo [ERROR] Build finished but "%EXE_PATH%" was not found.
  exit /b 1
)

set "OUTPUT_DIR=build\exe"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
copy /Y "%EXE_PATH%" "%OUTPUT_DIR%\work-pulse-checker.exe" >nul
if errorlevel 1 exit /b 1

if not exist "%WEBVIEW2_LOADER%" (
  echo [ERROR] Build finished but "%WEBVIEW2_LOADER%" was not found.
  exit /b 1
)

copy /Y "%WEBVIEW2_LOADER%" "%OUTPUT_DIR%\WebView2Loader.dll" >nul
if errorlevel 1 exit /b 1

echo [DONE] EXE created:
echo        %CD%\%OUTPUT_DIR%\work-pulse-checker.exe
echo [DONE] Runtime DLL copied:
echo        %CD%\%OUTPUT_DIR%\WebView2Loader.dll
exit /b 0
