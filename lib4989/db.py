"""Access mdb(APT4989.dll) 접근 계층.

모든 공개 메서드는 '논리 컬럼 이름'(config [columns])으로 값을 주고받는다.
트랜잭션은 기본적으로 열려 있고, commit() 을 명시적으로 불러야 반영된다.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyodbc

from .config import Config


class FieldTooLong(ValueError):
    def __init__(self, logical: str, physical: str, size: int, length: int):
        self.logical, self.physical, self.size, self.length = logical, physical, size, length
        super().__init__(f'{logical}({physical}) 최대 {size}자인데 {length}자')


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type_name: str
    size: int


class Mdb:
    def __init__(self, cfg: Config, path: str | Path | None = None):
        self.cfg = cfg
        self.path = Path(path) if path else cfg.db.path
        self.table = cfg.db.table
        self.conn: pyodbc.Connection | None = None
        self.columns: dict[str, ColumnInfo] = {}

    # ---- connection -------------------------------------------------------
    def connect(self) -> 'Mdb':
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        conn_str = f'DRIVER={self.cfg.db.driver};DBQ={self.path};PWD={self.cfg.db.password};'
        self.conn = pyodbc.connect(conn_str, autocommit=False)
        cur = self.conn.cursor()
        self.columns = {
            c.column_name: ColumnInfo(c.column_name, c.type_name, c.column_size)
            for c in cur.columns(table=self.table)
        }
        if not self.columns:
            raise RuntimeError(f'테이블 {self.table} 을(를) 찾을 수 없습니다')
        self.validate()
        return self

    def validate(self) -> None:
        missing = {lg: ph for lg, ph in self.cfg.columns.items() if ph not in self.columns}
        if missing:
            raise RuntimeError(f'config 컬럼이 {self.table} 에 없음: {missing}')

    def backup(self) -> Path:
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        dst = self.path.with_name(f'{self.path.name}.bak-{ts}')
        shutil.copy2(self.path, dst)
        return dst

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> 'Mdb':
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.conn is not None:
                self.rollback()          # commit() 안 한 변경은 버린다
        finally:
            self.close()

    # ---- helpers ----------------------------------------------------------
    def _phys(self, logical: str) -> str:
        return self.cfg.col(logical)

    def _where(self, where: dict) -> tuple[str, list]:
        if not where:
            return '', []
        parts, params = [], []
        for lg, v in where.items():
            if v is None:
                parts.append(f'[{self._phys(lg)}] IS NULL')
            else:
                parts.append(f'[{self._phys(lg)}] = ?')
                params.append(v)
        return ' WHERE ' + ' AND '.join(parts), params

    def check_lengths(self, values: dict) -> None:
        """VARCHAR 길이 초과 검사. 초과 시 FieldTooLong."""
        for lg, v in values.items():
            if not isinstance(v, str):
                continue
            ph = self._phys(lg)
            info = self.columns[ph]
            if info.type_name.upper() in ('VARCHAR', 'CHAR') and len(v) > info.size:
                raise FieldTooLong(lg, ph, info.size, len(v))

    # ---- CRUD -------------------------------------------------------------
    def fetch(self, where: dict | None = None, fields: list[str] | None = None) -> list[dict]:
        """논리 이름 dict 목록 반환. fields 미지정 시 config 의 모든 컬럼."""
        fields = list(fields or self.cfg.columns)
        if 'code' not in fields:
            fields.insert(0, 'code')
        cols = ', '.join(f'[{self._phys(f)}]' for f in fields)
        w, params = self._where(where or {})
        cur = self.conn.cursor()
        cur.execute(f'SELECT {cols} FROM [{self.table}]{w}', params)
        return [dict(zip(fields, row)) for row in cur.fetchall()]

    def insert(self, values: dict) -> None:
        values = {k: v for k, v in values.items() if v is not None and k != 'code'}
        self.check_lengths(values)
        cols = ', '.join(f'[{self._phys(k)}]' for k in values)
        qs = ', '.join('?' * len(values))
        self.conn.cursor().execute(
            f'INSERT INTO [{self.table}] ({cols}) VALUES ({qs})', list(values.values()))

    def update(self, code: int, values: dict) -> None:
        values = {k: v for k, v in values.items() if k != 'code'}
        if not values:
            return
        self.check_lengths(values)
        sets = ', '.join(f'[{self._phys(k)}] = ?' for k in values)
        self.conn.cursor().execute(
            f'UPDATE [{self.table}] SET {sets} WHERE [{self._phys("code")}] = ?',
            [*values.values(), code])

    def delete(self, where: dict) -> int:
        if not where:
            raise ValueError('조건 없는 DELETE 는 허용하지 않습니다')
        w, params = self._where(where)
        cur = self.conn.cursor()
        cur.execute(f'DELETE FROM [{self.table}]{w}', params)
        return cur.rowcount
