@echo off
echo Starting download loop at %date% %time%
:loop
echo.
echo ============================================================
echo ATTEMPT at %date% %time%
echo ============================================================
"c:\Users\kaleb\Documents\murkml\.venv\Scripts\python.exe" "c:\Users\kaleb\Documents\murkml\scripts\download_batch.py" --continuous-only --skip-merge --batch-size 15
echo Exit code: %ERRORLEVEL%
if %ERRORLEVEL% EQU 0 (
    echo Download completed successfully!
    goto done
)
echo Process died, restarting in 10 seconds...
timeout /t 10 /nobreak
goto loop
:done
echo All done at %date% %time%
pause
