# 4989 mdb 도구 (`lib4989`)

4989 부동산 프로그램 DB(`APT4989.dll`, Access mdb, `MAIN` 테이블)를 안전하게 읽고 쓰는 라이브러리와 작업 스크립트.

## 구성

| 파일 | 역할 |
|---|---|
| `config.toml` | 드라이버/테이블 + **논리 이름 → MAIN 컬럼(S0~S47)** 매핑. 컬럼 용도가 바뀌면 여기만 수정 |
| `config.local.toml` | (git 제외) DB 경로, 비밀번호. `config.local.example.toml` 을 복사해서 작성 |
| `lib4989/db.py` | `Mdb`: 연결, 컬럼 검증, 논리 이름으로 fetch/insert/update/delete, VARCHAR 길이 검사, 백업 |
| `lib4989/sync.py` | `ComplexSync`: 단지 단위 (동,호) upsert + 병합 정책 + 변경 리포트(xlsx) |
| `lib4989/merge.py` | 병합 정책 `overwrite / prepend / append / fill_empty / keep` |
| `lib4989/excel.py` | 엑셀 시트를 `논리이름 = 열문자` 매핑으로 읽기 |
| `lib4989/text.py` | 전화번호/면적/평/키 정규화 |
| `lib4989/dup.py` | 전화번호 추출, 다중물건 판정 |
| `import_2cha.py` + `import_2cha.toml` | 2차명단 → '한신 2차' |
| `flag_multi.py` | 다중물건(S44) 재계산 |
| `.claude/skills/` | Claude Code skill: `4989-db`, `4989-import-2cha`, `4989-flag-multi` |

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config.local.example.toml config.local.toml   # 경로/비밀번호 채우기
```

Windows + Microsoft Access ODBC 드라이버가 필요합니다.

## 공통 규칙

- 모든 스크립트는 기본 **dry-run**(작업 후 롤백). `--commit` 일 때만 dll 을 `.bak-타임스탬프` 로 백업한 뒤 반영.
- 리포트는 `reports/` 에 저장 (git 제외, 개인정보 포함).
- `--db` 로 DB 경로를 덮어쓸 수 있음. 처음엔 사본에 돌려 보고, 다시 돌렸을 때 변경 0건인지 확인.

## 2차명단 입력

```powershell
.\.venv\Scripts\python.exe import_2cha.py            # dry-run + 리포트
.\.venv\Scripts\python.exe import_2cha.py --commit   # 반영
```

- 아파트: 기존 동/호 템플릿에 이름(S29)/전화(S30)/상담(S28, `현주소: …`)을 기존 기록 **뒤에** 추가. 비고는 그대로.
- 상가: 층/호/면적으로 새 행. 면적 원본 숫자·현주소는 상담, 다물건 표시만 비고.
- 이미 들어간 줄(글자까지 같은 줄)은 다시 넣지 않으므로 재실행해도 안전.

## 다중물건(S44) 재계산

```powershell
.\.venv\Scripts\python.exe flag_multi.py             # dry-run + 리포트 (변경 행 / 번호별 그룹)
.\.venv\Scripts\python.exe flag_multi.py --commit
```

- MAIN 전체에서 같은 임대인 번호가 2개 이상 물건에 나오면 True, 아니면 False (전체 재계산).
- 번호 정제: 붙은 번호 분리, 9자리 미만 제외(`--min-digits`), 해외번호는 줄 숫자 전체.
- 비교 칸 변경: `--fields owner_phone,tenant_phone`

## 새 작업 만들 때

```python
from lib4989 import load_config, Mdb, ComplexSync

cfg = load_config('config.toml')
with Mdb(cfg) as db:
    sync = ComplexSync(db, '반포 자이', key_fields=('dong', 'ho'))
    sync.apply({'dong': 101, 'ho': 1201}, {'owner': '홍길동'},
               policy={'owner': 'append'}, allow_insert=False, source='3행')
    sync.write_report('reports/report.xlsx')
    db.commit()          # 안 부르면 with 블록 끝에서 롤백
```

자세한 규칙은 `.claude/skills/*/SKILL.md` 참고.
