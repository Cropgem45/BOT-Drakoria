from __future__ import annotations

import asyncio
import inspect
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import discord

try:
    BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    BRASILIA_TZ = UTC  # type: ignore[assignment]

# ── Constantes ───────────────────────────────────────────────────────────────

ACTIVITIES: list[str] = [
    "Desenvolvimento",
    "Gestão",
    "Atendimento",
    "Moderação",
    "Suporte",
    "Arte/Design",
    "Social Media",
    "Organização",
    "Evento",
    "Reunião",
    "Testes",
    "Documentação",
    "Outro",
    "Não classificado",
]

CHANNEL_RULE_LABELS: dict[str, str] = {
    "work": "Canal de trabalho válido",
    "neutral": "Canal neutro (não define atividade)",
    "invalid": "Canal que não conta",
}

STATUS_LABELS: dict[str, str] = {
    "active": "Em expediente",
    "paused": "Pausado",
    "pending": "Pendente de validação",
    "closed": "Encerrado",
}

CHECKIN_INTERVAL_IN_CALL = 3600   # 60 min em call válida
CHECKIN_INTERVAL_EXTERNAL = 1800  # 30 min fora de call
CHECKIN_TIMEOUT = 300             # 5 min para responder
MAX_SESSION_HOURS = 12            # sinaliza como suspeito acima disso


@dataclass(slots=True)
class TimeclockStatus:
    has_session: bool
    status: str
    summary: str
    session: dict[str, Any] | None


@dataclass(slots=True)
class PeriodStats:
    valid_seconds: int = 0
    paused_seconds: int = 0
    pending_seconds: int = 0
    adjustment_seconds: int = 0
    by_activity: dict[str, int] = field(default_factory=dict)
    session_count: int = 0


# ── Serviço principal ─────────────────────────────────────────────────────────

class StaffTimeclockService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}
        self._checkin_task: asyncio.Task[None] | None = None
        self._maintenance_task: asyncio.Task[None] | None = None
        self._restored = False

    # ── Autorização ──────────────────────────────────────────────────────────

    async def is_staff_member(self, member: discord.Member) -> bool:
        role_ids = {row["role_id"] for row in await self.bot.db.get_staff_roles(member.guild.id)}
        if not role_ids:
            fallback = set(self.bot.server_map.voice_point_allowed_role_ids())
            role_ids = fallback
        return bool(role_ids.intersection(r.id for r in member.roles))

    def has_manage_permission(self, member: discord.Member) -> bool:
        return self.bot.permission_service.has(member, "manage_points")

    async def get_runtime_config(self, guild_id: int) -> dict[str, Any]:
        getter = getattr(self.bot.db, "get_staff_timeclock_config", None)
        stored = await self._maybe_await(getter(guild_id)) if callable(getter) else None
        if not isinstance(stored, dict):
            stored = {}
        base = {
            "control_channel_id": self._call_server_map("staff_timeclock_control_channel_id", self.bot.server_map.staff_timeclock_panel_channel_id()),
            "logs_channel_id": self.bot.server_map.staff_timeclock_log_channel_id(),
            "auto_prompt_on_voice_join": 1,
            "reminder_after_seconds": self._call_server_map("staff_timeclock_reminder_after_seconds", 180),
            "admin_alert_after_seconds": self._call_server_map("staff_timeclock_admin_alert_after_seconds", 600),
            "auto_pause_on_voice_leave": 1,
            "auto_pause_delay_seconds": self._call_server_map("staff_timeclock_auto_pause_delay_seconds", 120),
            "auto_pause_on_afk": 1,
            "checkin_voice_seconds": self.bot.server_map.staff_timeclock_checkin_interval_in_call(),
            "checkin_external_seconds": self.bot.server_map.staff_timeclock_checkin_interval_external(),
            "checkin_timeout_seconds": self.bot.server_map.staff_timeclock_checkin_timeout(),
            "alert_cooldown_seconds": self._call_server_map("staff_timeclock_alert_cooldown_seconds", 600),
            "admin_panel_auto_refresh_seconds": 120,
            "use_dm_as_fallback": 0,
            "test_mode": 0,
        }
        base.update({k: v for k, v in stored.items() if v is not None})
        if int(base.get("test_mode") or 0):
            base["reminder_after_seconds"] = min(int(base["reminder_after_seconds"]), 60)
            base["admin_alert_after_seconds"] = min(int(base["admin_alert_after_seconds"]), 180)
            base["auto_pause_delay_seconds"] = min(int(base["auto_pause_delay_seconds"]), 60)
            base["checkin_voice_seconds"] = min(int(base["checkin_voice_seconds"]), 120)
            base["checkin_external_seconds"] = min(int(base["checkin_external_seconds"]), 90)
            base["checkin_timeout_seconds"] = min(int(base["checkin_timeout_seconds"]), 30)
        return base

    async def configure_control_channel(self, guild: discord.Guild, channel: discord.TextChannel) -> None:
        await self.bot.db.update_staff_timeclock_config(guild.id, {"control_channel_id": channel.id})
        await self.bot.db.log_staff_event(guild.id, channel.id, "control_channel_configured", None, json.dumps({"channel_id": channel.id}))

    async def configure_logs_channel(self, guild: discord.Guild, channel: discord.TextChannel) -> None:
        await self.bot.db.update_staff_timeclock_config(guild.id, {"logs_channel_id": channel.id})
        await self.bot.db.log_staff_event(guild.id, channel.id, "logs_channel_configured", None, json.dumps({"channel_id": channel.id}))

    # ── Ciclo de vida da sessão ───────────────────────────────────────────────

    async def start_session(self, member: discord.Member, *, notes: str | None = None) -> dict[str, Any]:
        async with self._lock_for(member.id):
            existing = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
            if existing:
                raise RuntimeError("Já existe um expediente aberto para este membro.")
            if not await self.is_staff_member(member):
                raise RuntimeError("Você não possui cargo de staff para registrar expediente.")
            now = self._utcnow()
            environment, channel_id = self._get_member_environment(member)
            session_id = await self.bot.db.create_staff_session(
                guild_id=member.guild.id,
                user_id=member.id,
                started_at=self._iso(now),
                activity="Não classificado",
                environment=environment,
                channel_id=channel_id,
                notes=notes,
            )
            await self.bot.db.add_staff_segment(
                session_id=session_id,
                guild_id=member.guild.id,
                user_id=member.id,
                activity="Não classificado",
                started_at=self._iso(now),
                environment=environment,
                channel_id=channel_id,
            )
            await self.bot.db.log_staff_event(
                member.guild.id, member.id, "session_started", session_id,
                json.dumps({"environment": environment, "channel_id": channel_id}),
            )
            await self._dispatch_log(
                member.guild,
                "Expediente Iniciado",
                f"{member.mention} iniciou o expediente.",
                fields=[
                    ("Staff", member.mention, True),
                    ("Horário", self._format_dt(now), True),
                    ("Ambiente", environment or "Fora da call", True),
                    ("Atividade", "Não classificado", True),
                ],
                color=self.bot.embeds.success_color,
            )
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        await self.resolve_alert(member.guild, member.id, "voice_without_session", "resolved")
        await self.resolve_alert(member.guild, member.id, "paused_in_valid_voice", "resolved")
        await self.refresh_panel(member.guild)
        await self.refresh_admin_panel(member.guild)
        return session or {}

    async def pause_session(self, member: discord.Member, *, reason: str | None = None, actor: discord.Member | None = None) -> dict[str, Any]:
        async with self._lock_for(member.id):
            session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
            if session is None:
                raise RuntimeError("Nenhum expediente aberto encontrado para este membro.")
            if session["status"] == "paused":
                raise RuntimeError("O expediente já está pausado.")
            now = self._utcnow()
            await self._close_current_segment(session, now)
            pause_id = await self.bot.db.open_staff_pause(
                session_id=int(session["id"]),
                guild_id=member.guild.id,
                user_id=member.id,
                started_at=self._iso(now),
                reason=reason,
            )
            await self.bot.db.update_staff_session(int(session["id"]), {
                "status": "paused",
                "pause_started_at": self._iso(now),
                "active_pause_id": pause_id,
                "segment_started_at": None,
                "updated_at": self._iso(now),
            })
            await self.bot.db.log_staff_event(member.guild.id, member.id, "session_paused", int(session["id"]), json.dumps({"reason": reason}))
            await self._dispatch_log(
                member.guild,
                "Expediente Pausado",
                f"{member.mention} pausou o expediente.",
                fields=[
                    ("Staff", member.mention, True),
                    ("Horário", self._format_dt(now), True),
                    ("Motivo", reason or "Pausa manual", True),
                    ("Por", actor.mention if actor and actor.id != member.id else "Próprio membro", True),
                ],
            )
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        await self.resolve_alert(member.guild, member.id, "left_voice_with_active_session", "resolved")
        await self.refresh_panel(member.guild)
        await self.refresh_admin_panel(member.guild)
        return session or {}

    async def resume_session(self, member: discord.Member) -> dict[str, Any]:
        async with self._lock_for(member.id):
            session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
            if session is None:
                raise RuntimeError("Nenhum expediente aberto encontrado para este membro.")
            if session["status"] not in ("paused", "pending"):
                raise RuntimeError("O expediente não está pausado ou pendente.")
            now = self._utcnow()
            pause_id = session.get("active_pause_id")
            if pause_id:
                pause_started = self._parse_dt(session["pause_started_at"])
                pause_duration = max(0, int((now - pause_started).total_seconds()))
                await self.bot.db.close_staff_pause(int(pause_id), self._iso(now), pause_duration)
            environment, channel_id = self._get_member_environment(member)
            segment_id = await self.bot.db.add_staff_segment(
                session_id=int(session["id"]),
                guild_id=member.guild.id,
                user_id=member.id,
                activity=str(session["current_activity"]),
                started_at=self._iso(now),
                environment=environment,
                channel_id=channel_id,
            )
            pause_sec = max(0, int((now - self._parse_dt(session["pause_started_at"])).total_seconds())) if session.get("pause_started_at") else 0
            await self.bot.db.update_staff_session(int(session["id"]), {
                "status": "active",
                "pause_started_at": None,
                "active_pause_id": None,
                "segment_started_at": self._iso(now),
                "current_environment": environment,
                "current_channel_id": channel_id,
                "total_paused_seconds": int(session["total_paused_seconds"]) + pause_sec,
                "updated_at": self._iso(now),
            })
            await self.bot.db.log_staff_event(member.guild.id, member.id, "session_resumed", int(session["id"]), None)
            await self._dispatch_log(
                member.guild,
                "Expediente Retomado",
                f"{member.mention} retomou o expediente.",
                fields=[
                    ("Staff", member.mention, True),
                    ("Horário", self._format_dt(now), True),
                    ("Ambiente", environment or "Fora da call", True),
                    ("Atividade atual", str(session["current_activity"]), True),
                ],
                color=self.bot.embeds.success_color,
            )
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        await self.resolve_alert(member.guild, member.id, "paused_in_valid_voice", "resolved")
        await self.resolve_alert(member.guild, member.id, "afk_with_active_session", "resolved")
        await self.refresh_panel(member.guild)
        await self.refresh_admin_panel(member.guild)
        return session or {}

    async def end_session(
        self,
        member: discord.Member,
        *,
        actor: discord.Member | None = None,
        reason: str | None = None,
        close_mode: str = "manual",
    ) -> dict[str, Any]:
        async with self._lock_for(member.id):
            session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
            if session is None:
                raise RuntimeError("Nenhum expediente aberto encontrado para este membro.")
            now = self._utcnow()
            if session["status"] == "active" and session.get("segment_started_at"):
                await self._close_current_segment(session, now)
            elif session["status"] in ("paused", "pending") and session.get("active_pause_id"):
                pause_started = self._parse_dt(session["pause_started_at"])
                pause_duration = max(0, int((now - pause_started).total_seconds()))
                await self.bot.db.close_staff_pause(int(session["active_pause_id"]), self._iso(now), pause_duration)
            await self.bot.db.update_staff_session(int(session["id"]), {
                "status": "closed",
                "ended_at": self._iso(now),
                "close_reason": reason or "Encerrado manualmente.",
                "close_mode": close_mode,
                "ended_by_user_id": (actor or member).id,
                "pause_started_at": None,
                "active_pause_id": None,
                "segment_started_at": None,
                "updated_at": self._iso(now),
            })
            closed_session = await self.bot.db.get_staff_session(int(session["id"]))
            await self.bot.db.log_staff_event(member.guild.id, member.id, "session_ended", int(session["id"]), json.dumps({"close_mode": close_mode}))
        if closed_session:
            await self._send_session_report(member.guild, closed_session)
            await self._dispatch_close_log(member.guild, member, closed_session)
        for alert_type in ("voice_without_session", "left_voice_with_active_session", "afk_with_active_session", "paused_in_valid_voice", "checkin_pending"):
            await self.resolve_alert(member.guild, member.id, alert_type, "resolved")
        await self.refresh_panel(member.guild)
        await self.refresh_admin_panel(member.guild)
        return closed_session or session

    async def change_activity(self, member: discord.Member, activity: str) -> dict[str, Any]:
        if activity not in ACTIVITIES:
            raise RuntimeError(f"Atividade inválida: {activity}")
        async with self._lock_for(member.id):
            session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
            if session is None:
                raise RuntimeError("Nenhum expediente aberto encontrado para este membro.")
            if session["status"] != "active":
                raise RuntimeError("O expediente precisa estar ativo para trocar a atividade.")
            now = self._utcnow()
            old_activity = str(session["current_activity"])
            await self._close_current_segment(session, now)
            environment, channel_id = self._get_member_environment(member)
            await self.bot.db.add_staff_segment(
                session_id=int(session["id"]),
                guild_id=member.guild.id,
                user_id=member.id,
                activity=activity,
                started_at=self._iso(now),
                environment=environment,
                channel_id=channel_id,
            )
            await self.bot.db.update_staff_session(int(session["id"]), {
                "current_activity": activity,
                "current_environment": environment,
                "current_channel_id": channel_id,
                "segment_started_at": self._iso(now),
                "updated_at": self._iso(now),
            })
            await self.bot.db.log_staff_event(
                member.guild.id, member.id, "activity_changed", int(session["id"]),
                json.dumps({"from": old_activity, "to": activity}),
            )
            await self._dispatch_log(
                member.guild,
                "Atividade Alterada",
                f"{member.mention} trocou de atividade.",
                fields=[
                    ("Staff", member.mention, True),
                    ("De", old_activity, True),
                    ("Para", activity, True),
                    ("Ambiente", environment or "Fora da call", True),
                ],
            )
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        await self.refresh_panel(member.guild)
        await self.refresh_admin_panel(member.guild)
        return session or {}

    # ── Integração com voz ────────────────────────────────────────────────────

    async def handle_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot or member.guild.id != self.bot.server_map.guild_id():
            return
        if before.channel and after.channel and before.channel.id == after.channel.id:
            return
        before_rule = await self._get_channel_rule_type(member.guild.id, before.channel.id) if before.channel else None
        after_rule = await self._get_channel_rule_type(member.guild.id, after.channel.id) if after.channel else None
        before_valid = before_rule in ("work", "neutral")
        after_valid = after_rule in ("work", "neutral")
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        if session is None:
            if not await self.is_staff_member(member):
                return
            if after_valid:
                await self.send_voice_without_session_alert(member, after.channel)
            return
        if after_rule == "invalid" and session["status"] == "active":
            await self.pause_session(member, reason="Entrou em canal que nao conta como trabalho.")
            await self.send_afk_auto_paused_alert(member, after.channel)
            return
        if session["status"] == "paused" and after_valid:
            await self.send_paused_in_valid_voice_alert(member, after.channel)
            return
        if session["status"] == "active" and before_valid and not after_valid:
            await self.send_left_voice_active_alert(member)
        now = self._utcnow()
        environment, channel_id = self._get_member_environment(member)
        rule_type = await self._get_channel_rule_type(member.guild.id, channel_id) if channel_id else None
        if rule_type == "invalid":
            if session["status"] == "active":
                await self.pause_session(member, reason="Entrou em canal AFK/inválido automaticamente.")
            return
        if environment != session.get("current_environment") or channel_id != session.get("current_channel_id"):
            await self.bot.db.update_staff_session(int(session["id"]), {
                "current_environment": environment,
                "current_channel_id": channel_id,
                "updated_at": self._iso(now),
            })
            await self.bot.db.log_staff_event(
                member.guild.id, member.id, "environment_changed", int(session["id"]),
                json.dumps({"environment": environment, "channel_id": channel_id}),
            )
            await self._dispatch_log(
                member.guild,
                "Ambiente Alterado",
                f"{member.mention} mudou de canal durante o expediente.",
                fields=[
                    ("De", str(session.get("current_environment") or "Fora da call"), True),
                    ("Para", environment or "Fora da call", True),
                ],
            )
            await self.refresh_panel(member.guild)

    async def handle_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot or after.guild.id != self.bot.server_map.guild_id():
            return
        was_staff = await self.is_staff_member(before)
        is_now_staff = await self.is_staff_member(after)
        if was_staff and not is_now_staff:
            session = await self.bot.db.get_staff_open_session(after.guild.id, after.id)
            if session:
                await self.end_session(
                    after,
                    reason="Cargo de staff removido durante o expediente.",
                    close_mode="system_role_removed",
                )

    # ── Check-in ─────────────────────────────────────────────────────────────

    async def _control_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        config = await self.get_runtime_config(guild.id)
        channel_id = config.get("control_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_or_update_alert(
        self,
        member: discord.Member,
        alert_type: str,
        *,
        title: str,
        description: str,
        view: discord.ui.View,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        channel = await self._control_channel(member.guild)
        if channel is None:
            await self._dispatch_log(
                member.guild,
                "Central de Ponto nao configurada",
                "Configure com `/ponto configurar_central canal:#canal` para receber alertas criticos.",
                color=self.bot.embeds.warning_color,
            )
            return
        now = self._utcnow()
        existing = await self.bot.db.get_active_staff_presence_alert(member.guild.id, member.id, alert_type)
        if existing and existing.get("ignored_until"):
            try:
                if self._parse_dt(existing["ignored_until"]) > now:
                    return
            except Exception:
                pass
        embed = self.bot.embeds.make(title=title, description=description, color=self.bot.embeds.warning_color)
        embed.timestamp = now
        message: discord.Message | None = None
        if existing and existing.get("message_id"):
            try:
                old_channel = member.guild.get_channel(int(existing.get("channel_id") or channel.id))
                if isinstance(old_channel, discord.TextChannel):
                    message = await old_channel.fetch_message(int(existing["message_id"]))
                    await message.edit(content=member.mention, embed=embed, view=view)
            except (discord.NotFound, discord.HTTPException):
                message = None
        if message is None:
            message = await channel.send(member.mention, embed=embed, view=view)
        alert_id = await self.bot.db.upsert_staff_presence_alert(
            member.guild.id,
            member.id,
            alert_type,
            channel.id,
            message.id,
            self._iso(now),
            json.dumps(metadata or {}),
        )
        await self.bot.db.add_staff_notification(
            member.guild.id, member.id, alert_type, self._iso(now), channel.id, message.id, metadata_json=json.dumps(metadata or {})
        )
        await self.bot.db.log_staff_event(member.guild.id, member.id, f"alert_{alert_type}_sent", None, json.dumps({"alert_id": alert_id}))
        await self.refresh_admin_panel(member.guild)

    async def send_voice_without_session_alert(self, member: discord.Member, channel: discord.abc.GuildChannel | None) -> None:
        config = await self.get_runtime_config(member.guild.id)
        if not int(config.get("auto_prompt_on_voice_join") or 1):
            return
        from app.core.staff_timeclock_views import VoiceWithoutSessionAlertView
        channel_name = getattr(channel, "name", "call valida")
        await self._send_or_update_alert(
            member,
            "voice_without_session",
            title="Ponto nao iniciado",
            description=f"{member.mention}, detectamos que voce entrou na call **{channel_name}** sem expediente ativo.\n\nVoce deseja iniciar seu expediente agora?",
            view=VoiceWithoutSessionAlertView(self.bot),
            metadata={"voice_channel_id": getattr(channel, "id", None), "voice_channel_name": channel_name},
        )

    async def send_left_voice_active_alert(self, member: discord.Member) -> None:
        from app.core.staff_timeclock_views import LeftVoiceActiveAlertView
        await self._send_or_update_alert(
            member,
            "left_voice_with_active_session",
            title="Voce saiu da call com expediente ativo",
            description=f"{member.mention}, voce saiu da call com expediente ativo.\n\nO que deseja fazer?",
            view=LeftVoiceActiveAlertView(self.bot),
        )

    async def send_afk_auto_paused_alert(self, member: discord.Member, channel: discord.abc.GuildChannel | None) -> None:
        from app.core.staff_timeclock_views import AfkAutoPausedAlertView
        await self._send_or_update_alert(
            member,
            "afk_with_active_session",
            title="Expediente pausado automaticamente",
            description=f"{member.mention}, seu expediente foi pausado porque voce entrou em um canal que nao conta como trabalho.",
            view=AfkAutoPausedAlertView(self.bot),
            metadata={"voice_channel_id": getattr(channel, "id", None), "voice_channel_name": getattr(channel, "name", None)},
        )

    async def send_paused_in_valid_voice_alert(self, member: discord.Member, channel: discord.abc.GuildChannel | None) -> None:
        from app.core.staff_timeclock_views import PausedInValidVoiceAlertView
        channel_name = getattr(channel, "name", "call valida")
        await self._send_or_update_alert(
            member,
            "paused_in_valid_voice",
            title="Expediente pausado em call valida",
            description=f"{member.mention}, voce entrou na call **{channel_name}**, mas seu expediente esta pausado.\n\nDeseja retomar?",
            view=PausedInValidVoiceAlertView(self.bot),
            metadata={"voice_channel_id": getattr(channel, "id", None), "voice_channel_name": channel_name},
        )

    async def resolve_alert(self, guild: discord.Guild, user_id: int, alert_type: str, status: str = "resolved") -> None:
        resolver = getattr(self.bot.db, "resolve_staff_presence_alert", None)
        if callable(resolver):
            await self._maybe_await(resolver(guild.id, user_id, alert_type, status))

    async def ignore_alert_for_now(self, member: discord.Member, alert_type: str) -> None:
        config = await self.get_runtime_config(member.guild.id)
        now = self._utcnow()
        ignored_until = now + timedelta(seconds=int(config["alert_cooldown_seconds"]))
        alert = await self.bot.db.get_active_staff_presence_alert(member.guild.id, member.id, alert_type)
        if alert:
            await self.bot.db.update_staff_presence_alert(int(alert["id"]), {
                "ignored_until": self._iso(ignored_until),
                "last_reminder_at": self._iso(now),
                "updated_at": self._iso(now),
            })
        await self.bot.db.log_staff_event(member.guild.id, member.id, "alert_ignored_temporarily", None, json.dumps({"alert_type": alert_type}))
        await self.refresh_admin_panel(member.guild)

    async def mark_not_working(self, member: discord.Member) -> None:
        await self.resolve_alert(member.guild, member.id, "voice_without_session", "ignored")
        await self.bot.db.log_staff_event(member.guild.id, member.id, "voice_without_session_not_working", None, None)
        await self.refresh_admin_panel(member.guild)

    async def set_external_work(self, member: discord.Member) -> None:
        now = self._utcnow()
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        if session is None or session["status"] != "active":
            raise RuntimeError("Nenhum expediente ativo encontrado.")
        await self.bot.db.update_staff_session(int(session["id"]), {
            "current_environment": "Trabalho externo",
            "current_channel_id": None,
            "updated_at": self._iso(now),
        })
        await self.bot.db.log_staff_event(member.guild.id, member.id, "external_work_confirmed", int(session["id"]), None)
        await self.resolve_alert(member.guild, member.id, "left_voice_with_active_session", "resolved")
        await self.refresh_panel(member.guild)
        await self.refresh_admin_panel(member.guild)

    async def _send_checkin(self, session: dict[str, Any], guild: discord.Guild) -> None:
        now = self._utcnow()
        config = await self.get_runtime_config(guild.id)
        timeout_seconds = int(config["checkin_timeout_seconds"])
        deadline = now + timedelta(seconds=timeout_seconds)
        checkin_id = await self.bot.db.create_staff_checkin(
            session_id=int(session["id"]),
            guild_id=int(session["guild_id"]),
            user_id=int(session["user_id"]),
            sent_at=self._iso(now),
            deadline_at=self._iso(deadline),
        )
        member = guild.get_member(int(session["user_id"]))
        if member is None:
            return
        await self.bot.db.update_staff_session(int(session["id"]), {
            "last_checkin_at": self._iso(now),
            "checkin_pending": 1,
            "updated_at": self._iso(now),
        })
        from app.core.staff_timeclock_views import StaffCheckinView  # lazy import to avoid circular
        view = StaffCheckinView(self.bot, int(session["id"]), checkin_id)
        embed = self.bot.embeds.make(
            title="Verificação de Expediente",
            description=(
                f"{member.mention}, você ainda está em expediente?\n\n"
                f"Atividade atual: **{session['current_activity']}**\n"
                f"Responda dentro de **5 minutos** ou o expediente será pausado automaticamente."
            ),
        )
        message: discord.Message | None = None
        control = await self._control_channel(guild)
        if isinstance(control, discord.TextChannel):
            message = await control.send(member.mention, embed=embed, view=view)
        elif int(config.get("use_dm_as_fallback") or 0) or control is None:
            try:
                message = await member.send(embed=embed, view=view)
            except discord.HTTPException:
                message = None
        if message:
            notifier = getattr(self.bot.db, "add_staff_notification", None)
            if callable(notifier):
                await self._maybe_await(
                    notifier(guild.id, member.id, "checkin_pending", self._iso(now), getattr(message.channel, "id", None), message.id)
                )
            upsert_alert = getattr(self.bot.db, "upsert_staff_presence_alert", None)
            if callable(upsert_alert):
                await self._maybe_await(
                    upsert_alert(
                        guild.id, member.id, "checkin_pending", getattr(message.channel, "id", None), message.id, self._iso(now),
                        json.dumps({"checkin_id": checkin_id, "session_id": session["id"]}),
                    )
                )
        await self.bot.db.log_staff_event(
            int(session["guild_id"]), int(session["user_id"]), "checkin_sent", int(session["id"]),
            json.dumps({"checkin_id": checkin_id}),
        )

    async def process_checkin_response(self, session_id: int, checkin_id: int, response: str, user_id: int, *, activity: str | None = None) -> str:
        session = await self.bot.db.get_staff_session(session_id)
        if session is None or session["status"] == "closed":
            return "Sessão não encontrada ou já encerrada."
        now = self._utcnow()
        status_map = {"continue": "continued", "pause": "paused", "end": "ended"}
        checkin_status = status_map.get(response, response)
        await self.bot.db.update_staff_checkin(checkin_id, checkin_status, self._iso(now), response)
        await self.bot.db.update_staff_session(session_id, {"checkin_pending": 0, "updated_at": self._iso(now)})
        guild = self.bot.get_guild(int(session["guild_id"]))
        # Busca o member via guild para garantir contexto correto (evita discord.User de DM)
        member = guild.get_member(int(session["user_id"])) if guild else None
        if response == "continue":
            await self.bot.db.log_staff_event(int(session["guild_id"]), int(session["user_id"]), "checkin_answered_continue", session_id, None)
            if guild:
                await self.resolve_alert(guild, int(session["user_id"]), "checkin_pending", "resolved")
            return "Continuando."
        if response == "activity":
            if member and activity:
                await self.change_activity(member, activity)
            if guild:
                await self.resolve_alert(guild, int(session["user_id"]), "checkin_pending", "resolved")
            return f"Atividade atual: **{activity or session['current_activity']}**."
        if response == "pause":
            if member:
                await self.pause_session(member, reason="Pausa solicitada no check-in.")
            if guild:
                await self.resolve_alert(guild, int(session["user_id"]), "checkin_pending", "resolved")
            return "Pausado."
        if response == "end":
            if member:
                await self.end_session(member, reason="Encerrado pelo check-in.", close_mode="checkin_end")
            if guild:
                await self.resolve_alert(guild, int(session["user_id"]), "checkin_pending", "resolved")
            return "Encerrado."
        return "Resposta registrada."

    async def _process_expired_checkins(self, guild: discord.Guild) -> None:
        now = self._utcnow()
        expired = await self.bot.db.get_expired_checkins(guild.id, self._iso(now))
        for checkin in expired:
            await self.bot.db.update_staff_checkin(int(checkin["id"]), "expired", None, None)
            session = await self.bot.db.get_staff_session(int(checkin["session_id"]))
            if session and session["status"] == "active":
                member = guild.get_member(int(session["user_id"]))
                if member:
                    await self.pause_session(member, reason="Check-in não respondido — pausado automaticamente.")
                else:
                    await self.bot.db.update_staff_session(int(session["id"]), {
                        "status": "pending",
                        "updated_at": self._iso(now),
                    })
            await self.bot.db.log_staff_event(
                int(checkin["guild_id"]), int(checkin["user_id"]),
                "checkin_expired", int(checkin["session_id"]), None,
            )

    async def _maybe_send_checkins(self, guild: discord.Guild) -> None:
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        now = self._utcnow()
        config = await self.get_runtime_config(guild.id)
        for session in sessions:
            if session["status"] != "active":
                continue
            if session.get("checkin_pending"):
                continue
            last = session.get("last_checkin_at") or session["started_at"]
            last_dt = self._parse_dt(last)
            channel_id = session.get("current_channel_id")
            rule_type = await self._get_channel_rule_type(guild.id, channel_id) if channel_id else None
            interval = int(config["checkin_voice_seconds"]) if rule_type in ("work", "neutral") else int(config["checkin_external_seconds"])
            elapsed = (now - last_dt).total_seconds()
            if elapsed >= interval:
                await self._send_checkin(session, guild)

    # ── Painel ────────────────────────────────────────────────────────────────

    async def publish_panel(self, guild: discord.Guild) -> discord.Message:
        channel_id = self.bot.server_map.staff_timeclock_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do painel de expediente não configurado ou não encontrado.")
        from app.core.staff_timeclock_views import StaffTimeclockPanelView
        embed = await self.build_panel_embed(guild)
        view = StaffTimeclockPanelView(self.bot)
        stored = await self.bot.db.get_staff_timeclock_panel(guild.id)
        if stored:
            try:
                msg = await channel.fetch_message(int(stored["message_id"]))
                await msg.edit(embed=embed, view=view)
                return msg
            except (discord.NotFound, discord.HTTPException):
                pass
        msg = await channel.send(embed=embed, view=view)
        await self.bot.db.save_staff_timeclock_panel(guild.id, channel.id, msg.id)
        return msg

    async def refresh_panel(self, guild: discord.Guild) -> None:
        stored = await self.bot.db.get_staff_timeclock_panel(guild.id)
        if not stored:
            return
        channel = guild.get_channel(int(stored["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        from app.core.staff_timeclock_views import StaffTimeclockPanelView
        try:
            msg = await channel.fetch_message(int(stored["message_id"]))
            await msg.edit(embed=await self.build_panel_embed(guild), view=StaffTimeclockPanelView(self.bot))
        except (discord.NotFound, discord.HTTPException):
            await self.publish_panel(guild)

    async def build_panel_embed(self, guild: discord.Guild) -> discord.Embed:
        now = self._utcnow()
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        active = [s for s in sessions if s["status"] == "active"]
        paused = [s for s in sessions if s["status"] == "paused"]
        pending = [s for s in sessions if s["status"] == "pending"]
        embed = self.bot.embeds.make(
            title="Painel de Expediente da Staff",
            description="Controle manual de jornada de trabalho validada por atividade.",
        )
        embed.add_field(name="Em Expediente", value=str(len(active)), inline=True)
        embed.add_field(name="Pausados", value=str(len(paused)), inline=True)
        embed.add_field(name="Pendentes", value=str(len(pending)), inline=True)
        if active:
            lines = []
            for s in active[:10]:
                dur = self._format_duration(self._live_valid_seconds(s))
                env = s.get("current_environment") or "Fora da call"
                lines.append(f"<@{s['user_id']}> | `{s['current_activity']}` | {env} | `{dur}`")
            embed.add_field(name="Em Expediente Agora", value="\n".join(lines), inline=False)
        if paused:
            lines = [f"<@{s['user_id']}> | pausado há `{self._format_duration(self._live_paused_seconds(s))}`" for s in paused[:8]]
            embed.add_field(name="Pausados", value="\n".join(lines), inline=False)
        if pending:
            lines = [f"<@{s['user_id']}> | pendente de validação" for s in pending[:8]]
            embed.add_field(name="Pendentes de Validação", value="\n".join(lines), inline=False)
        embed.add_field(
            name="Ações Disponíveis",
            value="Use os botões abaixo ou os comandos `/ponto` para gerenciar seu expediente.",
            inline=False,
        )
        embed.set_footer(text=f"Atualizado em {self._format_dt(now)}")
        embed.timestamp = now
        return embed

    # ── Relatórios ────────────────────────────────────────────────────────────

    async def get_member_period_stats(
        self,
        guild_id: int,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> PeriodStats:
        stats = PeriodStats()
        now = self._utcnow()
        segments = await self.bot.db.get_staff_segments_in_range(
            guild_id, self._iso(start_at), self._iso(end_at), user_id=user_id
        )
        for seg in segments:
            # Pular segmentos ainda abertos — contabilizados via sessão ativa abaixo
            # para evitar contagem dupla.
            if not seg["ended_at"]:
                continue
            seg_start = self._parse_dt(seg["started_at"])
            seg_end = self._parse_dt(seg["ended_at"])
            overlap = self._overlap_seconds(seg_start, seg_end, start_at, end_at)
            if overlap <= 0:
                continue
            activity = str(seg["activity"])
            stats.by_activity[activity] = stats.by_activity.get(activity, 0) + overlap
            if str(seg.get("segment_status", "valid")) == "valid":
                stats.valid_seconds += overlap
        # Segmento ativo atual (não fechado ainda)
        open_session = await self.bot.db.get_staff_open_session(guild_id, user_id)
        if open_session and open_session["status"] == "active" and open_session.get("segment_started_at"):
            seg_start = self._parse_dt(open_session["segment_started_at"])
            effective_end = min(now, end_at)
            overlap = self._overlap_seconds(seg_start, effective_end, start_at, end_at)
            if overlap > 0:
                activity = str(open_session["current_activity"])
                stats.by_activity[activity] = stats.by_activity.get(activity, 0) + overlap
                stats.valid_seconds += overlap
        sessions = await self.bot.db.get_staff_sessions_in_range(
            guild_id, self._iso(start_at), self._iso(end_at), user_id=user_id
        )
        stats.session_count = len(sessions)
        adjustments = await self.bot.db.get_staff_adjustments(guild_id, user_id)
        for adj in adjustments:
            adj_dt = self._parse_dt(adj["created_at"])
            if start_at <= adj_dt < end_at:
                stats.adjustment_seconds += int(adj["adjustment_seconds"])
        return stats

    async def describe_member_status(self, member: discord.Member) -> TimeclockStatus:
        session = await self.bot.db.get_staff_open_session(member.guild.id, member.id)
        if session is None:
            sessions_today = await self.bot.db.get_staff_sessions_in_range(
                member.guild.id,
                self._iso(self._start_of_day(self._utcnow())),
                self._iso(self._utcnow()),
                user_id=member.id,
            )
            count = len(sessions_today)
            detail = f"Nenhum expediente aberto. {count} sessão(ões) hoje." if count else "Nenhum expediente registrado hoje."
            return TimeclockStatus(False, "closed", detail, None)
        status_label = STATUS_LABELS.get(str(session["status"]), session["status"])
        env = session.get("current_environment") or "Fora da call"
        activity = str(session["current_activity"])
        live_valid = self._live_valid_seconds(session)
        started = self._format_dt(self._parse_dt(session["started_at"]))
        summary = (
            f"Status: **{status_label}**\n"
            f"Atividade: **{activity}**\n"
            f"Ambiente: **{env}**\n"
            f"Início: {started}\n"
            f"Tempo validado: **{self._format_duration(live_valid)}**"
        )
        return TimeclockStatus(True, str(session["status"]), summary, dict(session))

    async def build_member_hours_embed(self, guild: discord.Guild, member: discord.Member) -> discord.Embed:
        now = self._utcnow()
        today_stats = await self.get_member_period_stats(guild.id, member.id, self._start_of_day(now), now)
        week_stats = await self.get_member_period_stats(guild.id, member.id, self._start_of_week(now), now)
        month_stats = await self.get_member_period_stats(guild.id, member.id, self._start_of_month(now), now)
        status = await self.describe_member_status(member)
        embed = self.bot.embeds.make(
            title=f"Horas de {member.display_name}",
            description=f"{member.mention}\n\n{status.summary}",
        )
        embed.add_field(name="Hoje", value=self._format_duration(today_stats.valid_seconds), inline=True)
        embed.add_field(name="Semana", value=self._format_duration(week_stats.valid_seconds), inline=True)
        embed.add_field(name="Mês", value=self._format_duration(month_stats.valid_seconds), inline=True)
        if week_stats.by_activity:
            lines = [
                f"**{act}:** {self._format_duration(sec)}"
                for act, sec in sorted(week_stats.by_activity.items(), key=lambda x: x[1], reverse=True)
                if sec > 0
            ]
            embed.add_field(name="Por Atividade (Semana)", value="\n".join(lines[:10]) or "Sem dados", inline=False)
        if week_stats.adjustment_seconds:
            sign = "+" if week_stats.adjustment_seconds > 0 else ""
            embed.add_field(name="Ajustes Manuais (Semana)", value=f"{sign}{self._format_duration(abs(week_stats.adjustment_seconds))}", inline=True)
        embed.set_footer(text=f"Gerado em {self._format_dt(now)}")
        return embed

    async def build_general_report_embed(self, guild: discord.Guild, period: str) -> discord.Embed:
        now = self._utcnow()
        start_at, label = self._period_bounds_labeled(period, now)
        embed = self.bot.embeds.make(
            title=f"Relatório Geral da Staff — {label}",
            description="Visão consolidada do expediente de toda a equipe.",
        )
        members = [m for m in guild.members if not m.bot]
        staff_data: list[tuple[discord.Member, PeriodStats]] = []
        for m in members:
            if await self.is_staff_member(m):
                stats = await self.get_member_period_stats(guild.id, m.id, start_at, now)
                if stats.valid_seconds > 0 or stats.session_count > 0:
                    staff_data.append((m, stats))
        staff_data.sort(key=lambda x: x[1].valid_seconds, reverse=True)
        total_seconds = sum(s.valid_seconds for _, s in staff_data)
        embed.add_field(name="Total Geral", value=self._format_duration(total_seconds), inline=True)
        embed.add_field(name="Staff com horas", value=str(len(staff_data)), inline=True)
        lines = [
            f"{idx}. {m.mention} — `{self._format_duration(s.valid_seconds)}`"
            for idx, (m, s) in enumerate(staff_data[:15], start=1)
        ]
        embed.add_field(name="Ranking", value="\n".join(lines) or "Sem dados no período.", inline=False)
        all_activity: dict[str, int] = {}
        for _, s in staff_data:
            for act, sec in s.by_activity.items():
                all_activity[act] = all_activity.get(act, 0) + sec
        if all_activity:
            act_lines = [
                f"**{act}:** {self._format_duration(sec)}"
                for act, sec in sorted(all_activity.items(), key=lambda x: x[1], reverse=True)[:10]
                if sec > 0
            ]
            embed.add_field(name="Por Atividade", value="\n".join(act_lines), inline=False)
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        active_now = [s for s in sessions if s["status"] == "active"]
        if active_now:
            now_lines = [f"<@{s['user_id']}> | `{s['current_activity']}`" for s in active_now[:10]]
            embed.add_field(name="Em Expediente Agora", value="\n".join(now_lines), inline=False)
        embed.set_footer(text=f"Gerado em {self._format_dt(now)}")
        return embed

    async def build_ranking_embed(self, guild: discord.Guild, period: str) -> discord.Embed:
        now = self._utcnow()
        start_at, label = self._period_bounds_labeled(period, now)
        ranking: list[tuple[discord.Member, int]] = []
        for m in guild.members:
            if m.bot:
                continue
            if not await self.is_staff_member(m):
                continue
            stats = await self.get_member_period_stats(guild.id, m.id, start_at, now)
            if stats.valid_seconds > 0:
                ranking.append((m, stats.valid_seconds))
        ranking.sort(key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        lines = [
            f"{medals[i] if i < 3 else f'{i+1}.'} {m.mention} — `{self._format_duration(sec)}`"
            for i, (m, sec) in enumerate(ranking[:15])
        ]
        embed = self.bot.embeds.make(
            title=f"Ranking de Horas — {label}",
            description="\n".join(lines) or "Nenhum dado disponível para o período.",
        )
        embed.set_footer(text=f"Gerado em {self._format_dt(now)}")
        return embed

    async def build_status_embed(self, guild: discord.Guild) -> discord.Embed:
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        active = [s for s in sessions if s["status"] == "active"]
        paused = [s for s in sessions if s["status"] == "paused"]
        pending = [s for s in sessions if s["status"] == "pending"]
        embed = self.bot.embeds.make(title="Status da Staff Agora")
        if active:
            embed.add_field(
                name=f"Em Expediente ({len(active)})",
                value="\n".join(f"<@{s['user_id']}> | `{s['current_activity']}` | `{self._format_duration(self._live_valid_seconds(s))}`" for s in active[:12]),
                inline=False,
            )
        if paused:
            embed.add_field(
                name=f"Pausados ({len(paused)})",
                value="\n".join(f"<@{s['user_id']}>" for s in paused[:10]),
                inline=False,
            )
        if pending:
            embed.add_field(
                name=f"Pendentes ({len(pending)})",
                value="\n".join(f"<@{s['user_id']}>" for s in pending[:10]),
                inline=False,
            )
        if not sessions:
            embed.description = "Nenhum membro da staff em expediente no momento."
        embed.set_footer(text=f"Atualizado em {self._format_dt(self._utcnow())}")
        return embed

    async def publish_admin_panel(self, guild: discord.Guild, channel: discord.TextChannel | None = None) -> discord.Message:
        target = channel or await self._control_channel(guild)
        if not isinstance(target, discord.TextChannel):
            raise RuntimeError("Central de Ponto nao configurada. Use `/ponto configurar_central canal:#canal`.")
        from app.core.staff_timeclock_views import StaffTimeclockAdminPanelView
        embed = await self.build_admin_panel_embed(guild)
        view = StaffTimeclockAdminPanelView(self.bot)
        stored = await self.bot.db.get_staff_timeclock_admin_panel(guild.id)
        if stored and int(stored["channel_id"]) == target.id:
            try:
                msg = await target.fetch_message(int(stored["message_id"]))
                await msg.edit(embed=embed, view=view)
                return msg
            except (discord.NotFound, discord.HTTPException):
                pass
        msg = await target.send(embed=embed, view=view)
        await self.bot.db.save_staff_timeclock_admin_panel(guild.id, target.id, msg.id)
        return msg

    async def refresh_admin_panel(self, guild: discord.Guild) -> None:
        getter = getattr(self.bot.db, "get_staff_timeclock_admin_panel", None)
        stored = await self._maybe_await(getter(guild.id)) if callable(getter) else None
        if not isinstance(stored, dict):
            return
        if not stored:
            return
        channel = guild.get_channel(int(stored["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        from app.core.staff_timeclock_views import StaffTimeclockAdminPanelView
        try:
            msg = await channel.fetch_message(int(stored["message_id"]))
            await msg.edit(embed=await self.build_admin_panel_embed(guild), view=StaffTimeclockAdminPanelView(self.bot))
        except (discord.NotFound, discord.HTTPException):
            return

    async def build_admin_panel_embed(self, guild: discord.Guild) -> discord.Embed:
        now = self._utcnow()
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        active = [s for s in sessions if s["status"] == "active"]
        paused = [s for s in sessions if s["status"] == "paused"]
        pending = [s for s in sessions if s["status"] == "pending"]
        voice_alerts = await self.bot.db.list_active_staff_presence_alerts(guild.id, "voice_without_session")
        left_alerts = await self.bot.db.list_active_staff_presence_alerts(guild.id, "left_voice_with_active_session")
        checkin_alerts = await self.bot.db.list_active_staff_presence_alerts(guild.id, "checkin_pending")
        staff_members = [m for m in guild.members if not m.bot and await self.is_staff_member(m)]
        today = await self._total_staff_seconds(guild, self._start_of_day(now), now)
        week = await self._total_staff_seconds(guild, self._start_of_week(now), now)
        external = [s for s in active if str(s.get("current_environment") or "") == "Trabalho externo"]
        embed = self.bot.embeds.make(
            title="Central de Controle de Ponto",
            description="Visao geral da jornada da staff. Nada critico depende de DM.",
        )
        embed.add_field(name="Staffs configurados", value=str(len(staff_members)), inline=True)
        embed.add_field(name="Ativos", value=str(len(active)), inline=True)
        embed.add_field(name="Pausados", value=str(len(paused)), inline=True)
        embed.add_field(name="Pendentes", value=str(len(pending)), inline=True)
        embed.add_field(name="Call sem ponto", value=str(len(voice_alerts)), inline=True)
        embed.add_field(name="Trabalho externo", value=str(len(external)), inline=True)
        embed.add_field(name="Horas hoje", value=self._format_duration(today), inline=True)
        embed.add_field(name="Horas semana", value=self._format_duration(week), inline=True)
        embed.add_field(name="Check-ins pendentes", value=str(len(checkin_alerts)), inline=True)
        lines: list[str] = []
        for s in sessions[:12]:
            member = guild.get_member(int(s["user_id"]))
            name = member.display_name if member else f"<@{s['user_id']}>"
            env = s.get("current_environment") or "Fora da call"
            live = self._live_valid_seconds(s) if s["status"] == "active" else self._live_paused_seconds(s)
            lines.append(f"**{name}** | {STATUS_LABELS.get(str(s['status']), s['status'])} | {s['current_activity']} | {env} | `{self._format_duration(live)}`")
        for alert in voice_alerts[:6]:
            member = guild.get_member(int(alert["user_id"]))
            name = member.display_name if member else f"<@{alert['user_id']}>"
            started = self._parse_dt(alert["started_at"])
            lines.append(f"**{name}** | Em call sem ponto | `{self._format_duration(int((now - started).total_seconds()))}` | acao: lembrar")
        embed.add_field(name="Resumo por staff", value="\n".join(lines[:18]) or "Nenhum movimento agora.", inline=False)
        if left_alerts:
            embed.add_field(name="Saida de call com ponto aberto", value="\n".join(f"<@{a['user_id']}>" for a in left_alerts[:10]), inline=False)
        embed.set_footer(text=f"Ultima atualizacao: {self._format_dt(now)}")
        embed.timestamp = now
        return embed

    async def build_pending_review_embed(self, guild: discord.Guild) -> discord.Embed:
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        pending = [s for s in sessions if s["status"] == "pending"]
        lines = [
            f"ID `{s['id']}` | <@{s['user_id']}> | {s.get('current_environment') or 'Sem ambiente'}"
            for s in pending[:20]
        ]
        return self.bot.embeds.make(
            title="Pendencias de Ponto",
            description="\n".join(lines) or "Nenhuma pendencia no momento.",
            fields=[("Como revisar", "Use `/ponto revisar`, `/ponto aprovar_pendente` ou `/ponto reprovar_pendente`.", False)],
        )

    async def remind_member(self, guild: discord.Guild, target: discord.Member, admin: discord.Member | None = None) -> None:
        channel = target.voice.channel if target.voice else None
        await self.send_voice_without_session_alert(target, channel)
        if admin:
            await self.bot.db.add_staff_admin_action(guild.id, admin.id, target.id, "remind_member", "Lembrete manual")

    async def remind_all_voice_without_session(self, guild: discord.Guild, admin: discord.Member | None = None) -> int:
        count = 0
        for member in guild.members:
            if member.bot or not await self.is_staff_member(member):
                continue
            if await self.bot.db.get_staff_open_session(guild.id, member.id):
                continue
            channel = member.voice.channel if member.voice else None
            if not channel:
                continue
            rule = await self._get_channel_rule_type(guild.id, channel.id)
            if rule in ("work", "neutral"):
                await self.send_voice_without_session_alert(member, channel)
                count += 1
        if admin:
            await self.bot.db.add_staff_admin_action(guild.id, admin.id, None, "remind_all", f"{count} lembrete(s)")
        return count

    async def force_pause(self, guild: discord.Guild, target: discord.Member, admin: discord.Member, reason: str) -> None:
        await self.pause_session(target, reason=reason, actor=admin)
        await self.bot.db.add_staff_admin_action(guild.id, admin.id, target.id, "force_pause", reason)

    async def force_end(self, guild: discord.Guild, target: discord.Member, admin: discord.Member, reason: str) -> None:
        await self.end_session(target, actor=admin, reason=reason, close_mode="admin_forced")
        await self.bot.db.add_staff_admin_action(guild.id, admin.id, target.id, "force_end", reason)

    async def _total_staff_seconds(self, guild: discord.Guild, start_at: datetime, end_at: datetime) -> int:
        total = 0
        for member in guild.members:
            if member.bot or not await self.is_staff_member(member):
                continue
            stats = await self.get_member_period_stats(guild.id, member.id, start_at, end_at)
            total += stats.valid_seconds
        return total

    async def export_csv(self, guild: discord.Guild, period: str) -> discord.File:
        now = self._utcnow()
        start_at, label = self._period_bounds_labeled(period, now)
        buf = io.StringIO()
        buf.write("usuario_id,nome,total_valido,pausado,pendente,sessoes,por_atividade\n")
        for m in guild.members:
            if m.bot:
                continue
            if not await self.is_staff_member(m):
                continue
            stats = await self.get_member_period_stats(guild.id, m.id, start_at, now)
            if stats.valid_seconds == 0 and stats.session_count == 0:
                continue
            act_str = "|".join(f"{a}:{self._format_duration(s)}" for a, s in sorted(stats.by_activity.items(), key=lambda x: x[1], reverse=True) if s > 0)
            buf.write(
                f"{m.id},{m.display_name},{self._format_duration(stats.valid_seconds)},"
                f"{self._format_duration(stats.paused_seconds)},{self._format_duration(stats.pending_seconds)},"
                f"{stats.session_count},{act_str}\n"
            )
        buf.seek(0)
        filename = f"relatorio_staff_{period}_{now.strftime('%Y%m%d')}.csv"
        return discord.File(io.BytesIO(buf.read().encode("utf-8-sig")), filename=filename)

    # ── Administração ─────────────────────────────────────────────────────────

    async def admin_adjust(
        self,
        guild: discord.Guild,
        target: discord.Member,
        admin: discord.Member,
        seconds: int,
        reason: str,
        session_id: int | None = None,
    ) -> None:
        await self.bot.db.add_staff_adjustment(
            guild.id, target.id, admin.id, seconds, reason, session_id
        )
        sign = "+" if seconds > 0 else ""
        await self.bot.db.log_staff_event(
            guild.id, target.id, "manual_adjustment", session_id,
            json.dumps({"admin_id": admin.id, "seconds": seconds, "reason": reason}),
        )
        await self._dispatch_log(
            guild,
            "Ajuste Manual de Horas",
            f"Admin {admin.mention} ajustou horas de {target.mention}.",
            fields=[
                ("Staff", target.mention, True),
                ("Admin", admin.mention, True),
                ("Ajuste", f"{sign}{self._format_duration(abs(seconds))}", True),
                ("Motivo", reason, False),
            ],
            color=self.bot.embeds.warning_color if seconds < 0 else self.bot.embeds.success_color,
        )

    async def review_pending_session(
        self,
        guild: discord.Guild,
        session_id: int,
        admin: discord.Member,
        action: str,
        note: str | None = None,
    ) -> str:
        session = await self.bot.db.get_staff_session(session_id)
        if session is None:
            raise RuntimeError("Sessão não encontrada.")
        if session["status"] != "pending":
            raise RuntimeError("A sessão não está com status pendente.")
        now = self._utcnow()
        if action == "approve":
            await self.bot.db.update_staff_session(session_id, {"status": "active", "updated_at": self._iso(now)})
            await self.bot.db.log_staff_event(
                int(session["guild_id"]), int(session["user_id"]), "pending_approved", session_id,
                json.dumps({"admin_id": admin.id, "note": note}),
            )
            await self._dispatch_log(guild, "Sessão Pendente Aprovada", f"Admin {admin.mention} aprovou sessão pendente de <@{session['user_id']}>.")
            return "Sessão aprovada e retomada como ativa."
        if action == "invalidate":
            member = guild.get_member(int(session["user_id"]))
            if member:
                await self.end_session(member, actor=admin, reason=note or "Invalidado pela revisão administrativa.", close_mode="admin_invalidated")
            else:
                await self.bot.db.update_staff_session(session_id, {
                    "status": "closed",
                    "ended_at": self._iso(now),
                    "close_mode": "admin_invalidated",
                    "close_reason": note or "Invalidado pela revisão administrativa.",
                    "ended_by_user_id": admin.id,
                    "updated_at": self._iso(now),
                })
            await self._dispatch_log(guild, "Sessão Pendente Invalidada", f"Admin {admin.mention} invalidou sessão de <@{session['user_id']}>.")
            return "Sessão invalidada e encerrada."
        raise RuntimeError("Ação inválida. Use 'approve' ou 'invalidate'.")

    # ── Bootstrap/Reconciliação ───────────────────────────────────────────────

    async def bootstrap(self) -> None:
        if self._restored:
            return
        self._restored = True
        self._ensure_tasks()
        guild = self.bot.get_guild(self.bot.server_map.guild_id())
        if guild is None:
            return
        now = self._utcnow()
        sessions = await self.bot.db.list_open_staff_sessions(guild.id)
        for session in sessions:
            member = guild.get_member(int(session["user_id"]))
            if member is None or not await self.is_staff_member(member):
                await self.bot.db.update_staff_session(int(session["id"]), {
                    "status": "pending",
                    "updated_at": self._iso(now),
                })
                await self.bot.db.log_staff_event(
                    int(session["guild_id"]), int(session["user_id"]),
                    "reconcile_member_absent", int(session["id"]), None,
                )
                continue
            if session["status"] == "active":
                session_start = self._parse_dt(session["started_at"])
                if (now - session_start).total_seconds() > MAX_SESSION_HOURS * 3600:
                    await self.bot.db.update_staff_session(int(session["id"]), {
                        "status": "pending",
                        "updated_at": self._iso(now),
                    })
                    await self.bot.db.log_staff_event(
                        int(session["guild_id"]), int(session["user_id"]),
                        "reconcile_session_too_long", int(session["id"]), None,
                    )
        await self.refresh_panel(guild)

    def _ensure_tasks(self) -> None:
        if not self._maintenance_task or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop(), name="staff-timeclock-maintenance")

    async def _maintenance_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(30)
                guild = self.bot.get_guild(self.bot.server_map.guild_id())
                if guild:
                    await self._process_expired_checkins(guild)
                    await self._maybe_send_checkins(guild)
                    await self._process_voice_alert_timeouts(guild)
                    await self.refresh_panel(guild)
                    await self.refresh_admin_panel(guild)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.bot.log.exception("Falha no loop de manutenção do timeclock da staff.")

    # ── Relatório de encerramento ─────────────────────────────────────────────

    async def _process_voice_alert_timeouts(self, guild: discord.Guild) -> None:
        now = self._utcnow()
        config = await self.get_runtime_config(guild.id)
        if not int(config.get("auto_pause_on_voice_leave") or 1):
            return
        alerts = await self.bot.db.list_active_staff_presence_alerts(guild.id, "left_voice_with_active_session")
        for alert in alerts:
            started = self._parse_dt(alert["started_at"])
            if (now - started).total_seconds() < int(config["auto_pause_delay_seconds"]):
                continue
            member = guild.get_member(int(alert["user_id"]))
            session = await self.bot.db.get_staff_open_session(guild.id, int(alert["user_id"]))
            if member and session and session["status"] == "active":
                await self.pause_session(member, reason="Expediente pausado automaticamente por saida de call sem resposta.")
                control = await self._control_channel(guild)
                if isinstance(control, discord.TextChannel):
                    await control.send(
                        member.mention,
                        embed=self.bot.embeds.make(
                            title="Expediente pausado automaticamente",
                            description=f"{member.mention}, seu expediente foi pausado porque voce saiu da call e nao respondeu ao aviso.",
                            color=self.bot.embeds.warning_color,
                        ),
                    )
            await self.resolve_alert(guild, int(alert["user_id"]), "left_voice_with_active_session", "expired")

    async def _send_session_report(self, guild: discord.Guild, session: dict[str, Any]) -> None:
        channel_id = self.bot.server_map.staff_timeclock_log_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        segments = await self.bot.db.get_session_segments(int(session["id"]))
        by_activity: dict[str, int] = {}
        for seg in segments:
            if seg["ended_at"] and seg["duration_seconds"]:
                act = str(seg["activity"])
                by_activity[act] = by_activity.get(act, 0) + int(seg["duration_seconds"])
        total_valid = int(session["total_valid_seconds"]) or sum(by_activity.values())
        started = self._format_dt(self._parse_dt(session["started_at"]))
        ended = self._format_dt(self._parse_dt(session["ended_at"])) if session.get("ended_at") else "agora"
        act_lines = "\n".join(
            f"— **{act}:** {self._format_duration(sec)}"
            for act, sec in sorted(by_activity.items(), key=lambda x: x[1], reverse=True)
            if sec > 0
        ) or "— Sem segmentos registrados."
        embed = self.bot.embeds.make(
            title="Relatório de Encerramento de Expediente",
            description=f"<@{session['user_id']}>",
            fields=[
                ("Início", started, True),
                ("Fim", ended, True),
                ("Total Validado", self._format_duration(total_valid), True),
                ("Modo de Encerramento", str(session.get("close_mode") or "manual").replace("_", " ").title(), True),
                ("Por Atividade", act_lines, False),
                ("Motivo", str(session.get("close_reason") or "Nenhum"), False),
            ],
        )
        await channel.send(embed=embed)

    async def _dispatch_close_log(self, guild: discord.Guild, member: discord.Member, session: dict[str, Any]) -> None:
        segments = await self.bot.db.get_session_segments(int(session["id"]))
        by_activity: dict[str, int] = {}
        for seg in segments:
            if seg["ended_at"] and seg["duration_seconds"]:
                act = str(seg["activity"])
                by_activity[act] = by_activity.get(act, 0) + int(seg["duration_seconds"])
        total = sum(by_activity.values())
        act_str = " | ".join(f"{a}: {self._format_duration(s)}" for a, s in sorted(by_activity.items(), key=lambda x: x[1], reverse=True)[:5] if s > 0) or "Sem dados"
        await self._dispatch_log(
            guild,
            "Expediente Encerrado",
            f"{member.mention} encerrou o expediente.",
            fields=[
                ("Staff", member.mention, True),
                ("Total Validado", self._format_duration(total), True),
                ("Modo", str(session.get("close_mode") or "manual").replace("_", " ").title(), True),
                ("Atividades", act_str, False),
            ],
            color=self.bot.embeds.default_color,
        )

    # ── Helpers de voz ────────────────────────────────────────────────────────

    def _get_member_environment(self, member: discord.Member) -> tuple[str | None, int | None]:
        if not member.voice or not member.voice.channel:
            return None, None
        channel = member.voice.channel
        return channel.name, channel.id

    async def _get_channel_rule_type(self, guild_id: int, channel_id: int | None) -> str | None:
        if channel_id is None:
            return None
        rule = await self.bot.db.get_channel_rule(guild_id, channel_id)
        if rule:
            return str(rule["rule_type"])
        groups = self.bot.server_map.voice_point_channel_groups()
        for group_name, ids in groups.items():
            if channel_id in ids:
                return "work"
        if channel_id in self.bot.server_map.voice_point_valid_channel_ids():
            return "neutral"
        return None

    # ── Helpers internos ─────────────────────────────────────────────────────

    async def _close_current_segment(self, session: dict[str, Any], now: datetime) -> None:
        seg_start_raw = session.get("segment_started_at")
        if not seg_start_raw:
            return
        seg_start = self._parse_dt(seg_start_raw)
        duration = max(0, int((now - seg_start).total_seconds()))
        segments = await self.bot.db.get_session_segments(int(session["id"]))
        open_seg = next((s for s in reversed(segments) if not s["ended_at"]), None)
        if open_seg:
            await self.bot.db.close_staff_segment(int(open_seg["id"]), self._iso(now), duration)
        await self.bot.db.update_staff_session(int(session["id"]), {
            "total_valid_seconds": int(session["total_valid_seconds"]) + duration,
            "segment_started_at": None,
            "updated_at": self._iso(now),
        })

    def _live_valid_seconds(self, session: dict[str, Any]) -> int:
        total = int(session["total_valid_seconds"])
        if session["status"] == "active" and session.get("segment_started_at"):
            total += max(0, int((self._utcnow() - self._parse_dt(session["segment_started_at"])).total_seconds()))
        return total

    def _live_paused_seconds(self, session: dict[str, Any]) -> int:
        total = int(session["total_paused_seconds"])
        if session["status"] in ("paused", "pending") and session.get("pause_started_at"):
            total += max(0, int((self._utcnow() - self._parse_dt(session["pause_started_at"])).total_seconds()))
        return total

    async def _dispatch_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        *,
        fields: list[tuple[str, str, bool]] | None = None,
        color: int | None = None,
    ) -> None:
        config = await self.get_runtime_config(guild.id)
        channel_id = config.get("logs_channel_id") or self.bot.server_map.staff_timeclock_log_channel_id()
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.bot.embeds.make(
            title=title,
            description=description,
            color=color or self.bot.embeds.default_color,
            fields=fields,
        )
        embed.timestamp = self._utcnow()
        await channel.send(embed=embed)

    def _lock_for(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _call_server_map(self, name: str, default: Any) -> Any:
        func = getattr(self.bot.server_map, name, None)
        if callable(func):
            value = func()
            if "unittest.mock" not in type(value).__module__:
                return value
        return default

    def _period_bounds_labeled(self, period: str, now: datetime) -> tuple[datetime, str]:
        key = str(period).strip().lower()
        if key in {"hoje", "today"}:
            return self._start_of_day(now), "Hoje"
        if key in {"ontem", "yesterday"}:
            start = self._start_of_day(now) - timedelta(days=1)
            return start, "Ontem"
        if key in {"semana", "semanal", "week", "weekly"}:
            return self._start_of_week(now), "Semana Atual"
        if key in {"semana_passada", "last_week"}:
            this_week = self._start_of_week(now)
            return this_week - timedelta(weeks=1), "Semana Passada"
        if key in {"mes", "mensal", "month", "monthly"}:
            return self._start_of_month(now), "Mês Atual"
        if key in {"mes_passado", "last_month"}:
            first = self._start_of_month(now)
            return self._start_of_month(first - timedelta(days=1)), "Mês Passado"
        raise RuntimeError("Período inválido. Use: hoje, semana, mes, semana_passada, mes_passado.")

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_dt(raw: Any) -> datetime:
        return datetime.fromisoformat(str(raw)).astimezone(UTC)

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.astimezone(BRASILIA_TZ).strftime("%d/%m/%Y %H:%M (Brasília)")

    @staticmethod
    def _format_duration(seconds: int) -> str:
        total = max(0, int(seconds))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}h {m:02d}m {s:02d}s"

    @staticmethod
    def _start_of_day(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _start_of_week(value: datetime) -> datetime:
        start = StaffTimeclockService._start_of_day(value)
        return start - timedelta(days=start.weekday())

    @staticmethod
    def _start_of_month(value: datetime) -> datetime:
        start = StaffTimeclockService._start_of_day(value)
        return start.replace(day=1)

    @staticmethod
    def _overlap_seconds(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> int:
        start = max(start_a, start_b)
        end = min(end_a, end_b)
        return max(0, int((end - start).total_seconds()))
