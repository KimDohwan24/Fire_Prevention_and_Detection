@echo off
chcp 65001 >nul
echo ========================================
echo   파이어가드 백엔드 및 프론트엔드 실행 중...
echo ========================================

:: 1. 백엔드(back) 실행
start "Fireguard Backend" cmd /k "cd /d %~dp0back && python app.py"

:: 2. 프론트엔드(front) 실행
start "Fireguard Frontend" cmd /k "cd /d %~dp0front && npm run dev"

echo 모든 서버 실행 창이 열렸습니다.
pause