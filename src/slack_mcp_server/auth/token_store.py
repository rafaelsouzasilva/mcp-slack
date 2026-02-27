from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS installations (
    user_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    user_token TEXT NOT NULL,
    user_token_expires_at REAL,
    user_refresh_token TEXT,
    user_scopes TEXT,
    team_name TEXT,
    user_name TEXT,
    installed_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, team_id)
);

CREATE TABLE IF NOT EXISTS default_workspace (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id TEXT NOT NULL,
    team_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
);
"""


@dataclass
class Installation:
    user_id: str
    team_id: str
    user_token: str
    user_token_expires_at: float | None = None
    user_refresh_token: str | None = None
    user_scopes: str | None = None
    team_name: str | None = None
    user_name: str | None = None
    installed_at: float = 0.0
    updated_at: float = 0.0


class TokenStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "TokenStore not initialized"
        return self._db

    # --- Installations ---

    async def save_installation(self, inst: Installation) -> None:
        now = time.time()
        await self.db.execute(
            """
            INSERT INTO installations
                (user_id, team_id, user_token, user_token_expires_at,
                 user_refresh_token, user_scopes, team_name, user_name,
                 installed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, team_id) DO UPDATE SET
                user_token = excluded.user_token,
                user_token_expires_at = excluded.user_token_expires_at,
                user_refresh_token = excluded.user_refresh_token,
                user_scopes = excluded.user_scopes,
                team_name = excluded.team_name,
                user_name = excluded.user_name,
                updated_at = excluded.updated_at
            """,
            (
                inst.user_id,
                inst.team_id,
                inst.user_token,
                inst.user_token_expires_at,
                inst.user_refresh_token,
                inst.user_scopes,
                inst.team_name,
                inst.user_name,
                inst.installed_at or now,
                now,
            ),
        )
        await self.db.commit()

    async def get_installation(
        self, user_id: str, team_id: str
    ) -> Installation | None:
        cursor = await self.db.execute(
            "SELECT * FROM installations WHERE user_id = ? AND team_id = ?",
            (user_id, team_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Installation(**dict(row))

    async def list_installations(self) -> list[Installation]:
        cursor = await self.db.execute(
            "SELECT * FROM installations ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [Installation(**dict(row)) for row in rows]

    async def remove_installation(self, user_id: str, team_id: str) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM installations WHERE user_id = ? AND team_id = ?",
            (user_id, team_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    # --- Default Workspace ---

    async def set_default_workspace(self, user_id: str, team_id: str) -> None:
        await self.db.execute(
            """
            INSERT INTO default_workspace (id, user_id, team_id) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET user_id = excluded.user_id, team_id = excluded.team_id
            """,
            (user_id, team_id),
        )
        await self.db.commit()

    async def get_default_workspace(self) -> tuple[str, str] | None:
        cursor = await self.db.execute(
            "SELECT user_id, team_id FROM default_workspace WHERE id = 1"
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return (row["user_id"], row["team_id"])

    # --- OAuth States ---

    async def save_oauth_state(self, state: str, ttl: float = 600) -> None:
        await self.db.execute(
            "INSERT INTO oauth_states (state, expires_at) VALUES (?, ?)",
            (state, time.time() + ttl),
        )
        await self.db.commit()

    async def validate_oauth_state(self, state: str) -> bool:
        cursor = await self.db.execute(
            "SELECT expires_at FROM oauth_states WHERE state = ?", (state,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        await self.db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        await self.db.commit()
        return row["expires_at"] > time.time()

    async def cleanup_expired_states(self) -> None:
        await self.db.execute(
            "DELETE FROM oauth_states WHERE expires_at < ?", (time.time(),)
        )
        await self.db.commit()
