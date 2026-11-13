"""config.toml 로딩.

논리 컬럼 이름(owner, note ...) <-> mdb 물리 컬럼(S29, S36 ...) 매핑을 제공한다.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DbConfig:
    path: Path
    password: str
    driver: str = '{Microsoft Access Driver (*.mdb, *.accdb)}'
    table: str = 'MAIN'
    backup_before_commit: bool = True


@dataclass
class Config:
    db: DbConfig
    columns: dict[str, str]                      # logical -> physical
    source: Path | None = None
    _reverse: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._reverse = {}
        for logical, physical in self.columns.items():
            if physical in self._reverse:
                raise ValueError(
                    f'config: 컬럼 {physical} 가 {self._reverse[physical]!r} 와 '
                    f'{logical!r} 에 중복 매핑됨')
            self._reverse[physical] = logical

    def col(self, logical: str) -> str:
        try:
            return self.columns[logical]
        except KeyError:
            raise KeyError(
                f'config [columns] 에 {logical!r} 가 없습니다 '
                f'(가능: {", ".join(self.columns)})') from None

    def logical(self, physical: str) -> str | None:
        return self._reverse.get(physical)


def _resolve(base: Path, p: str | os.PathLike) -> Path:
    p = Path(p)
    if str(p).startswith('\\\\') or p.is_absolute():
        return p
    return (base / p).resolve()


def load_config(path: str | os.PathLike = 'config.toml') -> Config:
    path = Path(path).resolve()
    with open(path, 'rb') as f:
        raw = tomllib.load(f)

    # 같은 폴더의 <이름>.local.toml (git 제외) 이 있으면 섹션 단위로 덮어씀
    local = path.with_name(f'{path.stem}.local.toml')
    if local.exists():
        with open(local, 'rb') as f:
            for section, values in tomllib.load(f).items():
                raw.setdefault(section, {}).update(values)

    db_raw = dict(raw.get('db', {}))
    if 'path' not in db_raw:
        raise ValueError(f'{path}: [db] path 가 필요합니다')
    db_raw['path'] = _resolve(path.parent, db_raw['path'])
    db_raw['password'] = os.environ.get('APT4989_PASSWORD', db_raw.get('password', ''))

    columns = raw.get('columns')
    if not columns:
        raise ValueError(f'{path}: [columns] 가 비어 있습니다')

    return Config(db=DbConfig(**db_raw), columns=dict(columns), source=path)


def load_toml(path: str | os.PathLike) -> dict:
    """작업(job)별 설정 파일 로딩용 헬퍼."""
    with open(path, 'rb') as f:
        return tomllib.load(f)
