@echo off
:: Define the default target
set DEFAULT_TARGET=help

if "%1" == "" (
    call :%DEFAULT_TARGET%
    goto :eof
) else (
    call :%1%
    goto :eof
)

:help
:: Show help for each of the batch file commands
echo Showing help for available commands:
for /f "tokens=1,2 delims=:" %%a in ('findstr ":" "%~f0" ^| findstr /v "::"') do (
    echo %%a:%%b
)
goto :eof

:lint
:: Format with black and lint with ruff
echo [+] Linting
python -m black .
goto :eof

:type-check
:: Run mypy
echo [+] Type checking
python -m mypy --config-file pyproject.toml . || echo [!] Type checking failed
goto :eof

:test
:: Run pytest
echo [+] Run tests
python -m pytest . || echo [!] Tests failed
goto :eof

:clean
:: Clean build artifacts
echo [+] Cleaning
for /r %%d in (__pycache__) do if exist %%d rd /s /q %%d
for /r %%f in (*.egg-info) do if exist %%f rd /s /q %%f
if exist poetry.lock del poetry.lock
if exist dist rd /s /q dist
goto :eof

:install_ghidra
:: Install Sighthouse Ghidra client on your system
call :check-env-ghidra
python .\src\sighthouse\client\install_ghidra.py %GHIDRA_INSTALL_DIR%
goto :eof

:install_ida
:: Install Sighthouse Ida client on your system
call :check-env-ida
python .\src\sighthouse\client\install_ida.py %IDA_DIR%
goto :eof

:install_binja
:: Install Sighthouse Binary Ninja client on your system
python .\src\sighthouse\client\install_binja.py
goto :eof

:check-env-ghidra
if "%GHIDRA_INSTALL_DIR%"=="" (
    echo [!] GHIDRA_INSTALL_DIR is undefined
    exit /b 1
)
goto :eof

:check-env-ida
if "%IDA_DIR%"=="" (
    echo [!] IDA_DIR is undefined
    exit /b 1
)
goto :eof

