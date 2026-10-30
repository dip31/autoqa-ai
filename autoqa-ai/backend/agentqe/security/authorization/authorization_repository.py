"""
Repository for target‑authorization records.
All queries use the shared `execute_query` helper to keep DB access consistent.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import List, Optional

from database.db import execute_query
from agentqe.security.models import TargetAuthorization


_TABLE = "security_target_authorizations"


def _init_table():
    """Create the table if it does not exist (idempotent)."""
    execute_query(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            hostname TEXT NOT NULL,
            scheme TEXT NOT NULL DEFAULT 'https',
            port INTEGER,
            path_prefix TEXT NOT NULL DEFAULT '/',
            allow_subdomains INTEGER NOT NULL DEFAULT 0,
            verification_method TEXT NOT NULL DEFAULT 'hosted_file',
            verification_status TEXT NOT NULL DEFAULT 'pending',
            verification_token TEXT,
            verified_at TIMESTAMP,
            expires_at TIMESTAMP,
            revoked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)


# Ensure table exists on module import
_init_table()


def _row_to_auth(row: dict) -> TargetAuthorization:
    return TargetAuthorization(
        id=row["id"],
        user_id=row["user_id"],
        hostname=row["hostname"],
        scheme=row["scheme"],
        port=row["port"],
        path_prefix=row["path_prefix"],
        allow_subdomains=bool(row["allow_subdomains"]),
        verification_method=row["verification_method"],
        verification_status=row["verification_status"],
        verification_token=row["verification_token"],
        verified_at=_parse_dt(row["verified_at"]),
        expires_at=_parse_dt(row["expires_at"]),
        revoked_at=_parse_dt(row["revoked_at"]),
        created_at=_parse_dt(row["created_at"]),
    )


def _parse_dt(val):
    if not val:
        return None
    # SQLite returns TEXT like '2024-01-01 12:34:56'
    try:
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def create_authorization(
    user_id: int,
    hostname: str,
    scheme: str = "https",
    port: Optional[int] = None,
    path_prefix: str = "/",
    allow_subdomains: bool = False,
    verification_method: str = "hosted_file",
) -> TargetAuthorization:
    """Insert a new pending authorization and return the record."""
    auth_id = secrets.token_urlsafe(16)
    token = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    expires = datetime.utcnow() + timedelta(hours=24)

    execute_query(
        f"""INSERT INTO {_TABLE}
            (id, user_id, hostname, scheme, port, path_prefix,
             allow_subdomains, verification_method, verification_status,
             verification_token, expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            auth_id,
            user_id,
            hostname.lower(),
            scheme.lower(),
            port,
            path_prefix,
            1 if allow_subdomains else 0,
            verification_method,
            "pending",
            token,
            expires.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    return TargetAuthorization(
        id=auth_id,
        user_id=user_id,
        hostname=hostname.lower(),
        scheme=scheme.lower(),
        port=port,
        path_prefix=path_prefix,
        allow_subdomains=allow_subdomains,
        verification_method=verification_method,
        verification_status="pending",
        verification_token=token,
        expires_at=expires,
        created_at=datetime.utcnow(),
    )


def get_authorization(auth_id: str) -> Optional[TargetAuthorization]:
    rows = execute_query(f"SELECT * FROM {_TABLE} WHERE id=?", (auth_id,), fetch=True)
    return _row_to_auth(rows[0]) if rows else None


def get_user_authorizations(user_id: int) -> List[TargetAuthorization]:
    rows = execute_query(f"SELECT * FROM {_TABLE} WHERE user_id=? ORDER BY created_at DESC", (user_id,), fetch=True)
    return [_row_to_auth(r) for r in rows]


def get_verified_authorization(user_id: int, hostname: str) -> Optional[TargetAuthorization]:
    rows = execute_query(
        f"""SELECT * FROM {_TABLE}
            WHERE user_id=? AND hostname=? AND verification_status='verified'
              AND (expires_at IS NULL OR expires_at > datetime('now'))
              AND revoked_at IS NULL""",
        (user_id, hostname.lower()),
        fetch=True,
    )
    return _row_to_auth(rows[0]) if rows else None


def mark_verified(auth_id: str) -> bool:
    """Mark an authorization as verified. Returns True if a row was updated."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # Use a direct connection to execute UPDATE and check changes() in the same transaction
    import sqlite3
    from database.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {_TABLE} SET verification_status='verified', verified_at=? WHERE id=? AND verification_status='pending'",
            (now, auth_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def revoke_authorization(auth_id: str, user_id: int) -> bool:
    """Revoke an authorization. Returns True if a row was updated."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    import sqlite3
    from database.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {_TABLE} SET revoked_at=? WHERE id=? AND user_id=?",
            (now, auth_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_authorization(auth_id: str, user_id: int) -> bool:
    """Delete an authorization. Returns True if a row was deleted."""
    import sqlite3
    from database.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM {_TABLE} WHERE id=? AND user_id=?",
            (auth_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()