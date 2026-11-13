r"""4989 PC 등록 도구 (MACt + 인증.txt).

제작사 원격 등록(재설치 시마다 비용)을 대신하기 위한, 본인 소유 프로그램용 유틸.

MAC 등록
    python pc_tools.py mac-show                      # MACt 목록 복호화해서 보기
    python pc_tools.py mac-this                       # 이 PC 어댑터 MAC 목록 + 인코딩
    python pc_tools.py mac-encode 58-11-22-BF-0B-69   # MAC → MACt 문자열
    python pc_tools.py mac-decode 2421892451...        # MACt 문자열 → MAC
    python pc_tools.py mac-add 58-11-22-BF-0B-69       # MACt 에 추가 (dry-run)
    python pc_tools.py mac-add 58-11-22-BF-0B-69 --commit

인증.txt
    python pc_tools.py auth-show                       # 현재 인증.txt 복호화
    python pc_tools.py auth-backup auth_key.txt        # 원문 key 를 평문으로 저장(재설치 대비)
    python pc_tools.py auth-make --key-file auth_key.txt --out 인증.txt
    python pc_tools.py auth-make --key t90fn3l... --suffix 2883 --out 인증.txt

--db / --share 로 경로 지정. 기본은 config.toml 의 [db] path 와 그 폴더.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from lib4989 import Mdb, load_config
from lib4989.vendor_codec import (decode_mac, decode_str, encode_mac,
                                  encode_str, normalize_mac)

HERE = Path(__file__).resolve().parent
AUTH_NAME = '인증.txt'
MACT_TABLE = 'MACt'
MACT_COL = 'ADD1'


# ---- MAC --------------------------------------------------------------------
def read_mact(db: Mdb) -> list[str]:
    cur = db.conn.cursor()
    cur.execute(f'SELECT [{MACT_COL}] FROM [{MACT_TABLE}]')
    return [r[0] for r in cur.fetchall()]


def cmd_mac_show(args, cfg):
    db = Mdb(cfg, args.db)
    with db:
        for v in read_mact(db):
            if not v:
                print('  (빈 행)')
            else:
                print(f'  {decode_mac(v):20}  {v}')


def this_pc_macs() -> list[tuple[str, str]]:
    """(설명, MAC) 목록. PowerShell Get-NetAdapter 사용."""
    ps = ('Get-NetAdapter | Sort-Object ifIndex | '
          'ForEach-Object { "$($_.MacAddress)`t$($_.Status)`t$($_.Name) :: $($_.InterfaceDescription)" }')
    out = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                         capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) >= 3 and re.match(r'^[0-9A-Fa-f-]{17}$', parts[0].strip()):
            res.append((f'[{parts[1].strip()}] {parts[2].strip()}', parts[0].strip()))
    return res


def cmd_mac_this(args, cfg):
    for desc, mac in this_pc_macs():
        print(f'  {normalize_mac(mac)}  {desc}')
        print(f'       → {encode_mac(mac)}')


def cmd_mac_encode(args, cfg):
    print(encode_mac(args.mac))


def cmd_mac_decode(args, cfg):
    print(decode_mac(args.enc))


def cmd_mac_add(args, cfg):
    target = normalize_mac(args.mac)
    enc = encode_mac(args.mac)
    db = Mdb(cfg, args.db)
    with db:
        existing = {decode_mac(v): v for v in read_mact(db) if v}
        if target in existing:
            print(f'이미 등록됨: {target}')
            return
        cur = db.conn.cursor()
        cur.execute(f'INSERT INTO [{MACT_TABLE}] ([{MACT_COL}]) VALUES (?)', enc)
        print(f'새 행 추가 예정: {target}')
        if args.commit:
            db.commit()
            print('커밋 완료')
        else:
            print('DRY-RUN: 롤백함 (반영하려면 --commit)')


# ---- 인증.txt ---------------------------------------------------------------
def auth_path(args, cfg) -> Path:
    if args.share:
        return Path(args.share) / AUTH_NAME
    # config db 폴더
    return cfg.db.path.parent / AUTH_NAME


def cmd_auth_show(args, cfg):
    p = Path(args.file) if args.file else auth_path(args, cfg)
    raw = p.read_text(encoding='mbcs').strip()
    body, suf = decode_str(raw)
    print(f'파일: {p}')
    print(f'원문 key: {body!r}')
    print(f'꼬리표  : {suf!r}')


def cmd_auth_backup(args, cfg):
    p = Path(args.file) if args.file else auth_path(args, cfg)
    raw = p.read_text(encoding='mbcs').strip()
    body, suf = decode_str(raw)
    out = Path(args.out)
    out.write_text(f'{body}\n{suf}\n', encoding='utf-8')
    print(f'{p} → {out} 저장 (1줄: key, 2줄: 꼬리표)')


def cmd_auth_make(args, cfg):
    if args.key_file:
        lines = Path(args.key_file).read_text(encoding='utf-8').splitlines()
        key = lines[0].strip()
        suffix = lines[1].strip() if len(lines) > 1 else args.suffix
    else:
        key = args.key
        suffix = args.suffix
    if not key:
        sys.exit('key 가 필요합니다 (--key 또는 --key-file)')
    enc = encode_str(key, suffix)
    out = Path(args.out)
    newline = '' if args.no_newline else '\r\n'   # 원본 인증.txt 는 '...2883\r\n'
    out.write_bytes((enc + newline).encode('mbcs'))
    print(f'인증.txt 생성: {out}')
    print(f'  key={key!r} suffix={suffix!r}')
    # 자기검증
    body, suf = decode_str(enc)
    assert body == key and suf == suffix, '검증 실패'
    print('  자기검증 OK')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default=HERE / 'config.toml')
    ap.add_argument('--db', help='mdb 경로 (config 덮어씀)')
    ap.add_argument('--share', help='인증.txt 가 있는 폴더')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('mac-show').set_defaults(fn=cmd_mac_show)
    sub.add_parser('mac-this').set_defaults(fn=cmd_mac_this)
    p = sub.add_parser('mac-encode'); p.add_argument('mac'); p.set_defaults(fn=cmd_mac_encode)
    p = sub.add_parser('mac-decode'); p.add_argument('enc'); p.set_defaults(fn=cmd_mac_decode)
    p = sub.add_parser('mac-add'); p.add_argument('mac'); p.add_argument('--commit', action='store_true'); p.set_defaults(fn=cmd_mac_add)

    p = sub.add_parser('auth-show'); p.add_argument('--file'); p.set_defaults(fn=cmd_auth_show)
    p = sub.add_parser('auth-backup'); p.add_argument('out'); p.add_argument('--file'); p.set_defaults(fn=cmd_auth_backup)
    p = sub.add_parser('auth-make')
    p.add_argument('--key'); p.add_argument('--key-file'); p.add_argument('--suffix', default='2883')
    p.add_argument('--no-newline', action='store_true', help='끝에 CRLF 안 붙임')
    p.add_argument('--out', default=AUTH_NAME); p.set_defaults(fn=cmd_auth_make)

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    args.fn(args, cfg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
