# 실거래가 DB 무손실 최적화·서빙 빌드 패키지

기준: 첨부 main(9).py, schema_info(1).txt / 작성일: 2026-09-27 / 최종 정리: 2026-09-28

## 먼저 확인할 결론

원본 DB의 모든 행·컬럼·저장값·NULL·중복·직거래 구분·별도 취소 원장을 유지합니다. 원본은 read-only로 열고, SQLite Backup API로 일관된 스냅샷을 만든 뒤 사본만 가공합니다. 사용자 데이터에 대한 DELETE, TRIM, CAST, UPDATE, 기간/지역 필터, 중복 제거는 수행하지 않습니다. 서빙 추출도 각 테이블의 모든 행과 모든 컬럼을 복사합니다. 자동 증가 테이블을 추가한 경우 내부 sqlite_sequence의 high-water mark만 복원합니다.

**실제 470MB DB는 제공되지 않았습니다. 따라서 실제 절감 MB, 실제 데이터에서의 결과 동일성, 실서비스 속도·메모리·무중단은 아직 검증되지 않았습니다.** 포함된 테스트 결과는 합성 DB에 대한 결과이며, 안전·회귀 테스트 9개가 모두 통과했습니다. 로컬에서 실행한 보고서가 실제 판정 근거입니다.

200~300MB는 목표일 뿐 보장값이 아닙니다. 전국 20년치 매매·전세의 모든 데이터를 지금의 비압축 SQLite 스키마와 한 파일에 유지하면서 크기를 고정할 수는 없습니다. 예산 초과 시 빌드는 실패하고, 데이터를 제거해 맞추지 않습니다.

Render 무료 웹 서비스의 **512MB는 RAM 한도**입니다. SQLite 파일 크기 한도와 다릅니다. 470MB DB가 자동으로 470MB RAM을 점유하지도 않고, 250MB DB라고 Python/pandas·동시 요청·LRU 캐시를 포함한 RAM이 512MB 이하라고 보장되지도 않습니다. 무료 파일시스템은 영구 저장소가 아닙니다. [Render Compute Plans](https://render.com/docs/compute-plans), [Deploy for Free](https://render.com/docs/free).

## 파일 구성

| 파일 | 용도 |
|---|---|
| optimize_db.py | 원본 스냅샷 → 인덱스 정리 → VACUUM → 검증 → 새 최적화 DB |
| build_serving_db.py | 원본 스냅샷 → 원래 DDL로 서빙 DB 재생성 → 인덱스 정리 → 검증 |
| verify_db.py | 모든 사용자 테이블 정밀 비교 + 실제 main.py 함수로 응답 비교 |
| db_tools.py | 공통 구현. 세 스크립트와 같은 폴더에 필수 |
| main.py | 기존 코드에 avg_pyeong SELECT 누락만 수정한 선택 적용본 |
| main_original.py | 첨부 main(9).py와 바이트가 같은 보존본 |
| requirements_tools.txt | 로컬 검증에 필요한 pandas/numpy. 운영 requirements 대체용 아님 |
| schema_reference.sql | 첨부 구조를 SQL 실행 형식으로 정리. 실제 DB에 실행하지 않음 |
| test_tools.py, test_results.txt | 합성 회귀 테스트 및 이번 실행 결과 |

main.py의 HTML/JS, 기존 함수 인자, 라우트, SQL 조건, 테이블·컬럼 이름은 유지했습니다. 수정은 get_rankings SELECT에 `COALESCE(s.avg_pyeong, 0) as avg_pyeong` 한 줄 추가뿐입니다. 별도 macro_router.py와 관련 파일은 제공되지 않았고 수정·검증하지 않았습니다.

## 1. 스키마 진단

| 테이블 | 진단과 보존 정책 |
|---|---|
| apt_trades | 8컬럼 전체 유지. deal_amount INTEGER, floor INTEGER, exclu_use_ar REAL은 그대로 둠. deal_type NULL도 원값 유지 |
| apt_cancelled_trades | 5컬럼 복합 PK와 모든 행 유지. 취소 정보는 이 별도 테이블에 존재하며 첨부 스키마에는 해제 날짜 컬럼 자체가 없음 |
| apt_meta_master | 8컬럼 모두 유지. units_84_str/units_59_str는 랭킹에서 실제 사용하므로 제거 불가 |
| apt_rank_yearly_summary | 19컬럼 전체와 실제 저장 타입 유지. 타입 미선언 컬럼에 CAST/스키마 타입 추가를 하면 비교·정렬 의미가 달라질 수 있음 |
| _db_sync_touch | 작더라도 보존. 운영 동기화 의미를 추정해서 삭제하지 않음 |

현재 main.py는 apt_cancelled_trades를 조회하지 않습니다. 이 작업은 취소 원장을 보존하며, 취소 표시/제외 기능을 새로 추가하는 작업은 아닙니다. 이미 누락된 해제사유발생일을 만들어 낼 수도 없습니다. 미래 원천 DB에 추가된 취소 관련 컬럼은 동적 DDL·전체 컬럼 복사를 통해 그대로 보존합니다.

`apt_name` 공백은 검색 캐시, 이름 표시, 정확 매칭과 REPLACE 매칭, 메타 조인에 영향을 줍니다. 문자열 TRIM, 날짜를 정수로 바꾸기, 금액을 문자열/정수로 재변환하기는 호환성이 검증되지 않아 실행하지 않습니다. SQLite INTEGER는 값 크기에 따라 가변 길이로 저장되므로 INT를 SMALLINT로 선언하는 식의 변경이 단순 용량 해결책도 아닙니다. 텍스트 공간과 실제 typeof 분포는 실행 보고서에 관찰값으로 기록합니다.

### 인덱스 전략

| 인덱스 | optimize 기본 compact | serving 기본 serving | 근거 |
|---|---|---|---|
| idx_meta_norm(norm_name) | 유지 | 유지 | 메타 탐색·랭킹 조인 |
| idx_rank_lookup(deal_year, lawd_5) | 유지 | 유지 | 연도·지역 필터 |
| idx_trade_name(apt_name) | 제거 | 유지 | compact에서는 기존 복합 인덱스의 선두 컬럼과 중복. serving에서는 작은 이름 인덱스 유지 |
| idx_trades_lookup(apt_name, deal_date, deal_amount, exclu_use_ar, floor) | 유지 | 제거 | serving은 큰 5컬럼 인덱스를 줄임. 차트의 OR/REPLACE 때문에 원래 인덱스도 항상 탐색에 쓰이는 것은 아님 |
| idx_apt_trades_deal_type(deal_type) | 제거 | 제거 | 현재 조건은 NULL OR != 직거래. 단독 인덱스의 효용이 제한적이며 검증·측정 대상 |
| idx_apt_trades_agent(estate_agent_sgg_nm) | 제거 | 제거 | 첨부 main.py에는 이 컬럼을 조건으로 하는 쿼리가 없음 |
| 취소 테이블 PK 자동 인덱스 | 반드시 유지 | 반드시 유지 | 무결성 제약 |
| 그 밖의 인덱스/뷰/트리거 | 유지 | 유지 | 임의 삭제하지 않음 |

인덱스 이름만 보고 지우지 않습니다. 테이블, 컬럼 순서, UNIQUE, partial, COLLATION, DESC 여부를 검사하고 예상 정의와 다르면 중단합니다. `--profile preserve`는 인덱스를 모두 유지한 압축 대안입니다. `--profile compact`/`serving`은 두 빌더에서 모두 선택 가능합니다. 독립 빌더이므로 **두 빌더 모두 원래 backup.db를 입력으로 사용**하세요. compact 출력에는 idx_trade_name이 없어 기본 serving 프로필의 안전 전제와 맞지 않습니다.

현재 차트는 매 요청 `MAX(deal_date)`를 구하고, 이름 조건에 OR/REPLACE를 씁니다. 이름 인덱스만으로 이 스캔을 해결했다고 주장하지 않습니다. 날짜 단독 인덱스나 표현식 인덱스는 용량 증가, 실행 계획, 같은 날짜 내 순서를 바꾸므로 이번 기본안에는 추가하지 않았습니다. 보고서의 EXPLAIN QUERY PLAN과 before/after 시간으로 판단하세요. 성능 저하가 크면 preserve 결과를 선택하세요. 시간은 실행 환경/캐시 영향을 받는 관찰값이며 자동 성능 보장 게이트는 아닙니다.

### 기존 코드에서 확인한 오류와 제약

- `pyeong_avg` 분기는 `r['avg_pyeong']`을 읽지만 원래 SELECT에는 그 컬럼이 없습니다. 데이터가 있는 연도·지역에서 KeyError가 납니다. DB 최적화로 해결할 수 없어 동봉 main.py에 최소 수정했습니다.
- 차트의 이동평균은 달력상 20일이 아니라 **최근 최대 20건 거래**이며, 볼린저밴드도 동일한 거래 순서를 사용합니다. 기존 계산은 그대로 둡니다.
- 차트 `ORDER BY deal_date`, 랭킹의 점수만 사용하는 ORDER BY, 메타의 `LIMIT 1`에는 동률을 해결할 추가 정렬 키가 없습니다. 인덱스·SQLite 버전에 따라 동률 순서가 달라질 수 있습니다. 비교기는 정렬해서 차이를 숨기지 않고, 차이가 있으면 그 후보를 거부합니다.
- `VACUUM`은 명시적 INTEGER PRIMARY KEY가 없는 테이블의 숨은 rowid 번호를 바꿀 수 있습니다. 모든 선언 컬럼 값과 rowid 순회 시의 행 순서는 비교하지만 숨은 rowid 숫자 자체는 보장하지 않습니다. 첨부 main.py는 rowid를 참조하지 않습니다. 외부 수집기가 이를 거래 ID로 사용한다면 이 패키지를 적용하지 말고 먼저 그 의존성을 제거해야 합니다.
- 전국 UI 문구와 달리 랭킹 지역 매핑은 대구 8개 구·군만 구현돼 있습니다. 전세용 테이블/API도 없습니다. DB 파일을 빌드하는 것만으로 전국 랭킹·전세 화면이 활성화되지는 않습니다.

### 절감량 분석: 실측 전에는 숫자를 확정하지 않음

470MB 기준 목표 300MB에는 170MB(약 36.2%), 200MB에는 270MB(약 57.4%) 절감이 필요합니다. 첨부 DDL에는 행 수·텍스트 길이·페이지 사용량이 없어 이러한 절감이 가능한지 계산할 수 없습니다.

실행 보고서의 `before.objects`는 dbstat가 지원될 때 테이블·인덱스별 bytes/payload_bytes/unused_bytes를 기록합니다.

```
1차 예상 최종 크기(MB)
= (스냅샷 bytes − freelist_bytes − 제거 후보 인덱스 bytes) / 1,000,000

실제 최종 크기
= 위 값 − VACUUM 재패킹으로 회수된 공간 + 페이지 단위 배치 차이
```

테이블/유지 인덱스의 unused_bytes 전부가 회수 가능하다고 계산하면 과대평가됩니다. dbstat 미지원 환경에서는 인덱스별 추정값을 null로 표시하고, 최종 파일 크기 측정으로 판단합니다. 모든 보존 테이블의 payload만 이미 300MB를 넘으면 비압축 파일 300MB 목표는 구조적으로 불가능합니다. payload 하한은 인덱스·레코드/페이지 오버헤드를 제외한 하한일 뿐입니다.

예를 들어 **가정상** 원본 470MB, free 20MB, 제거 인덱스 80MB이면 1차 추정은 370MB입니다. free 40MB, 제거 인덱스 160MB이면 270MB입니다. 두 예시는 실제 DB 추정치가 아닙니다. 실제 절감 MB는 report.json의 saved_MB이며 MB=10^6 bytes입니다. MiB와 혼용하지 마세요.

VACUUM은 사본의 B-Tree를 다시 구성하고 빈 페이지를 회수합니다. 압축 파일 포맷으로 전환하거나 정렬/재색인만으로 반복 텍스트를 사전 압축하는 기능이 아닙니다. [SQLite VACUUM](https://www.sqlite.org/lang_vacuum.html), [DBSTAT](https://www.sqlite.org/dbstat.html), [Rowid Tables](https://www.sqlite.org/rowidtable.html).

## 2. Windows 안전 실행 순서

압축을 전용 작업 폴더(예: `C:\apt_db_work`)에 풀고, 실제 DB 파일을 그 폴더에 준비하세요. 운영 서버가 현재 읽고 있는 파일을 작업 출력 경로로 지정하지 마세요. DB와 WAL 파일이 있는 환경에서 .db만 탐색기로 복사하면 최신 변경이 누락될 수 있습니다. 첫 단계의 Backup API를 사용하세요. 로컬 수집기는 백업 시 잠시 멈추면 반복 업데이트로 인한 백업 지연을 피할 수 있습니다. 웹 서비스는 이 오프라인 작업 동안 기존 DB를 계속 읽을 수 있습니다.

PowerShell 또는 명령 프롬프트에서 아래 명령을 **한 줄씩 실행**하세요. 모든 스크립트는 Python 3.10 이상을 요구합니다. 운영과 같은 Python/pandas/numpy/SQLite 버전에서 검증하는 것이 좋습니다.

```powershell
cd C:\apt_db_work
python -m pip install -r requirements_tools.txt
python optimize_db.py --source apt_data_render_master.db --output backup.db --backup-only
```

backup.db 생성 후 원본과 별도의 안전한 위치에 보관하세요. 온라인 백업은 WAL에 커밋된 데이터도 포함한 일관된 복사본을 만듭니다. [SQLite Backup API](https://www.sqlite.org/backup.html).

첫 번째 실제 용량 조사:

```powershell
python optimize_db.py --source backup.db --output inspection.db --inspect-only
```

`inspection.db`는 생성하지 않고 `inspection.db.run\baseline.db`와 `report.json`을 만듭니다. report.json에서 객체별 크기와 예상 크기를 읽을 수 있습니다.

기존 코드 오류를 먼저 확인하려면(데이터가 있는 pyeong_avg 분기는 FAIL이 예상됨):

```powershell
python verify_db.py --before backup.db --after backup.db --main main_original.py --report original_code_check.json
```

그다음 수정본 main.py를 양쪽 DB에 동일하게 적용하여 DB 변경 효과를 비교합니다. 이 검증은 **기존 성공 분기를 그대로 유지하고 알려진 오류만 고친 코드**를 기준으로 합니다. 오류를 내던 pyeong_avg에 대해 ‘원본 성공 응답과 동일함’을 주장하지 않습니다.

```powershell
python optimize_db.py --source backup.db --output optimized.db --main main.py
python build_serving_db.py --source backup.db --output serving_master.db --main main.py
```

두 작업은 독립 후보입니다. serving 빌드는 optimized.db가 아니라 backup.db를 입력으로 사용하세요. 300MB를 엄격한 파일 예산으로 정하려면 새 출력 이름으로 실행합니다:

```powershell
python build_serving_db.py --source backup.db --output serving_300.db --main main.py --max-mb 300
```

초과하면 exit code 1이며 최종 출력은 만들지 않습니다. 이것은 **파일 예산** 검사이지 Render 메모리 검사나 SLA 보장이 아닙니다.

별도 재검증:

```powershell
python verify_db.py --before backup.db --after serving_master.db --main main.py --report verification.json
```

더 넓은 UI 입력 조합 검증(데이터가 많으면 매우 오래 걸림):

```powershell
python verify_db.py --before backup.db --after serving_master.db --main main.py --full --report verification_full.json
```

원본 코드의 정상 분기만 비교하는 보조 검증도 가능합니다. pyeong_avg는 제외되므로 완전 통과 판정이 아닙니다:

```powershell
python verify_db.py --before backup.db --after serving_master.db --main main_original.py --rank-types price_max,84_max,84_avg,59_max,59_avg,trade_cnt --report original_successful_branches.json
```

모든 사용자 테이블 값 비교는 `--full` 유무와 무관하게 **전수**입니다. 표본/전수 선택은 엔드포인트 입력 조합에만 적용됩니다. 검사 대상 DB에 동시 쓰기를 하지 마세요. 빌더는 자체 스냅샷으로 이를 보장하고, 독립 verify는 사용자가 고정한 파일 두 개를 비교합니다.

### 실패 시

기본 serving 후보가 응답 순서를 바꾸면 compact, 이어 preserve 순으로 원본 스냅샷에서 다시 빌드·검증합니다. compact 요청은 preserve로만 재시도합니다. 실패 후보는 rejected_프로필.db로 남고 report.json의 attempts에 원인이 기록됩니다. selected_profile이 실제 게시한 프로필이며, 자동 재시도는 동일성 검증을 생략하지 않습니다. 구조 오류/잘못된 인덱스 정의는 곧바로 중단합니다.

기존 파일을 덮어쓰지 않습니다. `출력명.run` 폴더도 재사용하지 않으므로 재시도에는 새 출력 이름을 사용하세요. 실패 원인은 그 폴더의 report.json에 남고, baseline.db와 candidate.db 또는 rejected_프로필.db는 진단용으로 유지됩니다. **실패한 candidate.db를 운영에 올리지 마세요.** 인덱스 변경 때문에 순서가 달라지면 다음을 시도할 수 있습니다:

```powershell
python optimize_db.py --source backup.db --output preserved.db --main main.py --profile preserve
```

preserve도 검증을 통과해야 합니다. 임의로 오류를 무시하는 옵션은 없습니다. 원본 데이터 자체의 NULL/잘못된 날짜 등으로 기존 코드가 오류를 내면 양쪽이 같은 오류라도 FAIL입니다.

원본 백업, 각 실행의 baseline, candidate, VACUUM 임시 공간이 별도로 필요합니다. 원본 크기의 4~6배 이상 여유를 확보하고, 인덱스 후보 재시도와 여러 빌드 기록까지 보관하면 10배 이상의 여유가 필요할 수 있습니다. SQLite VACUUM 자체도 추가 임시 공간을 사용합니다. 정상 게시에는 동일 파일시스템의 hard link를 사용하므로 일반 NTFS/ext4 작업 폴더를 권장하며, 지원되지 않는 파일시스템에서는 실패 후 원본을 유지합니다.

## 3. 자동 검증 범위

| 검사 | 방식 |
|---|---|
| 파일 무결성 | 양쪽 PRAGMA integrity_check, foreign_key_check |
| 스키마 | 테이블 집합·원래 테이블/뷰/트리거 DDL·컬럼 타입/default/PK·제약 인덱스 비교 |
| 원장 데이터 | 모든 사용자 테이블을 청크로 읽어 값·Python SQLite 반환 타입·NULL·BLOB·float 비트·중복·순회 순서 직접 비교; 전수 SHA-256도 기록 |
| 취소/직거래 | 취소 테이블 전수 비교, apt_trades 모든 컬럼 전수 비교, deal_type 분포도 보고 |
| 자동완성 | 원래 시작 코드와 같은 전체 이름 캐시 비교 + 검색어별 결과 배열 비교 |
| 차트 | 원본 함수 본문을 AST로 추출. 원시 거래 배열과 실제 응답의 dates/prices/details/stats/ma/upper/lower를 순서 포함 비교 |
| 랭킹 | 실제 get_rankings를 호출해 Top 50 응답 전체와 순서 비교. 7종 랭킹, 2010~2026 및 DB에 있는 추가 연도 |
| 크기·속도 | 전후 파일 bytes/MB, 테이블·인덱스 점유, 함수 실행시간 합계·최대, 대표 실행 계획 |

기본 엔드포인트 조합: 최대 20개 균등 분포 이름 표본에 직거래/공백 이름을 보강, 없는 이름 추가, 3/12/24/240개월 × 84/59/all × 직거래 포함/제외. 랭킹은 대구전체·각 구군·혼합 지역·빈 값·알 수 없는 지역을 확인합니다. `--full`은 모든 캐시 이름, UI의 3~36개월 및 4~20년, 구군의 모든 부분집합을 검사합니다. 임의의 모든 API 문자열/숫자 입력을 수학적으로 전수 검증하는 것은 아닙니다. `--months 12,24` 또는 `--rank-types ...`로 축소하면 보고서에 그 범위를 기록합니다.

Supabase 기반 함께 비교된 Top 10은 양쪽 `[]`로 고정해 외부 변동을 제거합니다. 게시판·OAuth·macro_router·실제 HTTP 직렬화와 브라우저 화면은 별도 통합 검증 대상입니다. FastAPI 앱을 import하지 않으므로 수집/네트워크 부작용은 발생하지 않습니다. AST 실행은 신뢰하는 첨부 main.py용이며 임의의 악성 Python을 격리하는 보안 장치가 아닙니다.

**PASS는 실제 비교한 입력 범위의 일치입니다.** 인덱스 선택과 동률 정렬의 특성상 모든 환경/미래 입력의 100% 일치를 무조건 보장하지 않습니다. 출력값을 정렬하거나 부동소수 오차를 허용해 차이를 덮지 않습니다. 비교기에서 예외나 차이가 하나라도 발생한 후보는 게시하지 않습니다. 더 보수적인 후보도 실패하면 빌드 전체가 실패합니다.

## 4. 교체와 롤백: 실행 중 파일 덮어쓰기 금지

동봉 main.py는 기존처럼 자기 폴더의 `apt_data_render_master.db`를 읽습니다. 서빙 DB를 로컬의 **새 배포 준비 폴더**에 그 이름으로 복사하세요. 파일을 단순히 serving_master.db라는 이름으로 두면 기존 코드가 읽지 않습니다.

```powershell
mkdir release_new
copy serving_master.db release_new\apt_data_render_master.db
copy main.py release_new\main.py
```

이 준비 폴더에는 기존 프로젝트의 requirements.txt, macro_router.py, 매크로 DB·HTML 등 나머지 필수 파일도 기존 그대로 준비해야 합니다. 이 패키지는 전체 운영 프로젝트를 포함하지 않습니다.

1. 기존 배포와 DB를 유지하고 새 리비전에 검증된 DB와 수정본을 함께 배치합니다.
2. 새 인스턴스가 새 DB로 시작하고 이름 캐시를 채운 뒤, 실제 `/api/search-apt`, `/api/chart-data`, `/api/rankings`를 확인합니다. 직거래 포함/제외, 날짜가 같은 거래, 84/59/all, 평당가 랭킹도 확인합니다.
3. 실제 브라우저에서 실거래 점·이동평균·볼린저밴드·랭킹·자동완성을 확인하고 Render의 peak RAM/응답시간/오류 로그를 관찰합니다. 추가 macro 라우트와 로그인도 점검합니다.
4. 새 리비전이 준비된 다음 트래픽을 전환하는 배포 경로를 사용합니다. 문제가 있으면 이전 **코드+DB 한 쌍**으로 롤백합니다.

실행 중 열린 SQLite 파일에 `copy /Y`나 `os.replace`를 하는 방식은 사용하지 마세요. Windows 파일 잠금, Linux의 기존 연결, 프로세스별 이름 캐시와 LRU 캐시, WAL 부속 파일 때문에 요청 간 세대 혼용이 생길 수 있습니다. 새 프로세스로 전환해야 캐시도 일관되게 갱신됩니다. 스크립트는 실제 배포나 트래픽 전환을 수행하지 않습니다. 무료 플랜의 sleep/cold start와 배포 구성까지 포함한 절대 무중단은 이 오프라인 작업으로 보장할 수 없습니다.

## 5. 전국·전세 확장 경로

원천 원장 DB에는 모든 이력과 원천 필드를 영구 보관합니다. 현재 빌더는 기존 5개 테이블을 모두 보존하고, 새 테이블을 발견하면 자동으로 빼지 않고 중단합니다. 예를 들어 전세 원장 `apt_rents`를 추가했다면:

```powershell
python build_serving_db.py --source future_master.db --output serving_future.db --main main.py --extra-table apt_rents
```

추가 테이블도 모든 컬럼·행·제약·인덱스를 보존합니다. 용도 미분류 테이블을 몰래 제외하지 않도록 설계했습니다. 수집 로그 등 정말 배포에서 뺄 수 있는 테이블은 실제 확장 스키마와 외부 의존성을 검토한 뒤 별도 허용 목록 설계가 필요합니다. 현 스키마의 5개 테이블은 전부 보존 대상이라, ‘미사용 테이블 제거’에서 얻을 절감량은 현재 0입니다.

전국 확장 전에는 이름 하나만 쓰는 단지 식별을 법정동코드·주소/단지 고유 ID 기반으로 전환해야 합니다. 지금은 이름이 같은 다른 지역 아파트가 섞일 수 있습니다. 매매와 전세도 별도 계약 종류·보증금·월세·취소 이력을 모델링해야 합니다. 기존 API 계약을 유지하는 어댑터를 두고 검증하는 별도 작업입니다.

모든 전국 데이터의 기존 SQL 호환성과 전수 접근성을 동시에 유지해야 한다면, 실측 결과에 맞는 저장/메모리 자원을 확보하는 것이 정직한 해법입니다. 파일 200~300MB를 고정하려면 지역/연도별 분할과 라우팅 또는 외부 DB 조회 같은 아키텍처 변경이 필요합니다. 그런 변경은 DB 파일 교체만으로 100% 호환되는 이번 범위를 벗어나므로 자동 수행하지 않았습니다.

원본 main.py의 LRU 캐시는 최대 128개의 거래 레코드 결과를 유지하고, pandas/NumPy 계산과 전체 단지명 캐시도 RAM을 사용합니다. 전국 확장 시에는 이 경로의 실제 peak RSS를 동시 요청 상황에서 측정해야 합니다. DB 파일 다이어트와 별개의 문제입니다.
