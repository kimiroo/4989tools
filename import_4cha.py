"""4차명단.xlsx (Sheet1: 단지/동/호실/이름/전화번호) → 4989 MAIN '한신4차'.

- 엑셀 1행 = 물건 1건. mdb 에 이미 있는 동/호 템플릿 행만 갱신 (새 행 INSERT 안 함)
- 이름(S29): 쉼표로 나뉜 공유자를 한 줄에 한 명씩, 기존 기록 '뒤에' 추가. '(거주)' 같은 메모는 그대로
- 전화(S30): 쉼표로 나뉜 번호를 한 줄에 하나씩, 기존 기록 '뒤에' 추가. '-' 는 번호 없음
- 상담/비고/평형 등 다른 칸은 건드리지 않음
- 중복 판정은 줄이 글자까지 같을 때만 (lib4989.merge 엄격 비교)

기본은 DRY-RUN(변경 후 롤백). 실제 반영은 --commit.

    python import_4cha.py                       # dry-run, 리포트만 생성
    python import_4cha.py --db "\\\\10.13.57.71\\apt4989\\APT4989.dll" --commit
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from lib4989 import ComplexSync, Mdb, load_config, load_toml, read_rows
from lib4989.text import clean, phones, unique

HERE = Path(__file__).resolve().parent

_NO_VALUE = {'-', '–', '—'}


def split_list(v) -> list[str]:
    """'홍길동, 김철수(거주)' → ['홍길동', '김철수(거주)']. 쉼표/줄바꿈 구분, '-' 는 버림."""
    s = clean(v)
    if s is None:
        return []
    parts = (p.strip() for p in re.split(r'[,\n\r]+', s))
    return [p for p in parts if p and p not in _NO_VALUE]


def norm_dong(v) -> str | None:
    """'201동' → '201'."""
    s = clean(v)
    return re.sub(r'\s*동$', '', s) if s else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default=HERE / 'config.toml')
    ap.add_argument('--job', default=HERE / 'import_4cha.toml')
    ap.add_argument('--db', help='mdb(dll) 경로 (config.toml [db] path 덮어씀)')
    ap.add_argument('--excel', help='엑셀 경로 (job [source] excel 덮어씀)')
    ap.add_argument('--complex', help="mdb 단지명 (job [target] complex 덮어씀. DB마다 '한신4차'/'한신 4차' 로 다름)")
    ap.add_argument('--report', help='리포트 xlsx 경로 (기본: reports/report_4cha_<시각>.xlsx)')
    ap.add_argument('--commit', action='store_true', help='실제로 반영 (없으면 dry-run)')
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    job = load_toml(args.job)
    src, tgt = job['source'], job['target']
    if args.complex:
        tgt['complex'] = args.complex
    policy = job.get('policy', {})
    excel = Path(args.excel) if args.excel else (Path(args.job).resolve().parent / src['excel'])
    report = Path(args.report) if args.report else HERE / 'reports' / f'report_4cha_{datetime.now():%Y%m%d-%H%M%S}.xlsx'
    report.parent.mkdir(parents=True, exist_ok=True)

    rows = list(read_rows(excel, src['sheet'], src['columns'], start_row=src.get('start_row', 2)))
    warnings: list[str] = []
    items = []
    for rno, r in rows:
        dong, ho = norm_dong(r['dong']), clean(r['ho'])
        if dong is None or ho is None:
            warnings.append(f'{rno}행: 동/호 없음, 무시')
            continue
        want = src.get('complex_value')
        if want and clean(r['complex']) != want:
            warnings.append(f'{rno}행: 단지 {r["complex"]!r} ≠ {want!r}, 무시')
            continue
        names = '\n'.join(unique(split_list(r['name']))) or None
        tel = '\n'.join(phones(*split_list(r['phone']))) or None
        if names is None and tel is None:
            warnings.append(f'{rno}행 ({dong}동 {ho}호): 이름/전화 모두 비어 있음, 건너뜀')
            continue
        items.append((rno, dong, ho, names, tel))

    print(f'엑셀: {excel.name} / {len(rows)}행 중 입력 대상 {len(items)}건')

    db = Mdb(cfg, args.db)
    with db:
        if args.commit and cfg.db.backup_before_commit:
            print(f'백업: {db.backup()}')
        sync = ComplexSync(db, tgt['complex'], key_fields=('dong', 'ho'))
        print(f'mdb: {db.path} / {sync.complex_name!r} 기존 {sync.loaded}행')
        if sync.loaded == 0:
            print(f'[오류] mdb 에 단지 {tgt["complex"]!r} 가 없음. import_4cha.toml [target] complex 확인')
            return 1

        for rno, dong, ho, names, tel in items:
            sync.apply({'dong': dong, 'ho': ho}, {'owner': names, 'owner_phone': tel},
                       policy=policy, allow_insert=tgt.get('allow_insert', False),
                       source=f'{rno}행')

        s = sync.summary()
        print('결과:', dict(s))
        for w in warnings:
            print('[경고]', w)
        errors = [c for c in sync.changes if c.action == 'error']
        for c in errors[:20]:
            print('[오류]', c.source, c.key, c.message)

        sync.write_report(report)
        print(f'리포트: {report}')

        if args.commit:
            db.commit()
            print('커밋 완료')
        else:
            print('DRY-RUN: 롤백함 (반영하려면 --commit)')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
