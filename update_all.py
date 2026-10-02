import os
import sys
import subprocess
import time
import sqlite3

def run_step(step_name, cmd):
    print("=" * 60)
    print(f"[*] {step_name}")
    print("=" * 60)
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"\n[오류 발생] {step_name} 단계에서 실패했습니다.")
        sys.exit(res.returncode)
    print()

def main():
    # 1. 국토부 실거래가 수집
    run_step("[1/3] 국토부 최신 실거래가 수집 (update_trades.py)", "python update_trades.py")

    # 2. 랭킹 요약 재집계
    run_step("[2/3] 아파트 랭킹 요약 집계 (refresh_rank_summary.py)", "python refresh_rank_summary.py")

    # 3. DB 가벼운 최적화 (인덱스 통계 갱신)
    print("=" * 60)
    print("[3/3] DB 인덱스 통계 갱신 및 캐시 정리")
    print("=" * 60)
    try:
        conn = sqlite3.connect("apt_data_render_master.db")
        conn.execute("ANALYZE;")
        conn.close()
        print("-> DB 최적화 완료")
    except Exception as e:
        print(f"-> DB 최적화 건너뜀: {e}")
    print()

    # 4. 서버 재시작
    print("=" * 60)
    print("[서버 재시작] 기존 서버 종료 후 새 캐시로 구동")
    print("=" * 60)
    os.system("taskkill /f /im python.exe > nul 2>&1")
    time.sleep(1)
    os.system("start \"TECH REALTY INSIGHT SERVER\" python main.py")

    print("\n" + "=" * 60)
    print(" [완료] 실거래가 및 랭킹 업데이트가 정상적으로 끝났습니다!")
    print(" 브라우저에서 Ctrl + F5를 눌러 확인해 주세요.")
    print("=" * 60)
    time.sleep(3)

if __name__ == "__main__":
    main()
