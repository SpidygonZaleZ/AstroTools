@echo off
set LOGFILE=build_log.txt
echo ===== Kompilacja rozpoczęta: %DATE% %TIME% ===== > %LOGFILE%

REM Tworzenie i aktywacja środowiska wirtualnego
echo Tworzenie srodowiska venv...
echo Tworzenie srodowiska venv... >> %LOGFILE%
python -m venv %~d0\python\venv >> %LOGFILE% 2>&1
call %~d0\python\venv\Scripts\activate.bat >> %LOGFILE% 2>&1

REM Aktualizacja pip i instalacja zależności
echo Instalacja pakietow...
echo Instalacja pakietow... >> %LOGFILE%
python -m pip install --upgrade pip >> %LOGFILE% 2>&1
pip install -r requirements.txt >> %LOGFILE% 2>&1
pip install pyinstaller >> %LOGFILE% 2>&1

REM Budowa pliku EXE
echo Budowanie aplikacji...
echo Budowanie aplikacji... >> %LOGFILE%
python -m PyInstaller --onefile --windowed ^
    --specpath .\ ^
    --workpath %~d0\python\build ^
    --distpath ..\ ^
    siril_prereg.pyw >> %LOGFILE% 2>&1

REM Dezaktywacja srodowiska
REM echo Dezaktywacja srodowiska...
REM echo Dezaktywacja srodowiska... >> %LOGFILE%
REM deactivate >> %LOGFILE% 2>&1

echo ===== Kompilacja zakonczona: %DATE% %TIME% ===== >> %LOGFILE%

REM Informacja dla użytkownika
echo.
echo Kompilacja zakonczona. Zobacz log w pliku %LOGFILE%
echo.
pause
