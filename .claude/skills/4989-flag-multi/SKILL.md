---
name: 4989-flag-multi
description: 4989 DB MAIN 전체에서 같은 소유주 전화번호가 여러 물건에 나오면 다중물건(S44)을 표시하는 flag_multi.py 실행·수정 방법. 중복 매물/다중물건 검사, S44 갱신, 명단 입력 후 후처리에 사용.
---

# 다중물건(S44) 재계산 (flag_multi.py)

먼저 `4989-db` skill 의 안전 규칙을 따른다.

## 실행
```powershell
.\.venv\Scripts\python.exe flag_multi.py                 # dry-run + reports/report_multi_*.xlsx
.\.venv\Scripts\python.exe flag_multi.py --commit        # dll 백업 후 반영
# 옵션: --db <dll>  --fields owner_phone,tenant_phone  --min-digits 9  --report <경로>
```

## 규칙 (사용자와 합의된 것)
- 대상: MAIN 전체(모든 단지). 기본 비교 칸은 임대인 전화(`owner_phone`, S30).
- **전체 재계산**: 규칙대로 True/False 를 모두 다시 쓴다(손으로 찍은 True 도 규칙에 안 맞으면 꺼짐). 바뀌는 행만 UPDATE.
- 번호 정제 (`lib4989/dup.py` `extract_phones`):
  - 0으로 시작하는 9~11자리 번호를 뽑음. `010-5057-4443010-3955-1534` 처럼 붙은 번호는 두 개로 나눔.
  - 하이픈/공백/괄호 무시, 숫자만 같으면 같은 번호.
  - 0으로 시작하는 번호가 없는 줄(해외번호 `1-213-923-2920`)은 그 줄 숫자 전체를 한 번호로.
  - 9자리 미만(지역번호 없는 `3477-3839`, 생년월일)은 제외. 같은 단지 안 8자리 번호까지 잡으려면 `--min-digits 7` (오탐 증가).

## 리포트
- `변경` 시트: 바뀌는 행, 기존/새 S44, 겹치는 번호, 같은 번호를 쓰는 다른 물건.
- `번호별 그룹` 시트: 번호 → 물건 목록(많은 순).
- 커밋 후 다시 dry-run 해서 `변경: 0행` 인지 확인한다.
