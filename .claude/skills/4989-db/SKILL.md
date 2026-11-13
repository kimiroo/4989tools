---
name: 4989-db
description: 4989 부동산 프로그램 DB(APT4989.dll, Access mdb, MAIN 테이블)를 lib4989 로 읽고 쓰는 방법과 안전 규칙. 4989 DB 조회/수정, 새 엑셀 명단 가져오기 스크립트 작성, MAIN 컬럼(S0~S47) 매핑 변경을 할 때 사용.
---

# 4989 DB 작업 (lib4989)

## 구조
- `config.toml` — `[db]` 드라이버/테이블, `[columns]` **논리 이름 → MAIN 컬럼** 매핑 (`owner = 'S29'` 등).
  컬럼 용도가 바뀌면 여기만 고친다. 코드에서는 S번호를 직접 쓰지 말고 항상 논리 이름을 쓴다.
- `config.local.toml` (git 제외) — `[db] path`, `password`. 없으면 `config.local.example.toml` 을 복사해서 채운다.
  환경변수 `APT4989_PASSWORD` 가 있으면 그게 우선.
- `lib4989/`
  - `db.py` `Mdb`: 연결(연결 시 config 컬럼이 MAIN 에 있는지 검증), `fetch/insert/update/delete`(논리 이름),
    VARCHAR 길이 초과는 잘라 넣지 않고 `FieldTooLong`, `backup()`.
  - `sync.py` `ComplexSync`: 단지 하나를 (동, 호) 키로 읽어 두고 `apply()` 로 upsert, 변경 리포트 xlsx.
  - `merge.py` 병합 정책: `overwrite`, `prepend`, `append`, `fill_empty`, `keep`.
    `prepend/append` 는 줄 단위이고, 기존에 **글자까지 똑같은 줄**은 다시 넣지 않는다(엄격 비교).
  - `excel.py` `read_rows(path, sheet, {논리이름: 열문자}, start_row)`.
  - `text.py` 전화번호/면적(㎡→평)/평형 10단위/키 정규화.
  - `dup.py` 전화번호 추출과 다중물건 판정.

## 실행 환경
- Windows + Microsoft Access ODBC 드라이버. Python 은 프로젝트 `.venv` (`pip install -r requirements.txt`).
- 운영 DB는 UNC 경로(`\\서버\공유\APT4989.dll`). Git Bash 에서는 `\\` 가 깨지므로 PowerShell 로 실행하거나 config 경로를 쓴다.
- 콘솔 한글이 깨지면 `PYTHONUTF8=1`.

## 안전 규칙 (반드시)
1. 모든 쓰기 스크립트는 **기본 dry-run**(작업 후 롤백), `--commit` 일 때만 반영. `Mdb` 는 `commit()` 을 안 부르면 with 블록 끝에서 롤백한다.
2. `--commit` 전에 `db.backup()` 으로 dll 을 `.bak-타임스탬프` 로 복사 (`backup_before_commit = true`).
3. 운영 DB에 커밋하기 전에 사용자에게 dry-run 리포트를 보여 주고 확인받는다.
4. 처음엔 DB 사본(로컬 복사본)에서 commit → 다시 실행해서 변경 0건(멱등)인지 확인한다.
5. 조건 없는 DELETE 금지(`Mdb.delete` 가 거부함). 기존 단지 행은 지우지 말고 갱신한다.
6. 리포트는 `reports/` 에 저장 (git 제외, 개인정보 포함).

## 새 가져오기 작업 만들기
`import_2cha.py` + `import_2cha.toml` 을 본보기로 한다.
1. `<작업>.toml` 에 엑셀 경로/시트/시작 행, `[source.columns]` 열 매핑, 대상 단지, 필드별 병합 정책을 적는다.
2. 엑셀 행을 물건 단위로 묶는다. 보통 동/호가 있는 행이 첫 행이고, 아래 빈 행들은 공유자.
3. 물건마다 `sync.apply({'dong':..,'ho':..}, {논리이름: 값}, policy=..., allow_insert=..., source='엑셀 N행')`.
   - 템플릿(동/호 행)이 이미 있는 단지는 `allow_insert=False` 로 두고, 없는 동/호는 오류로 리포트한다.
4. `sync.write_report(...)`, 요약을 출력하고, `--commit` 일 때만 `db.commit()`.

```python
from lib4989 import load_config, Mdb, ComplexSync
cfg = load_config('config.toml')
with Mdb(cfg) as db:
    sync = ComplexSync(db, '반포 자이', key_fields=('dong', 'ho'))
    sync.apply({'dong': 101, 'ho': 1201}, {'owner': '홍길동'},
               policy={'owner': 'append'}, allow_insert=False, source='3행')
    sync.write_report('reports/report.xlsx')
    # db.commit()   # 사용자 확인 후에만
```

## 칸 사용 관례 (MAIN)
- S1 단지, S2 평형(평 10단위 내림), S3 동(상가는 층), S4 호, S5 전용㎡, S6 평.
- S29 임대인 이름, S30 임대인 전화, S28 상담(LONGCHAR, 상세·로그용), S36 비고(250자, **핵심만**), S44 다중물건(BIT).
- 상세 정보(현주소, 면적 원본 숫자 등)는 상담(S28)에 넣고 비고는 짧게 유지한다.
- 새로 넣는 기록은 기존 기록 **뒤에** 붙인다(`append`).
