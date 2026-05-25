from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    REQUIRED_TABLES = (
        "guild_settings",
        "onboarding_applications",
        "whitelist_members",
        "points",
        "point_entries",
        "tickets",
        "announcements",
        "ticket_panel_state",
        "voice_point_sessions",
        "voice_point_segments",
        "voice_point_panel_state",
        "management_dashboard_state",
        "staff_operational_alerts",
        "registration_panel_state",
        "member_registration_panel_state",
        "registration_records",
        "member_registration_sessions",
        "beta_program_panel_state",
        "beta_influencer_codes",
        "beta_tester_applications",
    )

    def __init__(self, path: Path) -> None:
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.path.as_posix())
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    async def fetchone(self, conn: aiosqlite.Connection, query: str, params: tuple[Any, ...]) -> aiosqlite.Row | None:
        cursor = await conn.execute(query, params)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def fetchall(self, conn: aiosqlite.Connection, query: str, params: tuple[Any, ...]) -> list[aiosqlite.Row]:
        cursor = await conn.execute(query, params)
        try:
            return await cursor.fetchall()
        finally:
            await cursor.close()

    async def initialize(self) -> None:
        conn = await self.connect()
        try:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    onboarding_open INTEGER NOT NULL DEFAULT 1,
                    panel_channel_id INTEGER,
                    panel_message_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS onboarding_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    reviewer_id INTEGER,
                    review_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TEXT,
                    UNIQUE (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS whitelist_members (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    granted_by INTEGER,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS points (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS point_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    delta INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    claimed_by INTEGER,
                    closed_by INTEGER,
                    close_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    closed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS ticket_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS voice_point_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    start_mode TEXT NOT NULL,
                    close_mode TEXT,
                    started_by_user_id INTEGER,
                    ended_by_user_id INTEGER,
                    initial_channel_id INTEGER NOT NULL,
                    initial_channel_group TEXT NOT NULL,
                    active_channel_id INTEGER,
                    active_channel_group TEXT,
                    last_valid_channel_id INTEGER,
                    last_valid_channel_group TEXT,
                    current_segment_started_at TEXT,
                    grace_started_at TEXT,
                    grace_deadline_at TEXT,
                    total_seconds INTEGER NOT NULL DEFAULT 0,
                    attendance_seconds INTEGER NOT NULL DEFAULT 0,
                    meeting_seconds INTEGER NOT NULL DEFAULT 0,
                    leadership_seconds INTEGER NOT NULL DEFAULT 0,
                    development_seconds INTEGER NOT NULL DEFAULT 0,
                    grace_seconds INTEGER NOT NULL DEFAULT 0,
                    transition_count INTEGER NOT NULL DEFAULT 0,
                    close_reason TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS voice_point_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    channel_id INTEGER,
                    channel_group TEXT NOT NULL,
                    segment_kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES voice_point_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS voice_point_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS management_dashboard_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_operational_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    context_json TEXT,
                    resolved_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS registration_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS member_registration_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS registration_records (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    registered_at TEXT,
                    last_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    registered_role_id INTEGER,
                    removed_role_id INTEGER,
                    source_channel_id INTEGER,
                    source_message_id INTEGER,
                    source_interaction_id INTEGER,
                    notes TEXT,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS member_registration_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    rejection_reason TEXT,
                    age INTEGER,
                    game_nick TEXT,
                    how_found_drakoria TEXT,
                    prior_rp_experience TEXT,
                    weekly_availability TEXT,
                    interest_area TEXT,
                    what_called_attention TEXT,
                    rules_confirmation TEXT,
                    truth_confirmation TEXT,
                    final_notes TEXT,
                    applied_role_id INTEGER,
                    nickname_applied TEXT,
                    nickname_apply_status TEXT,
                    source_channel_id INTEGER,
                    source_message_id INTEGER,
                    panel_message_id INTEGER,
                    last_step TEXT NOT NULL DEFAULT 'started',
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS beta_program_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS beta_influencer_codes (
                    guild_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    influencer_name TEXT NOT NULL,
                    owner_user_id INTEGER,
                    slot_limit INTEGER NOT NULL DEFAULT 5,
                    slot_used INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_by_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, code)
                );

                CREATE TABLE IF NOT EXISTS beta_tester_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    submitted_at TEXT,
                    reviewed_at TEXT,
                    reviewed_by_id INTEGER,
                    review_result TEXT,
                    rejection_reason TEXT,
                    role_applied INTEGER NOT NULL DEFAULT 0,
                    card_generated INTEGER NOT NULL DEFAULT 0,
                    card_sent_dm INTEGER NOT NULL DEFAULT 0,
                    card_sent_channel INTEGER NOT NULL DEFAULT 0,
                    application_channel_id INTEGER,
                    application_message_id INTEGER,
                    panel_channel_id INTEGER,
                    panel_message_id INTEGER,
                    referral_type TEXT NOT NULL DEFAULT 'direct',
                    influencer_code TEXT,
                    influencer_name TEXT,
                    influencer_owner_id INTEGER,
                    last_step TEXT NOT NULL DEFAULT 'started',
                    last_error TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_onboarding_guild_status
                ON onboarding_applications (guild_id, status);

                CREATE INDEX IF NOT EXISTS idx_whitelist_guild_status
                ON whitelist_members (guild_id, status);

                CREATE INDEX IF NOT EXISTS idx_point_entries_guild_user_created
                ON point_entries (guild_id, user_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_tickets_guild_user_status
                ON tickets (guild_id, user_id, status);

                CREATE INDEX IF NOT EXISTS idx_tickets_guild_status
                ON tickets (guild_id, status);

                CREATE INDEX IF NOT EXISTS idx_announcements_guild_created
                ON announcements (guild_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_user_status
                ON voice_point_sessions (guild_id, user_id, status);

                CREATE INDEX IF NOT EXISTS idx_voice_sessions_status_started
                ON voice_point_sessions (guild_id, status, started_at DESC);

                CREATE INDEX IF NOT EXISTS idx_voice_segments_session_started
                ON voice_point_segments (session_id, started_at);

                CREATE INDEX IF NOT EXISTS idx_staff_operational_alerts_guild_created
                ON staff_operational_alerts (guild_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_staff_operational_alerts_guild_type
                ON staff_operational_alerts (guild_id, alert_type, created_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_sessions_one_active
                ON voice_point_sessions (guild_id, user_id)
                WHERE status = 'active';

                CREATE INDEX IF NOT EXISTS idx_registration_records_guild_status
                ON registration_records (guild_id, status);

                CREATE INDEX IF NOT EXISTS idx_member_registration_sessions_guild_user
                ON member_registration_sessions (guild_id, user_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_member_registration_sessions_guild_status
                ON member_registration_sessions (guild_id, status, updated_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_member_registration_sessions_one_active
                ON member_registration_sessions (guild_id, user_id)
                WHERE status = 'in_progress';

                CREATE INDEX IF NOT EXISTS idx_beta_tester_applications_guild_status
                ON beta_tester_applications (guild_id, status, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_beta_tester_applications_guild_user
                ON beta_tester_applications (guild_id, user_id, id DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_beta_tester_applications_one_active
                ON beta_tester_applications (guild_id, user_id)
                WHERE status IN ('in_progress', 'pending');
                """
            )
            await self._migrate_ticket_schema(conn)
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tickets_guild_status_assignee
                ON tickets (guild_id, status, assigned_staff_id)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tickets_guild_resolved_staff_closed
                ON tickets (guild_id, resolved_staff_id, closed_at DESC)
                """
            )
            await self._migrate_staff_timeclock_schema(conn)
            await self._migrate_beta_program_schema(conn)
            await conn.commit()
        finally:
            await conn.close()

    async def _migrate_beta_program_schema(self, conn: aiosqlite.Connection) -> None:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS beta_influencer_codes (
                guild_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                influencer_name TEXT NOT NULL,
                owner_user_id INTEGER,
                slot_limit INTEGER NOT NULL DEFAULT 5,
                slot_used INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_by_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, code)
            );
            """
        )
        columns = await self.fetchall(conn, "PRAGMA table_info(beta_tester_applications)", ())
        existing = {str(row["name"]) for row in columns}
        migrations = {
            "referral_type": "ALTER TABLE beta_tester_applications ADD COLUMN referral_type TEXT NOT NULL DEFAULT 'direct'",
            "influencer_code": "ALTER TABLE beta_tester_applications ADD COLUMN influencer_code TEXT",
            "influencer_name": "ALTER TABLE beta_tester_applications ADD COLUMN influencer_name TEXT",
            "influencer_owner_id": "ALTER TABLE beta_tester_applications ADD COLUMN influencer_owner_id INTEGER",
        }
        for column, statement in migrations.items():
            if column not in existing:
                await conn.execute(statement)
        influencer_columns = await self.fetchall(conn, "PRAGMA table_info(beta_influencer_codes)", ())
        influencer_existing = {str(row["name"]) for row in influencer_columns}
        if "slot_limit" not in influencer_existing:
            await conn.execute("ALTER TABLE beta_influencer_codes ADD COLUMN slot_limit INTEGER NOT NULL DEFAULT 5")
        if "slot_used" not in influencer_existing:
            await conn.execute("ALTER TABLE beta_influencer_codes ADD COLUMN slot_used INTEGER NOT NULL DEFAULT 0")
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beta_tester_applications_guild_influencer
            ON beta_tester_applications (guild_id, influencer_code, status)
            """
        )

    async def _migrate_staff_timeclock_schema(self, conn: aiosqlite.Connection) -> None:
        tables = await self.fetchall(
            conn, "SELECT name FROM sqlite_master WHERE type='table'", ()
        )
        existing = {str(row["name"]) for row in tables}
        if "staff_roles_config" not in existing:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS staff_roles_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, role_id)
                );

                CREATE TABLE IF NOT EXISTS staff_voice_channel_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    rule_type TEXT NOT NULL DEFAULT 'work',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, channel_id)
                );

                CREATE TABLE IF NOT EXISTS staff_work_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    close_reason TEXT,
                    close_mode TEXT,
                    ended_by_user_id INTEGER,
                    current_activity TEXT NOT NULL DEFAULT 'Não classificado',
                    current_environment TEXT,
                    current_channel_id INTEGER,
                    segment_started_at TEXT,
                    pause_started_at TEXT,
                    active_pause_id INTEGER,
                    total_valid_seconds INTEGER NOT NULL DEFAULT 0,
                    total_paused_seconds INTEGER NOT NULL DEFAULT 0,
                    total_pending_seconds INTEGER NOT NULL DEFAULT 0,
                    last_checkin_at TEXT,
                    checkin_pending INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_work_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES staff_work_sessions(id),
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    activity TEXT NOT NULL DEFAULT 'Não classificado',
                    environment TEXT,
                    channel_id INTEGER,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER,
                    segment_status TEXT NOT NULL DEFAULT 'valid',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_work_pauses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES staff_work_sessions(id),
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER,
                    reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_work_checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES staff_work_sessions(id),
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    deadline_at TEXT NOT NULL,
                    answered_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    response TEXT,
                    message_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_work_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    session_id INTEGER,
                    admin_id INTEGER NOT NULL,
                    adjustment_seconds INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_work_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    session_id INTEGER,
                    event_type TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS staff_timeclock_panel_state (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_staff_work_sessions_guild_user
                ON staff_work_sessions (guild_id, user_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_staff_work_sessions_status
                ON staff_work_sessions (guild_id, status, started_at DESC);

                CREATE INDEX IF NOT EXISTS idx_staff_work_segments_session
                ON staff_work_segments (session_id, started_at);

                CREATE INDEX IF NOT EXISTS idx_staff_work_segments_guild_user
                ON staff_work_segments (guild_id, user_id, started_at DESC);

                CREATE INDEX IF NOT EXISTS idx_staff_work_events_guild
                ON staff_work_events (guild_id, created_at DESC);
                """
            )
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS staff_timeclock_config (
                guild_id INTEGER PRIMARY KEY,
                control_channel_id INTEGER,
                logs_channel_id INTEGER,
                auto_prompt_on_voice_join INTEGER NOT NULL DEFAULT 1,
                reminder_after_seconds INTEGER NOT NULL DEFAULT 180,
                admin_alert_after_seconds INTEGER NOT NULL DEFAULT 600,
                auto_pause_on_voice_leave INTEGER NOT NULL DEFAULT 1,
                auto_pause_delay_seconds INTEGER NOT NULL DEFAULT 120,
                auto_pause_on_afk INTEGER NOT NULL DEFAULT 1,
                checkin_voice_seconds INTEGER NOT NULL DEFAULT 3600,
                checkin_external_seconds INTEGER NOT NULL DEFAULT 1800,
                checkin_timeout_seconds INTEGER NOT NULL DEFAULT 300,
                alert_cooldown_seconds INTEGER NOT NULL DEFAULT 600,
                admin_panel_auto_refresh_seconds INTEGER NOT NULL DEFAULT 120,
                use_dm_as_fallback INTEGER NOT NULL DEFAULT 0,
                test_mode INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS staff_call_presence_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER,
                alert_type TEXT NOT NULL,
                message_id INTEGER,
                started_at TEXT NOT NULL,
                last_reminder_at TEXT,
                ignored_until TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                metadata_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_presence_alert_unique_active
            ON staff_call_presence_alerts (guild_id, user_id, alert_type)
            WHERE status = 'active';

            CREATE INDEX IF NOT EXISTS idx_staff_presence_alerts_guild_status
            ON staff_call_presence_alerts (guild_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS staff_timeclock_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                channel_id INTEGER,
                message_id INTEGER,
                sent_at TEXT NOT NULL,
                answered_at TEXT,
                status TEXT NOT NULL DEFAULT 'sent',
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS staff_admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                target_user_id INTEGER,
                action_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS staff_timeclock_admin_panel_state (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = await self._table_columns(conn, "staff_voice_channel_rules")
        if "activity_suggested" not in columns:
            await conn.execute("ALTER TABLE staff_voice_channel_rules ADD COLUMN activity_suggested TEXT")

    async def _table_columns(self, conn: aiosqlite.Connection, table_name: str) -> set[str]:
        rows = await self.fetchall(conn, f"PRAGMA table_info({table_name})", ())
        return {str(row["name"]) for row in rows}

    async def _migrate_ticket_schema(self, conn: aiosqlite.Connection) -> None:
        columns = await self._table_columns(conn, "tickets")
        migrations = {
            "ticket_type": "ALTER TABLE tickets ADD COLUMN ticket_type TEXT NOT NULL DEFAULT 'general_support'",
            "assigned_staff_id": "ALTER TABLE tickets ADD COLUMN assigned_staff_id INTEGER",
            "transferred_from_staff_id": "ALTER TABLE tickets ADD COLUMN transferred_from_staff_id INTEGER",
            "status_detail": "ALTER TABLE tickets ADD COLUMN status_detail TEXT",
            "panel_message_id": "ALTER TABLE tickets ADD COLUMN panel_message_id INTEGER",
            "transcript_name": "ALTER TABLE tickets ADD COLUMN transcript_name TEXT",
            "transcript_channel_id": "ALTER TABLE tickets ADD COLUMN transcript_channel_id INTEGER",
            "transcript_message_id": "ALTER TABLE tickets ADD COLUMN transcript_message_id INTEGER",
            "dm_status": "ALTER TABLE tickets ADD COLUMN dm_status TEXT",
            "closed_by_id": "ALTER TABLE tickets ADD COLUMN closed_by_id INTEGER",
            "opened_at": "ALTER TABLE tickets ADD COLUMN opened_at TEXT",
            "updated_at": "ALTER TABLE tickets ADD COLUMN updated_at TEXT",
            "last_status_changed_by": "ALTER TABLE tickets ADD COLUMN last_status_changed_by INTEGER",
            "last_status_changed_at": "ALTER TABLE tickets ADD COLUMN last_status_changed_at TEXT",
            "close_reason": "ALTER TABLE tickets ADD COLUMN close_reason TEXT",
            "resolved_staff_id": "ALTER TABLE tickets ADD COLUMN resolved_staff_id INTEGER",
        }
        for column, statement in migrations.items():
            if column not in columns:
                await conn.execute(statement)

        if "claimed_by" in columns and "assigned_staff_id" in await self._table_columns(conn, "tickets"):
            await conn.execute(
                """
                UPDATE tickets
                SET assigned_staff_id = COALESCE(assigned_staff_id, claimed_by)
                WHERE claimed_by IS NOT NULL
                """
            )

        refreshed_columns = await self._table_columns(conn, "tickets")
        if "opened_at" in refreshed_columns:
            await conn.execute(
                """
                UPDATE tickets
                SET opened_at = COALESCE(opened_at, created_at, CURRENT_TIMESTAMP)
                WHERE opened_at IS NULL
                """
            )
        if "updated_at" in refreshed_columns:
            await conn.execute(
                """
                UPDATE tickets
                SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
                WHERE updated_at IS NULL
                """
            )
        if "last_status_changed_at" in refreshed_columns:
            await conn.execute(
                """
                UPDATE tickets
                SET last_status_changed_at = COALESCE(last_status_changed_at, opened_at, created_at, CURRENT_TIMESTAMP)
                WHERE last_status_changed_at IS NULL
                """
            )
        if "resolved_staff_id" in refreshed_columns:
            await conn.execute(
                """
                UPDATE tickets
                SET resolved_staff_id = COALESCE(resolved_staff_id, closed_by_id, closed_by, assigned_staff_id)
                WHERE status = 'closed'
                """
            )

    async def _run_write(self, query: str, params: tuple[Any, ...]) -> None:
        conn = await self.connect()
        try:
            await conn.execute(query, params)
            await conn.commit()
        finally:
            await conn.close()

    async def ensure_guild(self, guild_id: int, onboarding_open: bool) -> None:
        await self._run_write(
            """
            INSERT INTO guild_settings (guild_id, onboarding_open)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO NOTHING
            """,
            (guild_id, int(onboarding_open)),
        )

    async def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
        finally:
            await conn.close()
        return dict(row) if row else {}

    async def table_exists(self, table_name: str) -> bool:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            )
        finally:
            await conn.close()
        return row is not None

    async def count_rows(self, table_name: str) -> int:
        conn = await self.connect()
        try:
            cursor = await conn.execute(f"SELECT COUNT(*) AS total FROM {table_name}")
            try:
                row = await cursor.fetchone()
            finally:
                await cursor.close()
        finally:
            await conn.close()
        return int(row["total"]) if row else 0

    async def integrity_check(self) -> str:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "PRAGMA integrity_check", ())
        finally:
            await conn.close()
        return str(row[0]) if row else "unknown"

    async def set_onboarding_open(self, guild_id: int, value: bool) -> None:
        await self._run_write(
            """
            INSERT INTO guild_settings (guild_id, onboarding_open)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET onboarding_open = excluded.onboarding_open
            """,
            (guild_id, int(value)),
        )

    async def save_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO guild_settings (guild_id, panel_channel_id, panel_message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                panel_channel_id = excluded.panel_channel_id,
                panel_message_id = excluded.panel_message_id
            """,
            (guild_id, channel_id, message_id),
        )

    async def upsert_application(self, guild_id: int, user_id: int, answers: dict[str, str]) -> int:
        payload = json.dumps(answers, ensure_ascii=False)
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO onboarding_applications (guild_id, user_id, status, answers_json)
                VALUES (?, ?, 'pending', ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    status = 'pending',
                    answers_json = excluded.answers_json,
                    reviewer_id = NULL,
                    review_reason = NULL,
                    reviewed_at = NULL,
                    created_at = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, payload),
            )
            await conn.commit()
            row = await self.fetchone(
                conn,
                "SELECT id FROM onboarding_applications WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return int(row["id"])

    async def get_application(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM onboarding_applications WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def review_application(
        self,
        guild_id: int,
        user_id: int,
        status: str,
        reviewer_id: int,
        reason: str | None,
    ) -> None:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                UPDATE onboarding_applications
                SET status = ?, reviewer_id = ?, review_reason = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ?
                """,
                (status, reviewer_id, reason, guild_id, user_id),
            )
            await conn.execute(
                """
                INSERT INTO whitelist_members (guild_id, user_id, status, granted_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    status = excluded.status,
                    granted_by = excluded.granted_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, "approved" if status == "approved" else "rejected", reviewer_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def pending_application_user_ids(self, guild_id: int) -> list[int]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                "SELECT user_id FROM onboarding_applications WHERE guild_id = ? AND status = 'pending'",
                (guild_id,),
            )
        finally:
            await conn.close()
        return [int(row["user_id"]) for row in rows]

    async def get_whitelist_status(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM whitelist_members WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def adjust_points(self, guild_id: int, user_id: int, delta: int, reason: str, actor_id: int) -> int:
        current = await self.get_points(guild_id, user_id)
        total = current + delta
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO points (guild_id, user_id, total)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total = excluded.total,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, total),
            )
            await conn.execute(
                """
                INSERT INTO point_entries (guild_id, user_id, delta, reason, actor_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, delta, reason, actor_id),
            )
            await conn.commit()
        finally:
            await conn.close()
        return total

    async def get_points(self, guild_id: int, user_id: int) -> int:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT total FROM points WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return int(row["total"]) if row else 0

    async def top_points(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT user_id, total
                FROM points
                WHERE guild_id = ?
                ORDER BY total DESC, updated_at ASC
                LIMIT ?
                """,
                (guild_id, limit),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def create_ticket(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        ticket_type: str,
        status: str = "open",
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO tickets (
                    guild_id,
                    user_id,
                    channel_id,
                    ticket_type,
                    status,
                    opened_at,
                    updated_at,
                    last_status_changed_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (guild_id, user_id, channel_id, ticket_type, status),
            )
            await conn.commit()
            row = await self.fetchone(conn, "SELECT id FROM tickets WHERE channel_id = ?", (channel_id,))
        finally:
            await conn.close()
        return int(row["id"])

    async def get_open_ticket_by_user(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT * FROM tickets
                WHERE guild_id = ? AND user_id = ? AND status != 'closed'
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def list_open_tickets(self, guild_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT *
                FROM tickets
                WHERE guild_id = ? AND status != 'closed'
                ORDER BY opened_at ASC, id ASC
                """,
                (guild_id,),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def get_ticket_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_ticket_by_id(self, ticket_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def claim_ticket(self, channel_id: int, moderator_id: int) -> None:
        await self._run_write(
            """
            UPDATE tickets
            SET claimed_by = ?,
                assigned_staff_id = ?,
                status = 'in_progress',
                updated_at = CURRENT_TIMESTAMP,
                last_status_changed_by = ?,
                last_status_changed_at = CURRENT_TIMESTAMP
            WHERE channel_id = ?
            """,
            (moderator_id, moderator_id, moderator_id, channel_id),
        )

    async def transfer_ticket(self, channel_id: int, previous_staff_id: int | None, new_staff_id: int) -> None:
        await self._run_write(
            """
            UPDATE tickets
            SET claimed_by = ?,
                assigned_staff_id = ?,
                transferred_from_staff_id = ?,
                status = 'in_progress',
                updated_at = CURRENT_TIMESTAMP,
                last_status_changed_by = ?,
                last_status_changed_at = CURRENT_TIMESTAMP
            WHERE channel_id = ?
            """,
            (new_staff_id, new_staff_id, previous_staff_id, new_staff_id, channel_id),
        )

    async def set_ticket_status(
        self,
        channel_id: int,
        status: str,
        actor_id: int,
        detail: str | None = None,
    ) -> None:
        await self._run_write(
            """
            UPDATE tickets
            SET status = ?,
                status_detail = ?,
                updated_at = CURRENT_TIMESTAMP,
                last_status_changed_by = ?,
                last_status_changed_at = CURRENT_TIMESTAMP
            WHERE channel_id = ?
            """,
            (status, detail, actor_id, channel_id),
        )

    async def set_ticket_panel_message(self, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            UPDATE tickets
            SET panel_message_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE channel_id = ?
            """,
            (message_id, channel_id),
        )

    async def set_ticket_dm_status(self, channel_id: int, status: str) -> None:
        await self._run_write(
            """
            UPDATE tickets
            SET dm_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE channel_id = ?
            """,
            (status, channel_id),
        )

    async def close_ticket(
        self,
        channel_id: int,
        moderator_id: int,
        reason: str,
        *,
        transcript_name: str | None = None,
        transcript_channel_id: int | None = None,
        transcript_message_id: int | None = None,
    ) -> None:
        await self._run_write(
            """
            UPDATE tickets
            SET status = 'closed',
                closed_by = ?,
                closed_by_id = COALESCE(closed_by_id, ?),
                resolved_staff_id = COALESCE(resolved_staff_id, assigned_staff_id, closed_by_id, ?, ?),
                close_reason = ?,
                closed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                last_status_changed_by = ?,
                last_status_changed_at = CURRENT_TIMESTAMP,
                transcript_name = ?,
                transcript_channel_id = ?,
                transcript_message_id = ?
            WHERE channel_id = ?
            """,
            (
                moderator_id,
                moderator_id,
                moderator_id,
                moderator_id,
                reason,
                moderator_id,
                transcript_name,
                transcript_channel_id,
                transcript_message_id,
                channel_id,
            ),
        )

    async def mark_ticket_stale(self, channel_id: int, actor_id: int, reason: str) -> None:
        await self.close_ticket(channel_id, actor_id, reason)

    async def save_ticket_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO ticket_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_ticket_panel_message(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM ticket_panel_state WHERE guild_id = ?", (guild_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def create_announcement(
        self,
        guild_id: int,
        author_id: int,
        channel_id: int,
        title: str,
        body: str,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO announcements (guild_id, author_id, channel_id, title, body)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, author_id, channel_id, title, body),
        )

    async def create_voice_point_session(
        self,
        guild_id: int,
        user_id: int,
        started_at: str,
        channel_id: int,
        channel_group: str,
        start_mode: str,
        started_by_user_id: int | None,
        notes: str | None = None,
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO voice_point_sessions (
                    guild_id,
                    user_id,
                    status,
                    started_at,
                    start_mode,
                    started_by_user_id,
                    initial_channel_id,
                    initial_channel_group,
                    active_channel_id,
                    active_channel_group,
                    last_valid_channel_id,
                    last_valid_channel_group,
                    current_segment_started_at,
                    notes,
                    updated_at
                )
                VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    started_at,
                    start_mode,
                    started_by_user_id,
                    channel_id,
                    channel_group,
                    channel_id,
                    channel_group,
                    channel_id,
                    channel_group,
                    started_at,
                    notes,
                    started_at,
                ),
            )
            await conn.commit()
            row = await self.fetchone(
                conn,
                """
                SELECT id
                FROM voice_point_sessions
                WHERE guild_id = ? AND user_id = ? AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return int(row["id"])

    async def get_active_voice_point_session(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT *
                FROM voice_point_sessions
                WHERE guild_id = ? AND user_id = ? AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_voice_point_session(self, session_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM voice_point_sessions WHERE id = ?", (session_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def list_active_voice_point_sessions(self, guild_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT *
                FROM voice_point_sessions
                WHERE guild_id = ? AND status = 'active'
                ORDER BY started_at ASC
                """,
                (guild_id,),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def list_recent_voice_point_sessions(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT *
                FROM voice_point_sessions
                WHERE guild_id = ? AND status = 'closed'
                ORDER BY ended_at DESC, id DESC
                LIMIT ?
                """,
                (guild_id, limit),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def latest_voice_point_session(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT *
                FROM voice_point_sessions
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def update_voice_point_session(self, session_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        columns = ", ".join(f"{column} = ?" for column in fields)
        params = tuple(fields.values()) + (session_id,)
        await self._run_write(f"UPDATE voice_point_sessions SET {columns} WHERE id = ?", params)

    async def add_voice_point_segment(
        self,
        session_id: int,
        channel_id: int | None,
        channel_group: str,
        segment_kind: str,
        started_at: str,
        ended_at: str,
        duration_seconds: int,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO voice_point_segments (
                session_id,
                channel_id,
                channel_group,
                segment_kind,
                started_at,
                ended_at,
                duration_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, channel_id, channel_group, segment_kind, started_at, ended_at, duration_seconds),
        )

    async def get_voice_point_segments(self, session_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT *
                FROM voice_point_segments
                WHERE session_id = ?
                ORDER BY started_at ASC, id ASC
                """,
                (session_id,),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def count_active_voice_point_sessions(self, guild_id: int) -> int:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT COUNT(*) AS total FROM voice_point_sessions WHERE guild_id = ? AND status = 'active'",
                (guild_id,),
            )
        finally:
            await conn.close()
        return int(row["total"]) if row else 0

    async def save_voice_point_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO voice_point_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_voice_point_panel_message(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM voice_point_panel_state WHERE guild_id = ?",
                (guild_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def save_registration_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO registration_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_registration_panel_message(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM registration_panel_state WHERE guild_id = ?",
                (guild_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def save_member_registration_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO member_registration_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_member_registration_panel_message(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM member_registration_panel_state WHERE guild_id = ?",
                (guild_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_registration_record(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM registration_records WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def upsert_registration_record(
        self,
        guild_id: int,
        user_id: int,
        *,
        status: str,
        registered_role_id: int | None,
        removed_role_id: int | None,
        source_channel_id: int | None,
        source_message_id: int | None,
        source_interaction_id: int | None,
        notes: str | None,
        mark_registered: bool,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO registration_records (
                guild_id,
                user_id,
                status,
                registered_at,
                last_attempt_at,
                registered_role_id,
                removed_role_id,
                source_channel_id,
                source_message_id,
                source_interaction_id,
                notes
            )
            VALUES (
                ?, ?, ?,
                CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END,
                CURRENT_TIMESTAMP,
                ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                status = excluded.status,
                registered_at = CASE
                    WHEN excluded.registered_at IS NOT NULL THEN excluded.registered_at
                    ELSE registration_records.registered_at
                END,
                last_attempt_at = CURRENT_TIMESTAMP,
                registered_role_id = COALESCE(excluded.registered_role_id, registration_records.registered_role_id),
                removed_role_id = excluded.removed_role_id,
                source_channel_id = excluded.source_channel_id,
                source_message_id = excluded.source_message_id,
                source_interaction_id = excluded.source_interaction_id,
                notes = excluded.notes
            """,
            (
                guild_id,
                user_id,
                status,
                int(mark_registered),
                registered_role_id,
                removed_role_id,
                source_channel_id,
                source_message_id,
                source_interaction_id,
                notes,
            ),
        )

    async def get_latest_member_registration_session(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT *
                FROM member_registration_sessions
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_member_registration_session(self, session_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM member_registration_sessions WHERE id = ?",
                (session_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def start_member_registration_session(
        self,
        guild_id: int,
        user_id: int,
        *,
        source_channel_id: int | None,
        source_message_id: int | None,
        panel_message_id: int | None,
    ) -> int:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT id
                FROM member_registration_sessions
                WHERE guild_id = ? AND user_id = ? AND status = 'in_progress'
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
            if row is not None:
                return int(row["id"])
            await conn.execute(
                """
                INSERT INTO member_registration_sessions (
                    guild_id,
                    user_id,
                    status,
                    source_channel_id,
                    source_message_id,
                    panel_message_id,
                    last_step,
                    updated_at
                )
                VALUES (?, ?, 'in_progress', ?, ?, ?, 'started', CURRENT_TIMESTAMP)
                """,
                (guild_id, user_id, source_channel_id, source_message_id, panel_message_id),
            )
            await conn.commit()
            row = await self.fetchone(
                conn,
                """
                SELECT id
                FROM member_registration_sessions
                WHERE guild_id = ? AND user_id = ? AND status = 'in_progress'
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return int(row["id"])

    async def update_member_registration_session(
        self,
        session_id: int,
        fields: dict[str, Any],
    ) -> None:
        if not fields:
            return
        assignments: list[str] = []
        params: list[Any] = []
        for column, value in fields.items():
            assignments.append(f"{column} = ?")
            params.append(value)
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        params.append(session_id)
        query = f"UPDATE member_registration_sessions SET {', '.join(assignments)} WHERE id = ?"
        await self._run_write(query, tuple(params))

    async def list_member_registration_sessions(
        self,
        guild_id: int,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses = ["guild_id = ?"]
        params: list[Any] = [guild_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        params.append(limit)
        query = (
            "SELECT * FROM member_registration_sessions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id DESC LIMIT ?"
        )
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def save_beta_program_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO beta_program_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_beta_program_panel_message(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM beta_program_panel_state WHERE guild_id = ?",
                (guild_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def create_beta_tester_application(
        self,
        guild_id: int,
        user_id: int,
        *,
        panel_channel_id: int | None,
        panel_message_id: int | None,
        referral_type: str = "direct",
        influencer_code: str | None = None,
        influencer_name: str | None = None,
        influencer_owner_id: int | None = None,
        status: str = "in_progress",
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO beta_tester_applications (
                    guild_id,
                    user_id,
                    status,
                    answers_json,
                    panel_channel_id,
                    panel_message_id,
                    referral_type,
                    influencer_code,
                    influencer_name,
                    influencer_owner_id,
                    last_step,
                    updated_at
                )
                VALUES (?, ?, ?, '{}', ?, ?, ?, ?, ?, ?, 'started', CURRENT_TIMESTAMP)
                """,
                (
                    guild_id,
                    user_id,
                    status,
                    panel_channel_id,
                    panel_message_id,
                    referral_type,
                    influencer_code,
                    influencer_name,
                    influencer_owner_id,
                ),
            )
            await conn.commit()
            row = await self.fetchone(conn, "SELECT last_insert_rowid() AS application_id", ())
        finally:
            await conn.close()
        return int(row["application_id"])

    async def upsert_beta_influencer_code(
        self,
        guild_id: int,
        code: str,
        influencer_name: str,
        *,
        owner_user_id: int | None = None,
        created_by_id: int | None = None,
        slot_limit: int = 5,
        active: bool = True,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO beta_influencer_codes (
                guild_id, code, influencer_name, owner_user_id, slot_limit, slot_used, active, created_by_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, code) DO UPDATE SET
                influencer_name = excluded.influencer_name,
                owner_user_id = excluded.owner_user_id,
                slot_limit = excluded.slot_limit,
                active = excluded.active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, code, influencer_name, owner_user_id, slot_limit, int(active), created_by_id),
        )

    async def get_beta_influencer_code(self, guild_id: int, code: str) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM beta_influencer_codes WHERE guild_id = ? AND code = ?",
                (guild_id, code),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def has_user_used_beta_influencer_code(
        self,
        guild_id: int,
        user_id: int,
        code: str,
        *,
        ignored_statuses: tuple[str, ...] = (),
    ) -> bool:
        clauses = ["guild_id = ?", "user_id = ?", "influencer_code = ?"]
        params: list[Any] = [guild_id, user_id, code]
        if ignored_statuses:
            placeholders = ", ".join("?" for _ in ignored_statuses)
            clauses.append(f"status NOT IN ({placeholders})")
            params.extend(ignored_statuses)
        query = (
            "SELECT 1 FROM beta_tester_applications WHERE "
            + " AND ".join(clauses)
            + " LIMIT 1"
        )
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, query, tuple(params))
        finally:
            await conn.close()
        return row is not None

    async def get_beta_influencer_owner_quota(
        self,
        guild_id: int,
        *,
        owner_user_id: int | None,
        influencer_name: str,
    ) -> dict[str, int]:
        if owner_user_id is not None:
            where = "guild_id = ? AND owner_user_id = ?"
            params: tuple[Any, ...] = (guild_id, owner_user_id)
        else:
            where = "guild_id = ? AND owner_user_id IS NULL AND influencer_name = ? COLLATE NOCASE"
            params = (guild_id, influencer_name)
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                f"""
                SELECT
                    COUNT(*) AS total_codes,
                    SUM(CASE WHEN slot_used > 0 THEN 1 ELSE 0 END) AS used_codes,
                    SUM(CASE WHEN active = 1 AND slot_used = 0 THEN 1 ELSE 0 END) AS pending_codes
                FROM beta_influencer_codes
                WHERE {where}
                """,
                params,
            )
        finally:
            await conn.close()
        return {
            "total_codes": int(row["total_codes"] or 0) if row else 0,
            "used_codes": int(row["used_codes"] or 0) if row else 0,
            "pending_codes": int(row["pending_codes"] or 0) if row else 0,
        }

    async def set_beta_influencer_code_active(self, guild_id: int, code: str, active: bool) -> bool:
        conn = await self.connect()
        try:
            cursor = await conn.execute(
                """
                UPDATE beta_influencer_codes
                SET active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND code = ?
                """,
                (int(active), guild_id, code),
            )
            await conn.commit()
            changed = cursor.rowcount > 0
            await cursor.close()
        finally:
            await conn.close()
        return changed

    async def try_consume_beta_influencer_slot(self, guild_id: int, code: str) -> bool:
        conn = await self.connect()
        try:
            cursor = await conn.execute(
                """
                UPDATE beta_influencer_codes
                SET slot_used = slot_used + 1, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ?
                  AND code = ?
                  AND active = 1
                  AND slot_used < slot_limit
                """,
                (guild_id, code),
            )
            await conn.commit()
            consumed = cursor.rowcount > 0
            await cursor.close()
        finally:
            await conn.close()
        return consumed

    async def reset_beta_influencer_slots(self, guild_id: int, code: str | None = None) -> int:
        conn = await self.connect()
        try:
            if code:
                cursor = await conn.execute(
                    """
                    UPDATE beta_influencer_codes
                    SET slot_used = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = ? AND code = ?
                    """,
                    (guild_id, code),
                )
            else:
                cursor = await conn.execute(
                    """
                    UPDATE beta_influencer_codes
                    SET slot_used = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                )
            await conn.commit()
            changed = cursor.rowcount
            await cursor.close()
        finally:
            await conn.close()
        return int(changed)

    async def list_beta_influencer_codes(self, guild_id: int, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        clauses = ["guild_id = ?"]
        params: list[Any] = [guild_id]
        if not include_inactive:
            clauses.append("active = 1")
        query = (
            "SELECT * FROM beta_influencer_codes WHERE "
            + " AND ".join(clauses)
            + " ORDER BY active DESC, influencer_name COLLATE NOCASE ASC, code ASC"
        )
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def get_beta_influencer_code_stats(self, guild_id: int, code: str) -> dict[str, int]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT status, COUNT(*) AS total
                FROM beta_tester_applications
                WHERE guild_id = ? AND influencer_code = ?
                GROUP BY status
                """,
                (guild_id, code),
            )
        finally:
            await conn.close()
        stats = {"total": 0, "in_progress": 0, "pending": 0, "approved": 0, "rejected": 0}
        for row in rows:
            status = str(row["status"])
            total = int(row["total"])
            stats[status] = total
            stats["total"] += total
        return stats

    async def get_beta_tester_application(self, application_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM beta_tester_applications WHERE id = ?",
                (application_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_latest_beta_tester_application(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT *
                FROM beta_tester_applications
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def list_pending_beta_tester_application_ids(self, guild_id: int) -> list[int]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT id
                FROM beta_tester_applications
                WHERE guild_id = ? AND status = 'pending'
                ORDER BY id ASC
                """,
                (guild_id,),
            )
        finally:
            await conn.close()
        return [int(row["id"]) for row in rows]

    async def update_beta_tester_application(self, application_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        assignments: list[str] = []
        params: list[Any] = []
        for column, value in fields.items():
            assignments.append(f"{column} = ?")
            params.append(value)
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        params.append(application_id)
        query = f"UPDATE beta_tester_applications SET {', '.join(assignments)} WHERE id = ?"
        await self._run_write(query, tuple(params))

    async def set_beta_tester_application_answers(
        self,
        application_id: int,
        *,
        answers: dict[str, str],
        last_step: str,
    ) -> None:
        payload = json.dumps(answers, ensure_ascii=False)
        await self._run_write(
            """
            UPDATE beta_tester_applications
            SET answers_json = ?, last_step = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (payload, last_step, application_id),
        )

    async def list_beta_tester_applications(
        self,
        guild_id: int,
        *,
        status: str | None = None,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses = ["guild_id = ?"]
        params: list[Any] = [guild_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        params.append(limit)
        query = (
            "SELECT * FROM beta_tester_applications WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id DESC LIMIT ?"
        )
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def save_management_dashboard_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO management_dashboard_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_management_dashboard_message(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM management_dashboard_state WHERE guild_id = ?",
                (guild_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def create_staff_operational_alert(
        self,
        guild_id: int,
        alert_type: str,
        severity: str,
        detail: str,
        *,
        user_id: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        context_json = json.dumps(context or {}, ensure_ascii=False)
        await self._run_write(
            """
            INSERT INTO staff_operational_alerts (
                guild_id,
                user_id,
                alert_type,
                severity,
                detail,
                context_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, alert_type, severity, detail, context_json),
        )

    async def list_recent_staff_operational_alerts(self, guild_id: int, limit: int = 20) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                """
                SELECT *
                FROM staff_operational_alerts
                WHERE guild_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (guild_id, limit),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def count_staff_operational_alerts(
        self,
        guild_id: int,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        user_id: int | None = None,
    ) -> int:
        clauses = ["guild_id = ?"]
        params: list[Any] = [guild_id]
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if start_at:
            clauses.append("created_at >= ?")
            params.append(start_at)
        if end_at:
            clauses.append("created_at < ?")
            params.append(end_at)
        query = "SELECT COUNT(*) AS total FROM staff_operational_alerts WHERE " + " AND ".join(clauses)
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, query, tuple(params))
        finally:
            await conn.close()
        return int(row["total"]) if row else 0

    async def list_voice_segments_in_range(
        self,
        guild_id: int,
        start_at: str,
        end_at: str,
        *,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        where = [
            "s.guild_id = ?",
            "seg.ended_at > ?",
            "seg.started_at < ?",
        ]
        params: list[Any] = [guild_id, start_at, end_at]
        if user_id is not None:
            where.append("s.user_id = ?")
            params.append(user_id)
        query = (
            "SELECT seg.*, s.user_id, s.status AS session_status, s.close_mode, s.start_mode "
            "FROM voice_point_segments seg "
            "JOIN voice_point_sessions s ON s.id = seg.session_id "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY seg.started_at ASC, seg.id ASC"
        )
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def list_voice_sessions_in_range(
        self,
        guild_id: int,
        start_at: str,
        end_at: str,
        *,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        where = [
            "guild_id = ?",
            "COALESCE(ended_at, CURRENT_TIMESTAMP) > ?",
            "started_at < ?",
        ]
        params: list[Any] = [guild_id, start_at, end_at]
        if user_id is not None:
            where.append("user_id = ?")
            params.append(user_id)
        query = "SELECT * FROM voice_point_sessions WHERE " + " AND ".join(where) + " ORDER BY started_at DESC, id DESC"
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def list_staff_tickets_by_period(
        self,
        guild_id: int,
        start_at: str,
        end_at: str,
        *,
        staff_user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        where = [
            "guild_id = ?",
            "closed_at IS NOT NULL",
            "closed_at >= ?",
            "closed_at < ?",
        ]
        params: list[Any] = [guild_id, start_at, end_at]
        if staff_user_id is not None:
            where.append("COALESCE(resolved_staff_id, closed_by_id, closed_by) = ?")
            params.append(staff_user_id)
        query = (
            "SELECT * FROM tickets WHERE " + " AND ".join(where) + " "
            "ORDER BY closed_at DESC, id DESC"
        )
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def list_staff_ticket_claims_by_period(
        self,
        guild_id: int,
        start_at: str,
        end_at: str,
        *,
        staff_user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        where = [
            "guild_id = ?",
            "opened_at >= ?",
            "opened_at < ?",
            "assigned_staff_id IS NOT NULL",
        ]
        params: list[Any] = [guild_id, start_at, end_at]
        if staff_user_id is not None:
            where.append("assigned_staff_id = ?")
            params.append(staff_user_id)
        query = "SELECT * FROM tickets WHERE " + " AND ".join(where) + " ORDER BY opened_at DESC, id DESC"
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    # ── Staff Timeclock ─────────────────────────────────────────────────────────

    async def get_staff_roles(self, guild_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, "SELECT * FROM staff_roles_config WHERE guild_id = ? ORDER BY id ASC", (guild_id,))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def add_staff_role(self, guild_id: int, role_id: int) -> None:
        await self._run_write(
            "INSERT OR IGNORE INTO staff_roles_config (guild_id, role_id) VALUES (?, ?)",
            (guild_id, role_id),
        )

    async def remove_staff_role(self, guild_id: int, role_id: int) -> None:
        await self._run_write(
            "DELETE FROM staff_roles_config WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )

    async def get_channel_rule(self, guild_id: int, channel_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM staff_voice_channel_rules WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def set_channel_rule(self, guild_id: int, channel_id: int, rule_type: str) -> None:
        await self._run_write(
            """
            INSERT INTO staff_voice_channel_rules (guild_id, channel_id, rule_type, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET rule_type = excluded.rule_type, updated_at = excluded.updated_at
            """,
            (guild_id, channel_id, rule_type),
        )

    async def set_channel_rule_v3(
        self,
        guild_id: int,
        channel_id: int,
        rule_type: str,
        activity_suggested: str | None = None,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO staff_voice_channel_rules (guild_id, channel_id, rule_type, activity_suggested, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                rule_type = excluded.rule_type,
                activity_suggested = excluded.activity_suggested,
                updated_at = excluded.updated_at
            """,
            (guild_id, channel_id, rule_type, activity_suggested),
        )

    async def remove_channel_rule(self, guild_id: int, channel_id: int) -> None:
        await self._run_write(
            "DELETE FROM staff_voice_channel_rules WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )

    async def get_all_channel_rules(self, guild_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                "SELECT * FROM staff_voice_channel_rules WHERE guild_id = ? ORDER BY id ASC",
                (guild_id,),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def create_staff_session(
        self,
        guild_id: int,
        user_id: int,
        started_at: str,
        activity: str = "Não classificado",
        environment: str | None = None,
        channel_id: int | None = None,
        notes: str | None = None,
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO staff_work_sessions (
                    guild_id, user_id, status, started_at,
                    current_activity, current_environment, current_channel_id,
                    segment_started_at, notes, updated_at
                ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, started_at, activity, environment, channel_id, started_at, notes, started_at),
            )
            await conn.commit()
            row = await self.fetchone(
                conn,
                "SELECT id FROM staff_work_sessions WHERE guild_id = ? AND user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return int(row["id"])

    async def get_staff_open_session(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM staff_work_sessions WHERE guild_id = ? AND user_id = ? AND status IN ('active','paused','pending') ORDER BY id DESC LIMIT 1",
                (guild_id, user_id),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_staff_session(self, session_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM staff_work_sessions WHERE id = ?", (session_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def list_open_staff_sessions(self, guild_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                "SELECT * FROM staff_work_sessions WHERE guild_id = ? AND status IN ('active','paused','pending') ORDER BY started_at ASC",
                (guild_id,),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def update_staff_session(self, session_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        columns = ", ".join(f"{col} = ?" for col in fields)
        params = tuple(fields.values()) + (session_id,)
        await self._run_write(f"UPDATE staff_work_sessions SET {columns} WHERE id = ?", params)

    async def add_staff_segment(
        self,
        session_id: int,
        guild_id: int,
        user_id: int,
        activity: str,
        started_at: str,
        environment: str | None = None,
        channel_id: int | None = None,
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO staff_work_segments (session_id, guild_id, user_id, activity, environment, channel_id, started_at, segment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'valid')
                """,
                (session_id, guild_id, user_id, activity, environment, channel_id, started_at),
            )
            await conn.commit()
            row = await self.fetchone(conn, "SELECT id FROM staff_work_segments WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
        finally:
            await conn.close()
        return int(row["id"])

    async def close_staff_segment(self, segment_id: int, ended_at: str, duration_seconds: int) -> None:
        await self._run_write(
            "UPDATE staff_work_segments SET ended_at = ?, duration_seconds = ? WHERE id = ?",
            (ended_at, duration_seconds, segment_id),
        )

    async def get_session_segments(self, session_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, "SELECT * FROM staff_work_segments WHERE session_id = ? ORDER BY started_at ASC", (session_id,))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def open_staff_pause(
        self,
        session_id: int,
        guild_id: int,
        user_id: int,
        started_at: str,
        reason: str | None = None,
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                "INSERT INTO staff_work_pauses (session_id, guild_id, user_id, started_at, reason) VALUES (?, ?, ?, ?, ?)",
                (session_id, guild_id, user_id, started_at, reason),
            )
            await conn.commit()
            row = await self.fetchone(conn, "SELECT id FROM staff_work_pauses WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
        finally:
            await conn.close()
        return int(row["id"])

    async def close_staff_pause(self, pause_id: int, ended_at: str, duration_seconds: int) -> None:
        await self._run_write(
            "UPDATE staff_work_pauses SET ended_at = ?, duration_seconds = ? WHERE id = ?",
            (ended_at, duration_seconds, pause_id),
        )

    async def create_staff_checkin(
        self,
        session_id: int,
        guild_id: int,
        user_id: int,
        sent_at: str,
        deadline_at: str,
        message_id: int | None = None,
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                "INSERT INTO staff_work_checkins (session_id, guild_id, user_id, sent_at, deadline_at, message_id) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, guild_id, user_id, sent_at, deadline_at, message_id),
            )
            await conn.commit()
            row = await self.fetchone(conn, "SELECT id FROM staff_work_checkins WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
        finally:
            await conn.close()
        return int(row["id"])

    async def update_staff_checkin(self, checkin_id: int, status: str, answered_at: str | None = None, response: str | None = None) -> None:
        await self._run_write(
            "UPDATE staff_work_checkins SET status = ?, answered_at = ?, response = ? WHERE id = ?",
            (status, answered_at, response, checkin_id),
        )

    async def get_pending_checkin(self, session_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                "SELECT * FROM staff_work_checkins WHERE session_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def get_expired_checkins(self, guild_id: int, now_iso: str) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                "SELECT * FROM staff_work_checkins WHERE guild_id = ? AND status = 'pending' AND deadline_at <= ?",
                (guild_id, now_iso),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def add_staff_adjustment(
        self,
        guild_id: int,
        user_id: int,
        admin_id: int,
        adjustment_seconds: int,
        reason: str,
        session_id: int | None = None,
    ) -> None:
        await self._run_write(
            "INSERT INTO staff_work_adjustments (guild_id, user_id, admin_id, adjustment_seconds, reason, session_id) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, admin_id, adjustment_seconds, reason, session_id),
        )

    async def get_staff_adjustments(self, guild_id: int, user_id: int) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, "SELECT * FROM staff_work_adjustments WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC", (guild_id, user_id))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def log_staff_event(self, guild_id: int, user_id: int, event_type: str, session_id: int | None = None, metadata_json: str | None = None) -> None:
        await self._run_write(
            "INSERT INTO staff_work_events (guild_id, user_id, event_type, session_id, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, event_type, session_id, metadata_json),
        )

    async def get_staff_segments_in_range(
        self,
        guild_id: int,
        start_at: str,
        end_at: str,
        *,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        where = ["seg.guild_id = ?", "seg.started_at < ?", "COALESCE(seg.ended_at, ?) > ?"]
        params: list[Any] = [guild_id, end_at, end_at, start_at]
        if user_id is not None:
            where.append("seg.user_id = ?")
            params.append(user_id)
        query = (
            "SELECT seg.*, s.status AS session_status FROM staff_work_segments seg "
            "JOIN staff_work_sessions s ON s.id = seg.session_id "
            "WHERE " + " AND ".join(where) + " ORDER BY seg.started_at ASC"
        )
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def get_staff_sessions_in_range(
        self,
        guild_id: int,
        start_at: str,
        end_at: str,
        *,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        where = ["guild_id = ?", "started_at < ?", "COALESCE(ended_at, ?) > ?"]
        params: list[Any] = [guild_id, end_at, end_at, start_at]
        if user_id is not None:
            where.append("user_id = ?")
            params.append(user_id)
        query = "SELECT * FROM staff_work_sessions WHERE " + " AND ".join(where) + " ORDER BY started_at DESC"
        conn = await self.connect()
        try:
            rows = await self.fetchall(conn, query, tuple(params))
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def get_staff_timeclock_panel(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM staff_timeclock_panel_state WHERE guild_id = ?", (guild_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def save_staff_timeclock_panel(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO staff_timeclock_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, message_id = excluded.message_id, updated_at = excluded.updated_at
            """,
            (guild_id, channel_id, message_id),
        )

    async def get_staff_timeclock_config(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM staff_timeclock_config WHERE guild_id = ?", (guild_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def update_staff_timeclock_config(self, guild_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        columns = [
            "guild_id", "control_channel_id", "logs_channel_id", "auto_prompt_on_voice_join",
            "reminder_after_seconds", "admin_alert_after_seconds", "auto_pause_on_voice_leave",
            "auto_pause_delay_seconds", "auto_pause_on_afk", "checkin_voice_seconds",
            "checkin_external_seconds", "checkin_timeout_seconds", "alert_cooldown_seconds",
            "admin_panel_auto_refresh_seconds", "use_dm_as_fallback", "test_mode"
        ]
        defaults = {
            "guild_id": guild_id,
            "control_channel_id": None,
            "logs_channel_id": None,
            "auto_prompt_on_voice_join": 1,
            "reminder_after_seconds": 180,
            "admin_alert_after_seconds": 600,
            "auto_pause_on_voice_leave": 1,
            "auto_pause_delay_seconds": 120,
            "auto_pause_on_afk": 1,
            "checkin_voice_seconds": 3600,
            "checkin_external_seconds": 1800,
            "checkin_timeout_seconds": 300,
            "alert_cooldown_seconds": 600,
            "admin_panel_auto_refresh_seconds": 120,
            "use_dm_as_fallback": 0,
            "test_mode": 0,
        }
        current = await self.get_staff_timeclock_config(guild_id) or {}
        current = {**defaults, **current}
        merged = {**current, **fields, "guild_id": guild_id}
        values = tuple(merged.get(col) for col in columns)
        assignments = ", ".join(f"{col} = excluded.{col}" for col in columns if col != "guild_id")
        await self._run_write(
            f"""
            INSERT INTO staff_timeclock_config ({", ".join(columns)}, updated_at)
            VALUES ({", ".join("?" for _ in columns)}, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET {assignments}, updated_at = CURRENT_TIMESTAMP
            """,
            values,
        )

    async def upsert_staff_presence_alert(
        self,
        guild_id: int,
        user_id: int,
        alert_type: str,
        channel_id: int | None,
        message_id: int | None,
        started_at: str,
        metadata_json: str | None = None,
    ) -> int:
        conn = await self.connect()
        try:
            await conn.execute(
                """
                INSERT INTO staff_call_presence_alerts (
                    guild_id, user_id, channel_id, alert_type, message_id,
                    started_at, last_reminder_at, status, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(guild_id, user_id, alert_type) WHERE status = 'active'
                DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = COALESCE(excluded.message_id, staff_call_presence_alerts.message_id),
                    last_reminder_at = excluded.last_reminder_at,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (guild_id, user_id, channel_id, alert_type, message_id, started_at, started_at, metadata_json, started_at),
            )
            await conn.commit()
            row = await self.fetchone(
                conn,
                """
                SELECT id FROM staff_call_presence_alerts
                WHERE guild_id = ? AND user_id = ? AND alert_type = ? AND status = 'active'
                ORDER BY id DESC LIMIT 1
                """,
                (guild_id, user_id, alert_type),
            )
        finally:
            await conn.close()
        return int(row["id"])

    async def update_staff_presence_alert(self, alert_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        columns = ", ".join(f"{col} = ?" for col in fields)
        params = tuple(fields.values()) + (alert_id,)
        await self._run_write(f"UPDATE staff_call_presence_alerts SET {columns} WHERE id = ?", params)

    async def get_active_staff_presence_alert(self, guild_id: int, user_id: int, alert_type: str) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(
                conn,
                """
                SELECT * FROM staff_call_presence_alerts
                WHERE guild_id = ? AND user_id = ? AND alert_type = ? AND status = 'active'
                ORDER BY id DESC LIMIT 1
                """,
                (guild_id, user_id, alert_type),
            )
        finally:
            await conn.close()
        return dict(row) if row else None

    async def list_active_staff_presence_alerts(self, guild_id: int, alert_type: str | None = None) -> list[dict[str, Any]]:
        where = ["guild_id = ?", "status = 'active'"]
        params: list[Any] = [guild_id]
        if alert_type is not None:
            where.append("alert_type = ?")
            params.append(alert_type)
        conn = await self.connect()
        try:
            rows = await self.fetchall(
                conn,
                "SELECT * FROM staff_call_presence_alerts WHERE " + " AND ".join(where) + " ORDER BY updated_at DESC",
                tuple(params),
            )
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def resolve_staff_presence_alert(self, guild_id: int, user_id: int, alert_type: str, status: str = "resolved") -> None:
        await self._run_write(
            """
            UPDATE staff_call_presence_alerts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND user_id = ? AND alert_type = ? AND status = 'active'
            """,
            (status, guild_id, user_id, alert_type),
        )

    async def add_staff_notification(
        self,
        guild_id: int,
        user_id: int,
        notification_type: str,
        sent_at: str,
        channel_id: int | None = None,
        message_id: int | None = None,
        status: str = "sent",
        metadata_json: str | None = None,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO staff_timeclock_notifications (
                guild_id, user_id, notification_type, channel_id, message_id,
                sent_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, notification_type, channel_id, message_id, sent_at, status, metadata_json),
        )

    async def add_staff_admin_action(
        self,
        guild_id: int,
        admin_id: int,
        target_user_id: int | None,
        action_type: str,
        reason: str,
        metadata_json: str | None = None,
    ) -> None:
        await self._run_write(
            """
            INSERT INTO staff_admin_actions (guild_id, admin_id, target_user_id, action_type, reason, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, admin_id, target_user_id, action_type, reason, metadata_json),
        )

    async def get_staff_timeclock_admin_panel(self, guild_id: int) -> dict[str, Any] | None:
        conn = await self.connect()
        try:
            row = await self.fetchone(conn, "SELECT * FROM staff_timeclock_admin_panel_state WHERE guild_id = ?", (guild_id,))
        finally:
            await conn.close()
        return dict(row) if row else None

    async def save_staff_timeclock_admin_panel(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._run_write(
            """
            INSERT INTO staff_timeclock_admin_panel_state (guild_id, channel_id, message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                message_id = excluded.message_id,
                updated_at = excluded.updated_at
            """,
            (guild_id, channel_id, message_id),
        )
