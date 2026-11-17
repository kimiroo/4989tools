---
name: 4989-compact
description: 4989 DB(APT4989.dll, Jet 4.0 mdb)를 MS Access '압축 및 복구' 하는 compact_db.ps1 실행·수정 방법. DB 압축, 복구, 파일 크기 줄이기, 명단 입력 후 정리에 사용.
---

# DB 압축 및 복구 (compact_db.ps1)

먼저 `4989-db` skill 의 안전 규칙을 따른다.

## 실행
```powershell
powershell -ExecutionPolicy Bypass -File compact_db.ps1            # dry-run: 압축본 만들어 검증 후 삭제
powershell -ExecutionPolicy Bypass -File compact_db.ps1 -Commit    # 백업 후 교체
# 옵션: -Db <dll 경로>  (없으면 config.toml/config.local.toml 의 [db] path)
```

## 동작
- Access 프로그램 없이 Access 엔진 COM(`DAO.DBEngine.120`, 64비트 ACE 16.0)의 `CompactDatabase` 사용.
- 원본을 덮어쓰지 않고 `<dll>.compact-<시각>` 에 새로 쓴 뒤, 모든 테이블 행 수와 CollatingOrder 를 비교.
  같을 때만 원본을 `.bak-precompact-<시각>` 으로 복사하고 압축본으로 교체.
- 정렬 방식 유지: 운영 DB는 한국어(1042), E: 샘플 사본은 General(1033). 그 외 값이면 중단.
- `64` = dbVersion40 (Jet 4.0 형식 유지). 비밀번호는 config 에서 읽고 출력 안 함.
- `.ldb` 가 있으면(4989 사용 중) 시작 전/교체 직전 모두 중단.

## 주의
- 운영 DB(`\\10.13.57.71\apt4989`)는 SSH(키 인증) 세션에서 접근 거부 → 데스크톱 세션(예약 작업 Interactive)에서 실행.
- 교체 후 `import_4cha.py`/`flag_multi.py` dry-run 등으로 ODBC 로도 정상 열리는지 확인.
- 2026-11-17 운영 DB 압축: 9,007,104 → 8,916,992 bytes, 31개 테이블 행 수 동일(MAIN 25,643).
