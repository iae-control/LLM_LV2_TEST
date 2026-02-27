@echo off
chcp 65001 >nul
echo ==========================================
echo   SPL Winding Status Monitor - 통합 실행
echo ==========================================

echo.
echo [1/3] L2 Simulator 시작 (가상 L2 서버)...
start "L2 Simulator" cmd /k "cd /d %~dp0 && python -m l2_simulator.cli"
timeout /t 3 /nobreak >nul

echo [2/3] SPL Backend 시작...
start "SPL Backend" cmd /k "cd /d %~dp0 && python backend/main.py --l2-host 127.0.0.1 --l2-port 12147"
timeout /t 2 /nobreak >nul

echo [3/3] Frontend 열기...
start "" "%~dp0frontend\index.html"

echo.
echo 실행 완료!
echo   L2 Simulator : TCP Server on 0.0.0.0:12147
echo   SPL Backend  : TCP Client -^> 127.0.0.1:12147
echo                  API on http://localhost:8080
echo   Frontend     : frontend\index.html
echo.
echo 실제 L2 서버 접속 시:
echo   python backend/main.py --l2-host 130.1.1.30 --l2-port 12147
