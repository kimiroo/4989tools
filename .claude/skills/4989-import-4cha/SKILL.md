---
name: 4989-import-4cha
description: 4차명단.xlsx(신반포4차 소유주 명단) 를 4989 DB 의 '한신4차' 단지에 넣는 import_4cha.py 실행·수정 방법. 4차명단 재입력, 명단 갱신, 입력 규칙 질문에 사용.
---

# 4차명단 → 한신4차 (import_4cha.py)

먼저 `4989-db` skill 의 안전 규칙을 따른다.

## 실행
```powershell
.\.venv\Scripts\python.exe import_4cha.py                 # dry-run + reports/report_4cha_*.xlsx
.\.venv\Scripts\python.exe import_4cha.py --commit        # dll 백업 후 반영
# 옵션: --db <dll 경로>  --excel <엑셀 경로>  --report <리포트 경로>
```
설정은 `import_4cha.toml` (엑셀 열 매핑, 대상 단지, 필드별 병합 정책).

## 입력 규칙
- 시트 `Sheet1`, 2행부터. 열: A 단지(`신반포4차`), B 동(`201동`), C 호실, D 이름, E 전화번호.
  엑셀 1행 = 물건 1건 (2차와 달리 공유자 행이 따로 없음).
- 엑셀 단지명 `신반포4차` 는 운영 mdb 에서 `한신 4차`(1212행). A열이 다르면 경고 후 무시.
  `E:\payload\Desktop\4989\4989` 샘플 DB 는 `한신4차`(띄어쓰기 없음) → `--complex 한신4차`.
- mdb 템플릿 동/호만 갱신(`allow_insert=false`). 없는 동/호는 오류로 리포트.
- S29 이름: D열을 쉼표로 나눠 한 줄에 한 명. `(거주)`, `(대표 …)` 같은 메모는 그대로.
- S30 전화: E열을 쉼표로 나눠 한 줄에 하나(`format_phone`). `-` 는 번호 없음.
- 이름/전화 둘 다 빈 행은 경고 후 건너뜀.
- 상담(S28)/비고(S36)/평형 등 다른 칸은 건드리지 않음.
- 병합: `append`, 중복 판정은 줄이 글자까지 같을 때만(엄격).

## 확인 포인트
- 샘플 DB 사본(`E:\payload\Desktop\4989\4989\APT4989.dll` 복사본)으로 2026-11-17 검증:
  1209행 중 1207건 대상 → update 1203, unchanged 4, 오류 0. 사본 커밋 후 재실행 시 1207건 전부 unchanged.
  운영 DB(`\\10.13.57.71\apt4989`) dry-run(2026-11-17): update 1195, unchanged 12, 오류 0. 아직 커밋 안 함.
- SSH(키 인증) 세션에서는 UNC 접근이 거부됨 → 데스크톱 세션 예약 작업으로 실행하거나 `net use` 로 연결.
- 입력 후에는 `4989-flag-multi` 로 다중물건(S44)을 다시 계산한다.
