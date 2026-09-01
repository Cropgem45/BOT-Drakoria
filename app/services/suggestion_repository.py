from __future__ import annotations

from typing import Any


class SuggestionRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    async def ensure_schema(self) -> None:
        conn = await self.database.connect()
        try:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS suggestion_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER UNIQUE,
                    thread_id INTEGER,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS suggestion_votes (
                    suggestion_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    vote TEXT NOT NULL CHECK (vote IN ('yes', 'no')),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (suggestion_id, user_id),
                    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_suggestion_votes_suggestion ON suggestion_votes (suggestion_id, vote);
                """
            )
            await conn.commit()
        finally:
            await conn.close()

    async def create(self, guild_id: int, author_id: int, channel_id: int, title: str, body: str) -> int:
        conn = await self.database.connect()
        try:
            cursor = await conn.execute(
                "INSERT INTO suggestions (guild_id, author_id, channel_id, title, body) VALUES (?, ?, ?, ?, ?)",
                (guild_id, author_id, channel_id, title, body),
            )
            await conn.commit()
            return int(cursor.lastrowid)
        finally:
            await conn.close()

    async def update_message(self, suggestion_id: int, message_id: int, thread_id: int | None = None) -> None:
        conn = await self.database.connect()
        try:
            await conn.execute(
                "UPDATE suggestions SET message_id = ?, thread_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (message_id, thread_id, suggestion_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_by_message(self, message_id: int) -> dict[str, Any] | None:
        conn = await self.database.connect()
        try:
            row = await self.database.fetchone(conn, "SELECT * FROM suggestions WHERE message_id = ?", (message_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def counts(self, suggestion_id: int) -> dict[str, int]:
        conn = await self.database.connect()
        try:
            rows = await self.database.fetchall(conn, "SELECT vote, COUNT(*) AS total FROM suggestion_votes WHERE suggestion_id = ? GROUP BY vote", (suggestion_id,))
        finally:
            await conn.close()
        result = {"yes": 0, "no": 0}
        for row in rows:
            result[str(row["vote"])] = int(row["total"])
        return result

    async def set_vote(self, suggestion_id: int, user_id: int, vote: str) -> dict[str, int]:
        if vote not in {"yes", "no"}:
            raise ValueError("vote must be yes or no")
        conn = await self.database.connect()
        try:
            await conn.execute(
                """
                INSERT INTO suggestion_votes (suggestion_id, user_id, vote, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(suggestion_id, user_id) DO UPDATE SET vote = excluded.vote, updated_at = CURRENT_TIMESTAMP
                """,
                (suggestion_id, user_id, vote),
            )
            rows = await self.database.fetchall(conn, "SELECT vote, COUNT(*) AS total FROM suggestion_votes WHERE suggestion_id = ? GROUP BY vote", (suggestion_id,))
            await conn.commit()
        finally:
            await conn.close()
        result = {"yes": 0, "no": 0}
        for row in rows:
            result[str(row["vote"])] = int(row["total"])
        return result

    async def save_panel(self, guild_id: int, channel_id: int, message_id: int) -> None:
        conn = await self.database.connect()
        try:
            await conn.execute(
                "INSERT INTO suggestion_panel_state (guild_id, channel_id, message_id) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, message_id = excluded.message_id, updated_at = CURRENT_TIMESTAMP",
                (guild_id, channel_id, message_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_panel(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.database.connect()
        try:
            row = await self.database.fetchone(conn, "SELECT * FROM suggestion_panel_state WHERE guild_id = ?", (guild_id,))
        finally:
            await conn.close()
        return dict(row) if row else None
