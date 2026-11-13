"""다중물건(같은 소유주 번호가 여러 물건에 등장) 검사.

전화번호 정제 규칙:
- 셀 안의 텍스트에서 '0으로 시작, 9~11자리' 번호를 순서대로 뽑는다.
  '010-5057-4443010-3955-1534' 처럼 붙어 있는 경우도 두 번호로 나뉜다.
- 하이픈/공백/점/괄호는 무시, 숫자만 같으면 같은 번호.
- 0으로 시작하는 번호가 없는 줄(해외번호 등)은 그 줄의 숫자 전체를 하나의 번호로 본다.
- 9자리 미만(지역번호 없는 '533-8381', 생년월일 등)은 비교에서 제외.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

# 0 + 1~2자리 국번 + 3~4자리 + 4자리. 구분자는 선택.
_PHONE = re.compile(r'0\d{1,2}[\s\-.)]*\d{3,4}[\s\-.]*\d{4}')


def extract_phones(text, min_digits: int = 9) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    out = []
    for line in text.splitlines():
        found = [re.sub(r'\D', '', m.group()) for m in _PHONE.finditer(line)]
        if not found:
            # 0으로 시작하지 않는 번호 (해외 '1-213-923-2920' 등): 줄의 숫자 전체를 하나로
            found = [re.sub(r'\D', '', line)]
        for d in found:
            if len(d) >= min_digits and d not in out:
                out.append(d)
    return out


@dataclass
class MultiResult:
    flags: dict[int, bool]                          # code -> 다중물건 여부
    groups: dict[str, list[int]]                    # 번호 -> 그 번호가 나온 code 목록 (2개 이상만)
    phones_of: dict[int, list[str]] = field(default_factory=dict)

    def shared_phones(self, code: int) -> list[str]:
        return [p for p in self.phones_of.get(code, []) if p in self.groups]


def find_multi(rows: list[dict], phone_fields=('owner_phone',), min_digits: int = 9) -> MultiResult:
    """rows: Mdb.fetch() 결과 (code + phone_fields 포함)."""
    index: dict[str, set[int]] = defaultdict(set)
    phones_of: dict[int, list[str]] = {}
    for r in rows:
        ps = []
        for f in phone_fields:
            for p in extract_phones(r.get(f), min_digits):
                if p not in ps:
                    ps.append(p)
        phones_of[r['code']] = ps
        for p in ps:
            index[p].add(r['code'])

    groups = {p: sorted(c) for p, c in index.items() if len(c) > 1}
    flags = {code: any(p in groups for p in ps) for code, ps in phones_of.items()}
    return MultiResult(flags, groups, phones_of)
