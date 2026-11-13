"""4989 제작사의 단순 인코딩 (MACt, 인증.txt 등에 쓰임).

규칙:
    문자열의 글자마다  (ord(글자) + KEY) % 256  을 3자리 숫자로 적고, 뒤에 구분자 SEP 를 붙인다.
    즉 글자 1개 = '%03d%s' % (val, SEP)  = 6자.
    인증.txt 처럼 끝에 제작사 표식(SUFFIX, 예: '2883')이 붙는 경우가 있다.

암호화가 아니라 난독화 수준이다. (KEY=189, SEP='189')
"""
from __future__ import annotations

KEY = 189
SEP = '189'


def encode_str(s: str, suffix: str = '', key: int = KEY, sep: str = SEP) -> str:
    """일반 문자열 → 인코딩 문자열."""
    return ''.join(f'{(ord(ch) + key) % 256:03d}{sep}' for ch in s) + suffix


def decode_str(enc: str, key: int = KEY, sep: str = SEP) -> tuple[str, str]:
    """인코딩 문자열 → (원문, 꼬리표).

    6자 단위(숫자3 + 구분자)로 맞지 않는 뒷부분은 꼬리표(suffix)로 돌려준다.
    """
    out: list[str] = []
    i, n, step = 0, len(enc), 3 + len(sep)
    while i + step <= n and enc[i + 3:i + step] == sep and enc[i:i + 3].isdigit():
        out.append(chr((int(enc[i:i + 3]) - key) % 256))
        i += step
    return ''.join(out), enc[i:]


# ---- MAC 전용 --------------------------------------------------------------
def normalize_mac(mac: str) -> str:
    """'58-11-22-bf-0b-69' / '581122BF0B69' → '58:11:22:BF:0B:69'."""
    hexes = ''.join(c for c in mac if c in '0123456789abcdefABCDEF').upper()
    if len(hexes) != 12:
        raise ValueError(f'MAC 형식이 아님: {mac!r} (16진수 12자리 필요)')
    return ':'.join(hexes[i:i + 2] for i in range(0, 12, 2))


def encode_mac(mac: str) -> str:
    """MAC 주소 → MACt.ADD1 에 넣을 문자열."""
    return encode_str(normalize_mac(mac))


def decode_mac(enc: str) -> str:
    """MACt.ADD1 문자열 → MAC 주소."""
    body, _ = decode_str(enc)
    return body
