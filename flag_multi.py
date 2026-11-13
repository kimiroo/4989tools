"""다중물건(S44) 재계산: MAIN 전체에서 같은 소유주 전화번호가 2개 이상 물건에 나오면 True, 아니면 False.

- 번호 정제 (붙은 번호 분리, 9자리 미만 제외) → lib4989/dup.py
- 기본 DRY-RUN + 리포트, --commit 시 dll 백업 후 반영
- 바뀌는 행만 UPDATE

    python flag_multi.py                 # dry-run, 리포트만
    python flag_multi.py --commit        # 백업 후 반영
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from lib4989 import Mdb, load_config
from lib4989.dup import find_multi
from lib4989.text import norm_key

HERE = Path(__file__).resolve().parent


def fmt_phone(d: str) -> str:
    from lib4989.text import format_phone
    return format_phone(d)


def write_report(path, rows_by_code, res, changes):
    import openpyxl
    from openpyxl.styles import Alignment, Font

    def unit(code):
        r = rows_by_code[code]
        return f'{r["complex"]} {norm_key(r["dong"]) or ""}-{norm_key(r["ho"]) or ""}'

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '변경'
    ws.append(['code', '단지', '동', '호', '임대인', '기존 S44', '새 S44', '겹치는 번호', '같은 번호의 다른 물건'])
    for code, old, new in changes:
        r = rows_by_code[code]
        shared = res.shared_phones(code)
        others = sorted({c for p in shared for c in res.groups[p] if c != code})
        ws.append([code, r['complex'], norm_key(r['dong']), norm_key(r['ho']), r['owner'],
                   bool(old), new, '\n'.join(fmt_phone(p) for p in shared),
                   '\n'.join(unit(c) for c in others)])

    ws2 = wb.create_sheet('번호별 그룹')
    ws2.append(['번호', '물건 수', '물건 (단지 동-호 / 임대인)'])
    for p, codes in sorted(res.groups.items(), key=lambda kv: -len(kv[1])):
        ws2.append([fmt_phone(p), len(codes),
                    '\n'.join(f'{unit(c)} / {(rows_by_code[c]["owner"] or "").splitlines()[0] if rows_by_code[c]["owner"] else ""}'
                              for c in codes)])

    for sh, widths in ((ws, (8, 16, 8, 8, 16, 9, 9, 16, 40)), (ws2, (16, 8, 60))):
        for cell in sh[1]:
            cell.font = Font(bold=True)
        for row in sh.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        for i, w in enumerate(widths):
            sh.column_dimensions[chr(65 + i)].width = w
        sh.freeze_panes = 'A2'
    wb.save(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default=HERE / 'config.toml')
    ap.add_argument('--db', help='mdb(dll) 경로 (config 덮어씀)')
    ap.add_argument('--fields', default='owner_phone',
                    help='비교할 논리 컬럼, 쉼표 구분 (기본: owner_phone)')
    ap.add_argument('--min-digits', type=int, default=9)
    ap.add_argument('--report', help='리포트 경로 (기본: report_multi_<시각>.xlsx)')
    ap.add_argument('--commit', action='store_true')
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    fields = [f.strip() for f in args.fields.split(',') if f.strip()]
    report = Path(args.report) if args.report else HERE / 'reports' / f'report_multi_{datetime.now():%Y%m%d-%H%M%S}.xlsx'
    report.parent.mkdir(parents=True, exist_ok=True)

    with Mdb(cfg, args.db) as db:
        if args.commit and cfg.db.backup_before_commit:
            print(f'백업: {db.backup()}')
        rows = db.fetch(None, ['complex', 'dong', 'ho', 'owner', 'multi', *fields])
        rows_by_code = {r['code']: r for r in rows}
        res = find_multi(rows, fields, args.min_digits)

        changes = [(code, rows_by_code[code]['multi'], new)
                   for code, new in res.flags.items()
                   if bool(rows_by_code[code]['multi']) != new]
        on = sum(1 for _, _, n in changes if n)
        print(f'mdb: {db.path} / 전체 {len(rows)}행')
        print(f'겹치는 번호 {len(res.groups)}개 → 다중물건 {sum(res.flags.values())}행 '
              f'(현재 True {sum(1 for r in rows if r["multi"])}행)')
        print(f'변경: False→True {on}행, True→False {len(changes) - on}행')

        for code, _, new in changes:
            db.update(code, {'multi': new})

        write_report(report, rows_by_code, res, changes)
        print(f'리포트: {report}')
        if args.commit:
            db.commit()
            print('커밋 완료')
        else:
            print('DRY-RUN: 롤백함 (반영하려면 --commit)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
