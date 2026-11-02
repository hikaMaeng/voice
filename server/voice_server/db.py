"""SQLite 저장소 — 참조 세트·생성 결과·전사·작업 기록.

한 표 = 한 종류. 본문은 `data` JSON 열에 통째로 넣는다(재현에 필요한 값이 엔진마다 달라 열로 못 박는다).
파일(음성)은 `<data>/<kind>/<id>/` 아래에 두고 표에는 상대 경로만 적는다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid

from .config import DATA

_SCHEMA = """
CREATE TABLE IF NOT EXISTS refs        (id TEXT PRIMARY KEY, name TEXT, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS generations (id TEXT PRIMARY KEY, name TEXT, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS transcripts (id TEXT PRIMARY KEY, name TEXT, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS uploads     (id TEXT PRIMARY KEY, name TEXT, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS jobs        (id TEXT PRIMARY KEY, name TEXT, created REAL, data TEXT);
"""
TABLES = ("refs", "generations", "transcripts", "uploads", "jobs")


class Store:
    def __init__(self, path):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def put(self, table: str, row: dict) -> dict:
        assert table in TABLES
        row.setdefault("id", new_id())
        row.setdefault("created", time.time())
        with self._lock, self._db:
            self._db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?,?,?)",
                             (row["id"], row.get("name", ""), row["created"], json.dumps(row, ensure_ascii=False)))
        return row

    def get(self, table: str, id_: str) -> dict | None:
        assert table in TABLES
        with self._lock:
            r = self._db.execute(f"SELECT data FROM {table} WHERE id=?", (id_,)).fetchone()
        return json.loads(r[0]) if r else None

    def list(self, table: str, limit: int = 500) -> list[dict]:
        assert table in TABLES
        with self._lock:
            rows = self._db.execute(f"SELECT data FROM {table} ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete(self, table: str, id_: str) -> None:
        assert table in TABLES
        with self._lock, self._db:
            self._db.execute(f"DELETE FROM {table} WHERE id=?", (id_,))


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


store = Store(DATA / "voice.db")
