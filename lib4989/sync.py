"""단지 단위 upsert 엔진 + 변경 리포트.

사용 예:
    with Mdb(cfg, path) as db:
        sync = ComplexSync(db, '한신 2차', key_fields=('dong', 'ho'))
        sync.apply({'dong': 101, 'ho': 101},
                   {'owner': '홍길동', 'consult': '현주소: ...'},
                   policy={'owner': 'append', 'consult': 'append'},
                   allow_insert=False, source='엑셀 7행')
        sync.write_report('reports/report.xlsx')
        db.commit()
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .db import FieldTooLong, Mdb
from .merge import merge_value
from .text import clean, norm_key


@dataclass
class Change:
    action: str                     # insert / update / unchanged / error
    key: tuple
    code: int | None = None
    diffs: dict = field(default_factory=dict)    # logical -> (old, new)
    message: str = ''
    source: str = ''


def _same(a, b) -> bool:
    return clean(a) == clean(b) if not isinstance(a, bool) else a == b


class ComplexSync:
    def __init__(self, db: Mdb, complex_name: str, key_fields=('dong', 'ho')):
        self.db = db
        self.complex_name = complex_name
        self.key_fields = tuple(key_fields)
        self.changes: list[Change] = []
        self.index: dict[tuple, list[dict]] = {}
        for row in db.fetch({'complex': complex_name}):
            self.index.setdefault(self.key_of(row), []).append(row)
        self.loaded = sum(len(v) for v in self.index.values())

    def key_of(self, d: dict) -> tuple:
        return tuple(norm_key(d.get(k)) for k in self.key_fields)

    def apply(self, key: dict, values: dict, policy: dict | None = None,
              default_policy: str = 'overwrite', allow_insert: bool = True,
              source: str = '') -> Change:
        policy = policy or {}
        k = self.key_of(key)
        rows = self.index.get(k, [])

        try:
            if not rows:
                if not allow_insert:
                    return self._log(Change('error', k, message='mdb 에 해당 동/호 없음', source=source))
                new_row = {'complex': self.complex_name,
                           **{f: norm_key(key[f]) for f in self.key_fields},
                           **values}
                self.db.insert(new_row)
                self.index[k] = [{**new_row, 'code': None}]
                diffs = {f: (None, v) for f, v in new_row.items() if v is not None}
                return self._log(Change('insert', k, None, diffs, source=source))

            msg = ''
            if len(rows) > 1:
                msg = f'같은 동/호 {len(rows)}건 존재 → 첫 행(code={rows[0]["code"]})만 갱신'
            row = rows[0]

            updates, diffs = {}, {}
            for f, new in values.items():
                old = row.get(f)
                merged = merge_value(new, old, policy.get(f, default_policy))
                if not _same(merged, old):
                    updates[f] = merged
                    diffs[f] = (old, merged)

            if not updates:
                return self._log(Change('unchanged', k, row['code'], message=msg, source=source))

            if row['code'] is None:      # 이번 실행에서 insert 한 행 → 다시 찾아야 함
                raise RuntimeError('같은 키가 입력 데이터에 중복됨')
            self.db.update(row['code'], updates)
            row.update(updates)
            return self._log(Change('update', k, row['code'], diffs, msg, source))

        except FieldTooLong as e:
            return self._log(Change('error', k, rows[0]['code'] if rows else None,
                                    message=str(e), source=source))
        except Exception as e:   # noqa: BLE001 - 행 단위로 기록하고 계속 진행
            return self._log(Change('error', k, rows[0]['code'] if rows else None,
                                    message=f'{type(e).__name__}: {e}', source=source))

    def log_error(self, key: tuple, message: str, source: str = '') -> Change:
        """입력 데이터 자체의 문제 등, apply 전에 걸러낸 오류 기록."""
        return self._log(Change('error', key, message=message, source=source))

    def _log(self, c: Change) -> Change:
        self.changes.append(c)
        return c

    def untouched_keys(self) -> list[tuple]:
        touched = {c.key for c in self.changes}
        return sorted(k for k in self.index if k not in touched)

    # ---- report -----------------------------------------------------------
    def summary(self) -> Counter:
        return Counter(c.action for c in self.changes)

    def write_report(self, path) -> None:
        import openpyxl
        from openpyxl.styles import Alignment, Font

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = '변경내역'
        ws.append(['결과', *self.key_fields, 'code', '출처', '필드', '컬럼', '기존 값', '새 값', '메시지'])
        for c in self.changes:
            base = [c.action, *c.key, c.code, c.source]
            if c.diffs:
                for f, (old, new) in c.diffs.items():
                    ws.append([*base, f, self.db.cfg.columns.get(f), old, new, c.message])
            else:
                ws.append([*base, None, None, None, None, c.message])

        ws2 = wb.create_sheet('요약')
        ws2.append(['결과', '건수'])
        for a, n in self.summary().most_common():
            ws2.append([a, n])
        ws2.append([])
        ws2.append(['mdb 기존 행 중 이번에 안 건드린 키'])
        for k in self.untouched_keys():
            ws2.append(list(k))

        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        for col, w in zip('ABCDEFGHIJK', (10, 8, 10, 8, 18, 14, 8, 40, 40, 40, 30)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = 'A2'
        wb.save(path)
