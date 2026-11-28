import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator


DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/submissions.db")

app = FastAPI(title="お問い合わせ受付 API")


class ContactSubmission(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("name", "message")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("空白以外の文字を入力してください")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("有効なメールアドレスを入力してください")
        return value


def connect_database() -> sqlite3.Connection:
    return sqlite3.connect(DATABASE_PATH)


@app.on_event("startup")
def initialize_database() -> None:
    with closing(connect_database()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/submissions", status_code=201)
def create_submission(submission: ContactSubmission) -> dict[str, object]:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(connect_database()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO submissions (name, email, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                submission.name,
                submission.email,
                submission.message,
                created_at,
            ),
        )
        connection.commit()
        submission_id = cursor.lastrowid
    return {"id": submission_id, "created_at": created_at}


@app.get("/submissions")
def list_submissions() -> list[dict[str, object]]:
    with closing(connect_database()) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, name, email, message, created_at
            FROM submissions
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
