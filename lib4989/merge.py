"""기존 mdb 값과 새 값을 합치는 정책.

정책(policy):
    overwrite  : 새 값으로 교체 (새 값이 None 이면 기존 유지)
    prepend    : 새 줄들을 기존 값 앞에 추가. 기존에 이미 있는 줄은 빼고 추가.
    append     : prepend 와 같고 뒤에 추가.
    fill_empty : 기존 값이 비어 있을 때만 새 값.
    keep       : 기존이 있으면 절대 건드리지 않음 (insert 때만 값 사용). fill_empty 와 동일.
"""
from __future__ import annotations

from .text import clean, split_lines

POLICIES = ('overwrite', 'prepend', 'append', 'fill_empty', 'keep')


def merge_value(new, old, policy: str = 'overwrite'):
    if policy not in POLICIES:
        raise ValueError(f'알 수 없는 정책 {policy!r} (가능: {POLICIES})')

    if new is None or (isinstance(new, str) and clean(new) is None):
        return old

    if policy == 'overwrite':
        return new

    if policy in ('fill_empty', 'keep'):
        return new if clean(old) is None else old

    # prepend / append: 줄 단위 병합
    if not isinstance(new, str):
        new = str(new)
    old_s = clean(old)
    if old_s is None:
        return new

    old_lines = set(split_lines(old_s))
    add = [x for x in split_lines(new) if x not in old_lines]
    if not add:
        return old
    block = '\n'.join(add)
    return f'{block}\n{old_s}' if policy == 'prepend' else f'{old_s}\n{block}'
