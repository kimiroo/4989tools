"""문자열/숫자 정규화 헬퍼."""
from __future__ import annotations

import math
import re
from collections.abc import Iterable

SQM_TO_PYEONG = 0.3025

_DIGITS_ONLY = re.compile(r'^[\d\-\s.]+$')


def clean(v) -> str | None:
    """셀 값을 공백 제거한 문자열로. 빈 값이면 None."""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def norm_key(v) -> str | None:
    """동/호 같은 키 비교용 정규화: 101.0 -> '101', ' 101 ' -> '101'."""
    s = clean(v)
    if s is None:
        return None
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def split_lines(v) -> list[str]:
    s = clean(v)
    if s is None:
        return []
    return [x.strip() for x in s.replace('\r\n', '\n').replace('\r', '\n').split('\n') if x.strip()]


def unique(items: Iterable) -> list:
    seen, out = set(), []
    for x in items:
        if x is None or x == '' or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def format_phone(raw: str) -> str:
    """숫자/하이픈만 있는 번호는 한국식 하이픈 형식으로. 메모가 붙은 번호는 그대로."""
    s = raw.strip()
    if not _DIGITS_ONLY.match(s):
        return s
    d = re.sub(r'\D', '', s)
    if d.startswith('02'):
        if len(d) == 9:
            return f'{d[:2]}-{d[2:5]}-{d[5:]}'
        if len(d) == 10:
            return f'{d[:2]}-{d[2:6]}-{d[6:]}'
    if len(d) == 10:
        return f'{d[:3]}-{d[3:6]}-{d[6:]}'
    if len(d) == 11:
        return f'{d[:3]}-{d[3:7]}-{d[7:]}'
    return s


def phones(*cells) -> list[str]:
    """여러 셀(줄바꿈 포함)에서 전화번호 목록 추출 (순서 유지, 중복 제거)."""
    out = []
    for c in cells:
        out.extend(format_phone(x) for x in split_lines(c))
    return unique(out)


def to_float(v) -> float | None:
    s = clean(v)
    if s is None:
        return None
    try:
        return float(s.replace(',', ''))
    except ValueError:
        return None


def fmt_num(v: float | None, ndigits: int = 2) -> str | None:
    """14.660000001 -> '14.66', 30.0 -> '30'."""
    if v is None:
        return None
    s = f'{round(v, ndigits):.{ndigits}f}'.rstrip('0').rstrip('.')
    return s


def sqm_to_pyeong(sqm: float | None) -> float | None:
    return None if sqm is None else sqm * SQM_TO_PYEONG


def pyeong_bucket(pyeong: float | None, step: int = 10) -> str | None:
    """평형 칸 관례: 평을 step 단위로 내림 (34.2 -> '30')."""
    if pyeong is None:
        return None
    return str(int(math.floor(pyeong / step) * step))
