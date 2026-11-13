"""엑셀 시트를 '논리 이름 -> 열 문자' 매핑으로 읽기."""
from __future__ import annotations

from collections.abc import Iterator

import openpyxl
from openpyxl.utils import column_index_from_string


def read_rows(path, sheet: str, columns: dict[str, str], start_row: int = 2,
              stop_after_blank: int = 50) -> Iterator[tuple[int, dict]]:
    """(엑셀 행번호, {논리이름: 값}) 를 순서대로 반환.

    시트의 used range 가 실제보다 크게 잡혀 있는 경우가 많아,
    매핑된 열이 전부 빈 행이 stop_after_blank 번 연속되면 멈춘다.
    """
    idx = {name: column_index_from_string(letter) - 1 for name, letter in columns.items()}
    max_col = max(idx.values()) + 1

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        blank = 0
        for rno, row in enumerate(ws.iter_rows(min_row=start_row, max_col=max_col,
                                               values_only=True), start=start_row):
            rec = {name: (row[i] if i < len(row) else None) for name, i in idx.items()}
            if all(v is None or (isinstance(v, str) and not v.strip()) for v in rec.values()):
                blank += 1
                if blank >= stop_after_blank:
                    break
                continue
            blank = 0
            yield rno, rec
    finally:
        wb.close()
