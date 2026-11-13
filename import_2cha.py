"""2차명단.xlsx (조합원명부(동의자)) → 4989 MAIN '한신 2차'.

- 아파트: mdb 에 이미 있는 동/호 템플릿 행을 찾아 이름/연락처/상담(현주소)을 기존 기록 '뒤에' 추가. 비고는 안 건드림
- 상가  : 층/호/면적을 넣어 새 행 INSERT (재실행 시 같은 층/호는 갱신)
         면적 원본 숫자·현주소는 상담칸. 여러 호가 한 칸에 있는 다물건은 호마다 행을 나누고,
         원래 호수 목록과 면적 합계는 상담칸, 비고엔 '다물건 2층 201·202' 표시만

기본은 DRY-RUN(변경 후 롤백). 실제 반영은 --commit.

    python import_2cha.py                       # dry-run, 리포트만 생성
    python import_2cha.py --db "\\\\10.13.57.71\\apt4989\\APT4989.dll" --commit
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from lib4989 import ComplexSync, Mdb, load_config, load_toml, read_rows
from lib4989.text import (clean, fmt_num, norm_key, phones, pyeong_bucket,
                          split_lines, sqm_to_pyeong, to_float, unique)

HERE = Path(__file__).resolve().parent


@dataclass
class Unit:
    """엑셀의 물건 1건 = 첫 행(동/호 있음) + 아래 공유자 행들."""
    head_row: int
    head: dict
    members: list[tuple[int, dict]] = field(default_factory=list)

    @property
    def rows(self) -> list[tuple[int, dict]]:
        return [(self.head_row, self.head), *self.members]

    @property
    def source(self) -> str:
        last = self.members[-1][0] if self.members else self.head_row
        return f'{self.head_row}행' if last == self.head_row else f'{self.head_row}~{last}행'

    def names(self) -> str | None:
        return '\n'.join(unique(clean(r['name']) for _, r in self.rows)) or None

    def phones(self) -> str | None:
        cells = [c for _, r in self.rows for c in (r['phone1'], r['phone2'])]
        return '\n'.join(phones(*cells)) or None

    def addresses(self) -> list[str]:
        return unique(' '.join(split_lines(r['address'])) or None for _, r in self.rows)


def group_units(rows) -> tuple[list[Unit], list[str]]:
    units: list[Unit] = []
    warnings: list[str] = []
    for rno, r in rows:
        if clean(r['dong']) is not None:
            units.append(Unit(rno, r))
        elif clean(r['name']) is None:
            continue                          # 합계 행 등
        elif units:
            units[-1].members.append((rno, r))
            if clean(r['no']) is None:
                warnings.append(f'{rno}행 ({clean(r["name"])}): 번호 없음 → 바로 위 물건({units[-1].source.split("~")[0]})의 공유자로 처리')
        else:
            warnings.append(f'{rno}행: 동/호 없는 첫 행, 무시')
    return units, warnings


def address_lines(u: Unit) -> list[str]:
    return [f'현주소: {a}' for a in u.addresses()]


# ---- 아파트 -------------------------------------------------------------------
def apply_apartment(sync: ComplexSync, u: Unit, job: dict) -> None:
    sec = job['apartment']
    values = {
        'owner': u.names(),
        'owner_phone': u.phones(),
        'consult': '\n'.join(address_lines(u)) or None,   # 상세는 상담칸, 비고는 안 건드림
    }
    sync.apply({'dong': u.head['dong'], 'ho': u.head['ho']}, values,
               policy=sec.get('policy', {}), allow_insert=sec.get('allow_insert', False),
               source=u.source)


# ---- 상가 ---------------------------------------------------------------------
AREA_LABELS = [
    ('old_pyeong', '기존평형', ''),
    ('land_own', '토지 소유', '㎡'),
    ('land_incl', '토지 편입', '㎡'),
    ('bld_excl', '건물 전용', '㎡'),
    ('bld_own', '건물 소유', '㎡'),
]


def _raw_num(v) -> str | None:
    f = to_float(v)
    return fmt_num(f) if f is not None else clean(v)


def apply_store(sync: ComplexSync, u: Unit, job: dict) -> None:
    sec = job['store']
    h = u.head
    floors = split_lines(h['dong'])
    hos = [norm_key(x) for x in split_lines(h['ho'])]
    if len(floors) == 1 and len(hos) > 1:
        floors = floors * len(hos)
    if len(floors) != len(hos):
        sync.log_error((clean(h['dong']), clean(h['ho'])), '층/호 줄 수 불일치', u.source)
        return

    split = len(hos) > 1

    # 상담(S28): 면적 원본 숫자, 원래 호수, 현주소 등 상세
    consult_lines = []
    area_txt = ' / '.join(f'{label} {_raw_num(h[k])}{unit}'
                          for k, label, unit in AREA_LABELS if clean(h[k]) is not None)
    if area_txt:
        consult_lines.append(f'면적: {area_txt}')
    floor_txt = ', '.join(unique(floors))
    if split:
        consult_lines.append(f'원래 호수: {floor_txt} {", ".join(hos)} (면적은 {len(hos)}개 호 합계)')
    consult_lines.extend(address_lines(u))

    # 비고(S36): 핵심만 — 다물건 표시 (면적 칸이 빈 이유)
    note = f'다물건 {floor_txt} {"·".join(hos)}' if split else None

    base = {
        'owner': u.names(),
        'owner_phone': u.phones(),
        'consult': '\n'.join(consult_lines) or None,
        'note': note,
    }
    if not split:
        excl = to_float(h['bld_excl'])
        py = sqm_to_pyeong(excl)
        base |= {
            'pyeong_class': pyeong_bucket(py, sec.get('pyeong_step', 10)),
            'area_sqm': fmt_num(excl),
            'area_pyeong': fmt_num(py, 1),
        }

    for floor, ho in zip(floors, hos):
        sync.apply({'dong': floor, 'ho': ho}, base, policy=sec.get('policy', {}),
                   allow_insert=sec.get('allow_insert', True), source=u.source)


# ---- main ---------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default=HERE / 'config.toml')
    ap.add_argument('--job', default=HERE / 'import_2cha.toml')
    ap.add_argument('--db', help='mdb(dll) 경로 (config.toml [db] path 덮어씀)')
    ap.add_argument('--excel', help='엑셀 경로 (job [source] excel 덮어씀)')
    ap.add_argument('--report', help='리포트 xlsx 경로 (기본: report_2cha_<시각>.xlsx)')
    ap.add_argument('--commit', action='store_true', help='실제로 반영 (없으면 dry-run)')
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    job = load_toml(args.job)
    src = job['source']
    excel = Path(args.excel) if args.excel else (Path(args.job).resolve().parent / src['excel'])
    report = Path(args.report) if args.report else HERE / 'reports' / f'report_2cha_{datetime.now():%Y%m%d-%H%M%S}.xlsx'
    report.parent.mkdir(parents=True, exist_ok=True)

    rows = list(read_rows(excel, src['sheet'], src['columns'], start_row=src.get('start_row', 2)))
    units, warnings = group_units(rows)
    apt_kind, store_kind = job['apartment']['kind_value'], job['store']['kind_value']
    for u in units:
        if clean(u.head['kind']) is None and clean(u.head.get('usage')) is not None:
            u.head['kind'] = u.head['usage']
            warnings.append(f'{u.source}: 단지 칸 비어 있음 → 용도 {u.head["usage"]!r} 로 판단')
    apts = [u for u in units if clean(u.head['kind']) == apt_kind]
    stores = [u for u in units if clean(u.head['kind']) == store_kind]
    others = [u for u in units if u not in apts and u not in stores]
    for u in others:
        warnings.append(f'{u.source}: 단지 구분 {u.head["kind"]!r} 알 수 없음, 무시')

    print(f'엑셀: {excel.name} / 물건 {len(units)}건 (아파트 {len(apts)}, 상가 {len(stores)}, 기타 {len(others)})')

    db = Mdb(cfg, args.db)
    with db:
        if args.commit and cfg.db.backup_before_commit:
            print(f'백업: {db.backup()}')
        sync = ComplexSync(db, job['target']['complex'], key_fields=('dong', 'ho'))
        print(f'mdb: {db.path} / {sync.complex_name!r} 기존 {sync.loaded}행')

        for u in apts:
            apply_apartment(sync, u, job)
        for u in stores:
            apply_store(sync, u, job)

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
