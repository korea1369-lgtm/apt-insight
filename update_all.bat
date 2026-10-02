@echo off
chcp 65001 > nul
echo ========================================================
echo [1/4] 국토부 최신 실거래가 수집 중... (update_trades.py)
echo ========================================================
python update_trades.py
if %errorlevel% neq 0 (
    echo [오류] 실거래가 수집 중 문제가 발생했습니다.
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo [2/4] 아파트 랭킹 요약 데이터 재집계 중... (refresh_rank_summary.py)
echo ========================================================
python refresh_rank_summary.py
if %errorlevel% neq 0 (
    echo [오류] 랭킹 재집계 중 문제가 발생했습니다.
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo [3/4] 데이터베이스 인덱스 및 용량 최적화 중... (optimize_db.py)
echo ========================================================
python optimize_db.py

echo.
echo ========================================================
echo [4/4] 기존 서버 종료 및 최신 캐시 적용하여 재시작 중...
echo ========================================================
taskkill /f /im python.exe > nul 2>&1
timeout /t 1 > nul
start "TECH REALTY INSIGHT SERVER" python main.py

echo.
echo ========================================================
echo  모든 실거래가 및 랭킹 업데이트가 완료되었습니다!
echo  브라우저에서 Ctrl + F5를 눌러 확인해 주세요.
echo ========================================================
timeout /t 3
