@echo off
echo === LV2 System Starting ===
start "LV2-Backend" cmd /k "cd /d %~dp0backend && python main.py"
timeout /t 3
start "SPL-Simulator" cmd /k "cd /d %~dp0 && python -m spl_simulator.cli"
timeout /t 2
start "" "%~dp0frontend\index.html"
echo === All components launched ===
