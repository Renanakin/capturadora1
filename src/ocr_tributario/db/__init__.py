"""Persistencia SQLite de jobs y resultados."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

DB_PATH = Path("db/jobs.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    output_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT,
    metadata TEXT
);
CREATE TABLE IF NOT EXISTS job_records (
    job_id TEXT NOT NULL,
    archivo TEXT NOT NULL,
    estado TEXT,
    rut TEXT,
    fecha TEXT,
    total INTEGER,
    proveedor TEXT,
    folio INTEGER,
    doc_type TEXT,
    ocr_engine TEXT,
    ocr_avg_score REAL,
    missing_fields TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_records_job ON job_records(job_id);
"""


@dataclass
class Job:
    id: str
    status: str
    total_files: int
    processed: int
    failed: int
    output_path: str | None
    created_at: str
    updated_at: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


async def init_db() -> None:
    """Crea las tablas si no existen."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def create_job(job_id: str, total_files: int, metadata: dict[str, Any] | None = None) -> Job:
    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO jobs (id, status, total_files, processed, failed, output_path,
                                 created_at, updated_at, error, metadata)
               VALUES (?, ?, ?, 0, 0, NULL, ?, ?, NULL, ?)""",
            (job_id, "queued", total_files, now, now, json.dumps(metadata or {})),
        )
        await db.commit()
    return Job(
        id=job_id, status="queued", total_files=total_files,
        processed=0, failed=0, output_path=None,
        created_at=now, updated_at=now, metadata=metadata or {},
    )


async def update_job(
    job_id: str,
    *,
    status: str | None = None,
    processed: int | None = None,
    failed: int | None = None,
    output_path: str | None = None,
    error: str | None = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    fields = []
    values: list[Any] = []
    if status is not None:
        fields.append("status=?")
        values.append(status)
    if processed is not None:
        fields.append("processed=?")
        values.append(processed)
    if failed is not None:
        fields.append("failed=?")
        values.append(failed)
    if output_path is not None:
        fields.append("output_path=?")
        values.append(output_path)
    if error is not None:
        fields.append("error=?")
        values.append(error)
    fields.append("updated_at=?")
    values.append(now)
    values.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id=?"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, values)
        await db.commit()


async def get_job(job_id: str) -> Job | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = await cur.fetchone()
        await cur.close()
    if row is None:
        return None
    return Job(
        id=row["id"],
        status=row["status"],
        total_files=row["total_files"],
        processed=row["processed"],
        failed=row["failed"],
        output_path=row["output_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=row["error"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


async def list_jobs(limit: int = 50) -> list[Job]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = await cur.fetchall()
        await cur.close()
    return [
        Job(
            id=r["id"], status=r["status"], total_files=r["total_files"],
            processed=r["processed"], failed=r["failed"], output_path=r["output_path"],
            created_at=r["created_at"], updated_at=r["updated_at"],
            error=r["error"], metadata=json.loads(r["metadata"] or "{}"),
        )
        for r in rows
    ]


async def add_job_record(
    job_id: str,
    archivo: str,
    *,
    estado: str | None,
    rut: str | None,
    fecha: str | None,
    total: int | None,
    proveedor: str | None,
    folio: int | None,
    doc_type: str | None,
    ocr_engine: str | None,
    ocr_avg_score: float | None,
    missing_fields: list[str] | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO job_records
               (job_id, archivo, estado, rut, fecha, total, proveedor, folio,
                doc_type, ocr_engine, ocr_avg_score, missing_fields)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, archivo, estado, rut, fecha, total, proveedor, folio,
                doc_type, ocr_engine, ocr_avg_score,
                json.dumps(missing_fields or []),
            ),
        )
        await db.commit()


async def list_job_records(job_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT archivo, estado, rut, fecha, total, proveedor, folio,
                      doc_type, ocr_engine, ocr_avg_score, missing_fields
               FROM job_records WHERE job_id=? ORDER BY archivo""",
            (job_id,),
        )
        rows = await cur.fetchall()
        await cur.close()
    out = []
    for r in rows:
        d = dict(r)
        d["missing_fields"] = json.loads(d["missing_fields"] or "[]")
        out.append(d)
    return out