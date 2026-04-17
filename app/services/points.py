from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import discord


GROUP_TO_COLUMN = {
    "attendance_channels": "attendance_seconds",
    "meeting_channels": "meeting_seconds",
    "leadership_channels": "leadership_seconds",
    "development_channels": "development_seconds",
}
GROUP_TO_LABEL = {
    "attendance_channels": "Atendimento",
    "meeting_channels": "Reunião",
    "leadership_channels": "Liderança",
    "development_channels": "Desenvolvimento",
    "grace": "Tolerância",
}
try:
    BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    BRASILIA_TZ = timezone(timedelta(hours=-3))


@dataclass(slots=True)
class VoicePointStatus:
    active: bool
    summary: str
    session: dict[str, Any] | None


@dataclass(slots=True)
class SessionAudit:
    session: dict[str, Any]
    status: str
    detail: str


class PointService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}
        self._grace_tasks: dict[int, asyncio.Task[None]] = {}
        self._restored = False
        self._maintenance_task: asyncio.Task[None] | None = None

    async def apply_reward_roles(self, member: discord.Member, total: int) -> None:
        reward_roles = self.bot.server_map.point_roles()
        for threshold_text, role_id in reward_roles.items():
            threshold = int(threshold_text)
            role = member.guild.get_role(role_id)
            if not role:
                continue
            if total >= threshold and role not in member.roles:
                await member.add_roles(role, reason="Marco de ponto atingido em Drakoria")

    async def leaderboard_text(self, guild: discord.Guild) -> str:
        rows = await self.bot.db.top_points(guild.id, limit=10)
        if not rows:
            return "Nenhum nome foi registrado no quadro de honra ainda."
        lines = []
        for position, row in enumerate(rows, start=1):
            member = guild.get_member(row["user_id"])
            name = member.mention if member else f"<@{row['user_id']}>"
            lines.append(f"**{position}.** {name} - `{row['total']}` pontos")
        return "\n".join(lines)

    def enabled(self) -> bool:
        return self.bot.server_map.voice_points_enabled()

    def is_authorized_member(self, member: discord.Member) -> bool:
        allowed_role_ids = set(self.bot.server_map.voice_point_allowed_role_ids())
        return bool(allowed_role_ids.intersection(role.id for role in member.roles))

    def is_valid_voice_channel(self, channel: discord.abc.GuildChannel | None) -> bool:
        return bool(channel and self.bot.server_map.is_valid_voice_point_channel(channel.id))

    def current_valid_voice_channel(self, member: discord.Member) -> discord.VoiceChannel | discord.StageChannel | None:
        channel = member.voice.channel if member.voice else None
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) and self.is_valid_voice_channel(channel):
            return channel
        return None

    def channel_group(self, channel_id: int | None) -> str | None:
        if channel_id is None:
            return None
        overrides = self.bot.server_map.voice_point_group_override_by_channel_id()
        if int(channel_id) in overrides:
            return overrides[int(channel_id)]
        return self.bot.server_map.voice_point_channel_group(channel_id)

    def _resolve_runtime_group(self, session: dict[str, Any]) -> str | None:
        active_channel_id = int(session.get("active_channel_id") or 0)
        if active_channel_id:
            by_channel = self.channel_group(active_channel_id)
            if by_channel:
                return by_channel
        stored = session.get("active_channel_group")
        return str(stored) if stored else None

    async def bootstrap_runtime(self) -> None:
        if self._restored or not self.enabled() or not self.bot.is_ready():
            return
        self._restored = True
        self._ensure_maintenance_task()
        guild = self.bot.get_guild(self.bot.server_map.guild_id())
        if guild is None:
            return
        for session in await self.bot.db.list_active_voice_point_sessions(guild.id):
            member = guild.get_member(int(session["user_id"]))
            if member is None or not self.is_authorized_member(member):
                await self._close_session_by_row(
                    session,
                    close_mode="system_role_removed",
                    close_reason="Sessão encerrada na restauração por membro ausente/sem cargo.",
                    ended_by_user_id=self.bot.user.id if self.bot.user else None,
                )
                continue
            current = self.current_valid_voice_channel(member)
            if session["grace_started_at"]:
                deadline = self._parse_dt(session["grace_deadline_at"])
                if self._utcnow() >= deadline:
                    await self._close_session_by_row(
                        session,
                        close_mode="automatic",
                        close_reason="Tolerância expirada durante reinício.",
                        ended_by_user_id=self.bot.user.id if self.bot.user else None,
                    )
                else:
                    self._schedule_grace_timeout(session, deadline)
                continue
            if current is None:
                await self._start_grace(session, reason="Ausência detectada na restauração.")
            elif int(session.get("active_channel_id") or 0) != current.id:
                await self._move_session(session, current, reason="Reconciliação pós-reinício.", log_event="Canal Reconciliado")
        await self.refresh_panel_message(guild)
        await self.refresh_management_dashboard(guild)

    async def handle_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if not self.enabled() or member.bot or member.guild.id != self.bot.server_map.guild_id():
            return
        if before.channel and after.channel and before.channel.id == after.channel.id:
            return
        async with self._lock_for(member.id):
            session = await self.bot.db.get_active_voice_point_session(member.guild.id, member.id)
            current_channel = self.current_valid_voice_channel(member)
            if not self.is_authorized_member(member):
                if session:
                    await self._close_session_by_row(
                        session,
                        close_mode="system_role_removed",
                        close_reason="Sessão encerrada porque o membro perdeu cargo autorizado.",
                        ended_by_user_id=self.bot.user.id if self.bot.user else None,
                    )
                return
            if current_channel:
                if session is None:
                    await self._start_session(member, current_channel, start_mode="automatic", started_by_user_id=None)
                    return
                if session["grace_started_at"]:
                    await self._return_from_grace(session, current_channel)
                    return
                if int(session.get("active_channel_id") or 0) != current_channel.id:
                    await self._move_session(session, current_channel, reason="Transferência entre calls válidas.")
                return
            if session and not session["grace_started_at"]:
                await self._start_grace(session, reason="Saída de todas as calls válidas.")

    async def handle_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self.enabled() or after.bot or after.guild.id != self.bot.server_map.guild_id():
            return
        if self.is_authorized_member(before) and not self.is_authorized_member(after):
            async with self._lock_for(after.id):
                session = await self.bot.db.get_active_voice_point_session(after.guild.id, after.id)
                if session:
                    await self._close_session_by_row(
                        session,
                        close_mode="system_role_removed",
                        close_reason="Sessão encerrada porque o cargo autorizado foi removido durante o expediente.",
                        ended_by_user_id=self.bot.user.id if self.bot.user else None,
                    )

    async def manual_start(self, member: discord.Member, actor: discord.Member | None, notes: str | None = None) -> dict[str, Any]:
        channel = self.current_valid_voice_channel(member)
        if channel is None:
            raise RuntimeError("O membro precisa estar em call válida para iniciar/retomar.")
        async with self._lock_for(member.id):
            session = await self.bot.db.get_active_voice_point_session(member.guild.id, member.id)
            if session is None:
                return await self._start_session(member, channel, start_mode="manual", started_by_user_id=actor.id if actor else None, notes=notes)
            if session["grace_started_at"]:
                await self._return_from_grace(session, channel)
                return await self.bot.db.get_active_voice_point_session(member.guild.id, member.id) or session
            raise RuntimeError("Já existe expediente ativo para este membro.")

    async def manual_pause(self, member: discord.Member, actor: discord.Member, notes: str | None = None) -> dict[str, Any]:
        async with self._lock_for(member.id):
            session = await self.bot.db.get_active_voice_point_session(member.guild.id, member.id)
            if session is None:
                raise RuntimeError("Não existe expediente ativo para este membro.")
            if session["grace_started_at"]:
                raise RuntimeError("Este expediente já está em tolerância.")
            await self._start_grace(session, reason=notes or "Pausa manual solicitada.")
            return await self.bot.db.get_active_voice_point_session(member.guild.id, member.id) or session

    async def manual_close(self, member: discord.Member, actor: discord.Member, close_reason: str | None = None) -> dict[str, Any]:
        async with self._lock_for(member.id):
            session = await self.bot.db.get_active_voice_point_session(member.guild.id, member.id)
            if session is None:
                raise RuntimeError("Não existe expediente ativo para este membro.")
            return await self._close_session_by_row(
                session,
                close_mode="manual",
                close_reason=close_reason or "Encerrado manualmente.",
                ended_by_user_id=actor.id,
            )

    async def describe_member_status(self, member: discord.Member) -> VoicePointStatus:
        session = await self.bot.db.get_active_voice_point_session(member.guild.id, member.id)
        if session is None:
            latest = await self.bot.db.latest_voice_point_session(member.guild.id, member.id)
            if latest is None:
                return VoicePointStatus(False, "Nenhum expediente foi registrado para este membro.", None)
            return VoicePointStatus(
                False,
                f"Último expediente encerrou em **{self._format_dt(self._parse_dt(latest['ended_at']))}** com duração **{self._format_duration(int(latest['total_seconds']))}**.",
                latest,
            )
        total_seconds = self._live_total_seconds(session)
        if session["grace_started_at"]:
            deadline = self._parse_dt(session["grace_deadline_at"])
            remaining = max(0, int((deadline - self._utcnow()).total_seconds()))
            summary = (
                f"Status: **Em Tolerância**.\nPrazo final: **{self._format_dt(deadline)}**.\n"
                f"Tempo restante: **{self._format_duration(remaining)}**."
            )
        else:
            summary = (
                "Status: **Em Expediente**.\n"
                f"Call atual: {self._render_channel(member.guild, session['active_channel_id'])}.\n"
                f"Tipo atual: **{self._group_label(self._resolve_runtime_group(session))}**.\n"
                f"Início: **{self._format_dt(self._parse_dt(session['started_at']))}**."
            )
        summary += (
            f"\nDuração viva: **{self._format_duration(total_seconds)}**.\n"
            f"Atendimento: **{self._format_duration(int(session['attendance_seconds']))}** | "
            f"Reunião: **{self._format_duration(int(session['meeting_seconds']))}** | "
            f"Liderança: **{self._format_duration(int(session['leadership_seconds']))}** | "
            f"Dev: **{self._format_duration(int(session['development_seconds']))}**."
        )
        return VoicePointStatus(True, summary, session)

    async def list_active_session_rows(self, guild: discord.Guild) -> list[dict[str, Any]]:
        return await self.bot.db.list_active_voice_point_sessions(guild.id)

    async def list_grace_session_rows(self, guild: discord.Guild) -> list[dict[str, Any]]:
        rows = await self.bot.db.list_active_voice_point_sessions(guild.id)
        return [row for row in rows if row["grace_started_at"]]

    async def audit_active_sessions(self, guild: discord.Guild) -> list[SessionAudit]:
        audits: list[SessionAudit] = []
        sessions = await self.bot.db.list_active_voice_point_sessions(guild.id)
        session_by_user = {int(item["user_id"]): item for item in sessions}
        for member in guild.members:
            if member.bot or not self.is_authorized_member(member):
                continue
            current = self.current_valid_voice_channel(member)
            if current and member.id not in session_by_user:
                audits.append(
                    SessionAudit(
                        {"id": 0, "guild_id": guild.id, "user_id": member.id, "active_channel_id": current.id},
                        "stale",
                        "Staff em call válida sem sessão ativa no banco.",
                    )
                )
        for session in sessions:
            member = guild.get_member(int(session["user_id"]))
            if member is None:
                audits.append(SessionAudit(session, "stale", "Membro não encontrado na guild."))
                continue
            if not self.is_authorized_member(member):
                audits.append(SessionAudit(session, "stale", "Membro sem cargo autorizado."))
                continue
            if session["grace_started_at"]:
                deadline = self._parse_dt(session["grace_deadline_at"])
                audits.append(
                    SessionAudit(
                        session,
                        "stale" if self._utcnow() >= deadline else "grace",
                        "Tolerância expirada aguardando encerramento." if self._utcnow() >= deadline else "Sessão em tolerância dentro do prazo.",
                    )
                )
                continue
            current = self.current_valid_voice_channel(member)
            if current is None:
                audits.append(SessionAudit(session, "stale", "Sessão ativa sem call válida e sem tolerância."))
                continue
            if int(session.get("active_channel_id") or 0) != current.id:
                audits.append(SessionAudit(session, "warn", "Sessão divergente da call atual."))
                continue
            audits.append(SessionAudit(session, "ok", "Sessão consistente com a presenca em voz."))
        return audits

    async def cleanup_stale_session(
        self,
        guild: discord.Guild,
        member: discord.Member | None = None,
        session_id: int | None = None,
        actor: discord.Member | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        target: dict[str, Any] | None = None
        if session_id is not None:
            raw = await self.bot.db.get_voice_point_session(session_id)
            if raw and raw["status"] == "active" and int(raw["guild_id"]) == guild.id:
                target = raw
        elif member is not None:
            target = await self.bot.db.get_active_voice_point_session(guild.id, member.id)
        if target is None:
            raise RuntimeError("Nenhuma sessao ativa correspondente foi encontrada.")
        return await self._close_session_by_row(
            target,
            close_mode="stale_cleanup",
            close_reason=reason or "Sessão encerrada por limpeza operacional segura.",
            ended_by_user_id=actor.id if actor else None,
        )

    async def reconcile_active_sessions(self, guild: discord.Guild) -> list[SessionAudit]:
        audits = await self.audit_active_sessions(guild)
        for audit in audits:
            if audit.status == "warn":
                member = guild.get_member(int(audit.session["user_id"]))
                if member:
                    current = self.current_valid_voice_channel(member)
                    if current:
                        async with self._lock_for(member.id):
                            refreshed = await self.bot.db.get_active_voice_point_session(guild.id, member.id)
                            if refreshed and refreshed["status"] == "active" and not refreshed["grace_started_at"]:
                                await self._move_session(refreshed, current, reason="Reconciliacao automatica.", log_event="Reconciliacao Operacional")
            if audit.status == "stale":
                uid = int(audit.session["user_id"])
                async with self._lock_for(uid):
                    refreshed = await self.bot.db.get_active_voice_point_session(guild.id, uid)
                    if refreshed:
                        await self._close_session_by_row(
                            refreshed,
                            close_mode="stale_cleanup",
                            close_reason=f"Correcao automatica de stale: {audit.detail}",
                            ended_by_user_id=self.bot.user.id if self.bot.user else None,
                        )
        return audits

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        channel_id = self.bot.server_map.voice_point_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do painel de expediente nao encontrado.")
        embed = await self.build_panel_embed(guild)
        view = self.bot.view_factory.build_voice_point_panel_view()
        stored = await self.bot.db.get_voice_point_panel_message(guild.id)
        if stored:
            message = await self._fetch_message(channel, int(stored["message_id"]))
            if message:
                await message.edit(embed=embed, view=view)
                await self.bot.db.save_voice_point_panel_message(guild.id, channel.id, message.id)
                return message
        message = await channel.send(embed=embed, view=view)
        await self.bot.db.save_voice_point_panel_message(guild.id, channel.id, message.id)
        return message

    async def refresh_panel_message(self, guild: discord.Guild) -> None:
        stored = await self.bot.db.get_voice_point_panel_message(guild.id)
        if not stored:
            return
        channel = guild.get_channel(int(stored["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        message = await self._fetch_message(channel, int(stored["message_id"]))
        if not message:
            await self.publish_panel(guild)
            return
        await message.edit(embed=await self.build_panel_embed(guild), view=self.bot.view_factory.build_voice_point_panel_view())

    async def build_panel_embed(self, guild: discord.Guild) -> discord.Embed:
        now = self._utcnow()
        rows = await self.bot.db.list_active_voice_point_sessions(guild.id)
        grace_count = sum(1 for row in rows if row["grace_started_at"])
        active_lines: list[str] = []
        grace_lines: list[str] = []
        for row in rows[:12]:
            mention = f"<@{row['user_id']}>"
            if row["grace_started_at"]:
                deadline = self._parse_dt(row["grace_deadline_at"])
                remaining = max(0, int((deadline - now).total_seconds()))
                grace_lines.append(f"{mention} | prazo `{self._format_dt(deadline)}` | restante `{self._format_duration(remaining)}`")
            else:
                active_lines.append(
                    f"{mention} | {self._render_channel(guild, row['active_channel_id'])} | `{self._group_label(self._resolve_runtime_group(row))}` | `{self._format_duration(self._live_total_seconds(row))}`"
                )
        embed = self.bot.embeds.make(
            title="🎙️ Painel Operacional da Staff",
            description="Expediente automatico por ID: entrada em call valida inicia, saida entra em tolerancia, sem retorno encerra automaticamente.",
        )
        embed.add_field(name="Sistema", value="Operacional" if self.enabled() else "Desabilitado", inline=True)
        embed.add_field(name="Em Expediente", value=str(len(rows) - grace_count), inline=True)
        embed.add_field(name="Em Tolerancia", value=str(grace_count), inline=True)
        embed.add_field(name="Calls Monitoradas", value=str(len(self.bot.server_map.voice_point_valid_channel_ids())), inline=True)
        embed.add_field(name="Tolerancia", value=f"{self.bot.server_map.voice_point_grace_period_seconds()}s", inline=True)
        embed.add_field(name="Ultima Atualizacao", value=self._format_dt(now), inline=True)
        embed.add_field(name="Equipe em Operacao", value="\n".join(active_lines) if active_lines else "Nenhum membro em expediente.", inline=False)
        embed.add_field(name="Janelas de Tolerancia", value="\n".join(grace_lines) if grace_lines else "Nenhuma sessao em tolerancia.", inline=False)
        embed.add_field(name="Acoes", value="`Meu Estado` | `Encerrar meu expediente` | `Atualizar painel`", inline=False)
        embed.timestamp = now
        return embed

    async def build_admin_snapshot_embed(self, guild: discord.Guild) -> discord.Embed:
        active = await self.bot.db.list_active_voice_point_sessions(guild.id)
        audits = await self.audit_active_sessions(guild)
        stale_count = sum(1 for x in audits if x.status == "stale")
        warn_count = sum(1 for x in audits if x.status == "warn")
        embed = self.bot.embeds.make(
            title="Quadro Operacional do Expediente",
            description="Leitura administrativa por ID das sessoes monitoradas.",
        )
        embed.add_field(name="Ativos", value=str(len(active)), inline=True)
        embed.add_field(name="Alertas", value=str(stale_count + warn_count), inline=True)
        embed.add_field(name="Atualizado em", value=self._format_dt(self._utcnow()), inline=True)
        lines = []
        for row in active[:12]:
            state = "Tolerancia" if row["grace_started_at"] else self._group_label(self._resolve_runtime_group(row))
            lines.append(f"<@{row['user_id']}> | `{state}` | `{self._format_duration(self._live_total_seconds(row))}`")
        embed.add_field(name="Sessoes Ativas", value="\n".join(lines) if lines else "Nenhuma sessao ativa.", inline=False)
        return embed

    async def publish_management_dashboard(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        if not self.bot.server_map.management_dashboard_enabled():
            raise RuntimeError("Dashboard de gestao desabilitado na configuracao.")
        channel_id = self.bot.server_map.management_dashboard_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do dashboard de gestao nao encontrado.")
        embed = await self.build_management_dashboard_embed(guild)
        stored = await self.bot.db.get_management_dashboard_message(guild.id)
        if stored:
            message = await self._fetch_message(channel, int(stored["message_id"]))
            if message:
                await message.edit(embed=embed)
                await self.bot.db.save_management_dashboard_message(guild.id, channel.id, message.id)
                return message
        message = await channel.send(embed=embed)
        await self.bot.db.save_management_dashboard_message(guild.id, channel.id, message.id)
        return message

    async def refresh_management_dashboard(self, guild: discord.Guild) -> None:
        if not self.bot.server_map.management_dashboard_enabled():
            return
        stored = await self.bot.db.get_management_dashboard_message(guild.id)
        if not stored:
            return
        channel = guild.get_channel(int(stored["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        message = await self._fetch_message(channel, int(stored["message_id"]))
        if not message:
            await self.publish_management_dashboard(guild)
            return
        await message.edit(embed=await self.build_management_dashboard_embed(guild))

    async def ranking_horas(self, guild: discord.Guild, periodo: str, limit: int = 10) -> list[dict[str, Any]]:
        start_at, end_at = self._period_bounds(periodo)
        result = []
        for member in guild.members:
            if member.bot or not self.is_authorized_member(member):
                continue
            secs = await self._voice_seconds_for_staff(guild.id, member.id, start_at, end_at)
            result.append
        result.sort(key=lambda item: item["seconds"], reverse=True)
        return result[:limit]

    async def ranking_tickets(self, guild: discord.Guild, periodo: str, limit: int = 10) -> list[dict[str, Any]]:
        start_at, end_at = self._period_bounds(periodo)
        rows = await self.bot.db.list_staff_tickets_by_period(guild.id, self._iso(start_at), self._iso(end_at))
        counter: dict[int, int] = {}
        for row in rows:
            resolver = int(row.get("resolved_staff_id") or row.get("closed_by_id") or row.get("closed_by") or 0)
            if resolver <= 0:
                continue
            counter[resolver] = counter.get(resolver, 0) + 1
        ranking = [{"user_id": uid, "tickets": qty} for uid, qty in counter.items()]
        ranking.sort(key=lambda item: item["tickets"], reverse=True)
        return ranking[:limit]

    async def resumo_executivo(self, guild: discord.Guild, periodo: str) -> dict[str, Any]:
        start_at, end_at = self._period_bounds(periodo)
        staff_ids = [m.id for m in guild.members if (not m.bot and self.is_authorized_member(m))]
        total_seconds = 0
        for uid in staff_ids:
            total_seconds += await self._voice_seconds_for_staff(guild.id, uid, start_at, end_at)
        tickets = await self.bot.db.list_staff_tickets_by_period(guild.id, self._iso(start_at), self._iso(end_at))
        total_tickets = 0
        for row in tickets:
            resolver = int(row.get("resolved_staff_id") or row.get("closed_by_id") or row.get("closed_by") or 0)
            if resolver in staff_ids:
                total_tickets += 1
        count = max(1, len(staff_ids))
        return {
            "total_seconds": total_seconds,
            "total_tickets": total_tickets,
            "average_seconds_per_staff": int(total_seconds / count),
            "average_tickets_per_staff": float(total_tickets / count),
        }

    async def build_management_dashboard_embed(self, guild: discord.Guild) -> discord.Embed:
        now = self._utcnow()
        active = await self.bot.db.list_active_voice_point_sessions(guild.id)
        grace = sum(1 for row in active if row["grace_started_at"])
        audits = await self.audit_active_sessions(guild)
        alerts = [a for a in audits if a.status in {"stale", "warn"}]
        weekly_hours = await self.ranking_horas(guild, "semanal", limit=8)
        monthly_hours = await self.ranking_horas(guild, "mensal", limit=8)
        weekly_tickets = await self.ranking_tickets(guild, "semanal", limit=8)
        monthly_tickets = await self.ranking_tickets(guild, "mensal", limit=8)
        summary_week = await self.resumo_executivo(guild, "semanal")
        summary_month = await self.resumo_executivo(guild, "mensal")
        embed = self.bot.embeds.make(
            title="Dashboard Executivo da Gestao",
            description="Visao premium da operacao real da staff: expediente, produtividade e alertas.",
        )
        embed.add_field(name="Sistema", value="Online" if self.enabled() else "Offline", inline=True)
        embed.add_field(name="Em Expediente", value=str(len(active) - grace), inline=True)
        embed.add_field(name="Em Tolerancia", value=str(grace), inline=True)
        embed.add_field(name="Com Alertas", value=str(len(alerts)), inline=True)
        embed.add_field(name="Calls Monitoradas", value=str(len(self.bot.server_map.voice_point_valid_channel_ids())), inline=True)
        embed.add_field(name="Ultima Atualizacao", value=self._format_dt(now), inline=True)
        if active:
            now_lines = []
            for row in active[:12]:
                state = "Tolerancia" if row["grace_started_at"] else self._group_label(self._resolve_runtime_group(row))
                now_lines.append(f"<@{row['user_id']}> | {self._render_channel(guild, row['active_channel_id'])} | `{state}` | `{self._format_duration(self._live_total_seconds(row))}`")
            embed.add_field(name="Operacao Agora", value="\n".join(now_lines), inline=False)
        if alerts:
            embed.add_field(name="Alertas", value="\n".join(f"<@{a.session['user_id']}> | {a.detail}" for a in alerts[:8]), inline=False)
        embed.add_field(name="Ranking Horas Semana", value=self._render_rank(weekly_hours, "seconds"), inline=False)
        embed.add_field(name="Ranking Horas Mes", value=self._render_rank(monthly_hours, "seconds"), inline=False)
        embed.add_field(name="Ranking Tickets Semana", value=self._render_rank(weekly_tickets, "tickets"), inline=False)
        embed.add_field(name="Ranking Tickets Mes", value=self._render_rank(monthly_tickets, "tickets"), inline=False)
        embed.add_field(
            name="Resumo Executivo Semanal",
            value=f"Horas: `{self._format_duration(summary_week['total_seconds'])}` | Tickets: `{summary_week['total_tickets']}` | Media horas/staff: `{self._format_duration(summary_week['average_seconds_per_staff'])}`",
            inline=False,
        )
        embed.add_field(
            name="Resumo Executivo Mensal",
            value=f"Horas: `{self._format_duration(summary_month['total_seconds'])}` | Tickets: `{summary_month['total_tickets']}` | Media horas/staff: `{self._format_duration(summary_month['average_seconds_per_staff'])}`",
            inline=False,
        )
        embed.timestamp = now
        return embed

    async def build_staff_report_embeds(self, guild: discord.Guild, member: discord.Member) -> list[discord.Embed]:
        now = self._utcnow()
        start_today = self._start_of_day(now)
        start_week = self._start_of_week(now)
        start_month = self._start_of_month(now)
        status = await self.describe_member_status(member)
        hours_today = await self._voice_seconds_for_staff(guild.id, member.id, start_today, now)
        hours_week = await self._voice_seconds_for_staff(guild.id, member.id, start_week, now)
        hours_month = await self._voice_seconds_for_staff(guild.id, member.id, start_month, now)
        hours_total = await self._voice_seconds_for_staff(guild.id, member.id, datetime(1970, 1, 1, tzinfo=UTC), now)
        tickets_today = await self._ticket_stats_for_staff(guild.id, member.id, start_today, now)
        tickets_week = await self._ticket_stats_for_staff(guild.id, member.id, start_week, now)
        tickets_month = await self._ticket_stats_for_staff(guild.id, member.id, start_month, now)
        tickets_total = await self._ticket_stats_for_staff(guild.id, member.id, datetime(1970, 1, 1, tzinfo=UTC), now)
        embed1 = self.bot.embeds.make(
            title="Relatorio Premium por Staff",
            description=f"{member.mention}\n\n{status.summary}",
        )
        embed1.add_field(name="Horas Hoje", value=self._format_duration(hours_today), inline=True)
        embed1.add_field(name="Horas Semana", value=self._format_duration(hours_week), inline=True)
        embed1.add_field(name="Horas Mes", value=self._format_duration(hours_month), inline=True)
        embed1.add_field(name="Horas Totais", value=self._format_duration(hours_total), inline=True)
        embed1.add_field(name="Tickets Hoje", value=str(tickets_today["resolved"]), inline=True)
        embed1.add_field(name="Tickets Semana", value=str(tickets_week["resolved"]), inline=True)
        embed2 = self.bot.embeds.make(
            title="Produtividade de Tickets",
            description="Contagem principal baseada em `resolved_staff_id` (fallback `closed_by_id` / `closed_by`).",
            fields=[
                ("Atendidos Mes", str(tickets_month["resolved"]), True),
                ("Atendidos Total", str(tickets_total["resolved"]), True),
                ("Assumidos Semana", str(tickets_week["claimed"]), True),
                ("Encerrados Semana", str(tickets_week["closed"]), True),
                ("Assumidos Mes", str(tickets_month["claimed"]), True),
                ("Encerrados Mes", str(tickets_month["closed"]), True),
                ("Tempo medio por ticket (semana)", self._format_duration(tickets_week["avg_resolution_seconds"]), True),
                ("Tickets por categoria (semana)", tickets_week["by_type"], False),
            ],
        )
        return [embed1, embed2]

    async def _start_session(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel | discord.StageChannel,
        *,
        start_mode: str,
        started_by_user_id: int | None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        existing = await self.bot.db.get_active_voice_point_session(member.guild.id, member.id)
        if existing:
            raise RuntimeError("Ja existe um expediente ativo para este membro.")
        group = self.channel_group(channel.id)
        if group is None:
            raise RuntimeError("A call atual nao pertence a nenhum grupo de expediente.")
        now = self._utcnow()
        session_id = await self.bot.db.create_voice_point_session(
            guild_id=member.guild.id,
            user_id=member.id,
            started_at=self._iso(now),
            channel_id=channel.id,
            channel_group=group,
            start_mode=start_mode,
            started_by_user_id=started_by_user_id,
            notes=notes,
        )
        await self._dispatch_voice_log(
            "Inicio de Expediente",
            f"{member.mention} iniciou expediente por **{start_mode}**.",
            fields=[("Sessão", f"``", True), ("Call", self._render_channel(member.guild, channel.id), True), ("Tipo", self._group_label(group), True)],
            color=self.bot.embeds.success_color,
        )
        await self.refresh_panel_message(member.guild)
        await self.refresh_management_dashboard(member.guild)
        return await self.bot.db.get_voice_point_session(session_id) or {}

    async def _move_session(self, session: dict[str, Any], channel: discord.VoiceChannel | discord.StageChannel, *, reason: str, log_event: str = "Troca de Call") -> None:
        now = self._utcnow()
        previous_group = str(session.get("active_channel_group") or session.get("last_valid_channel_group") or "attendance_channels")
        previous_channel_id = int(session.get("active_channel_id") or 0)
        started = self._parse_dt(session["current_segment_started_at"])
        duration = max(0, int((now - started).total_seconds()))
        updates = self._build_group_updates(session, previous_group, duration)
        updates["total_seconds"] = int(session["total_seconds"]) + duration
        updates["transition_count"] = int(session["transition_count"]) + 1
        updates["active_channel_id"] = channel.id
        updates["active_channel_group"] = self.channel_group(channel.id)
        updates["last_valid_channel_id"] = channel.id
        updates["last_valid_channel_group"] = self.channel_group(channel.id)
        updates["current_segment_started_at"] = self._iso(now)
        updates["updated_at"] = self._iso(now)
        await self.bot.db.add_voice_point_segment(
            session_id=int(session["id"]),
            channel_id=previous_channel_id,
            channel_group=previous_group,
            segment_kind="voice",
            started_at=self._iso(started),
            ended_at=self._iso(now),
            duration_seconds=duration,
        )
        await self.bot.db.update_voice_point_session(int(session["id"]), updates)
        guild = self.bot.get_guild(int(session["guild_id"]))
        await self._dispatch_voice_log(
            log_event,
            f"<@{session['user_id']}> mudou de call valida sem reiniciar o expediente.",
            fields=[("De", self._render_channel(guild, previous_channel_id), True), ("Para", self._render_channel(guild, channel.id), True), ("Motivo", reason, False)],
        )
        if guild:
            await self.refresh_panel_message(guild)
            await self.refresh_management_dashboard(guild)

    async def _start_grace(self, session: dict[str, Any], *, reason: str) -> None:
        now = self._utcnow()
        updates: dict[str, Any] = {
            "grace_started_at": self._iso(now),
            "grace_deadline_at": self._iso(now + self._grace_delta()),
            "active_channel_id": None,
            "active_channel_group": None,
            "current_segment_started_at": None,
            "updated_at": self._iso(now),
        }
        if session["current_segment_started_at"] and session["last_valid_channel_id"] and session["last_valid_channel_group"]:
            seg_start = self._parse_dt(session["current_segment_started_at"])
            duration = max(0, int((now - seg_start).total_seconds()))
            await self.bot.db.add_voice_point_segment(
                session_id=int(session["id"]),
                channel_id=int(session["last_valid_channel_id"]),
                channel_group=str(session["last_valid_channel_group"]),
                segment_kind="voice",
                started_at=self._iso(seg_start),
                ended_at=self._iso(now),
                duration_seconds=duration,
            )
            updates["total_seconds"] = int(session["total_seconds"]) + duration
            updates.update(self._build_group_updates(session, str(session["last_valid_channel_group"]), duration))
        await self.bot.db.update_voice_point_session(int(session["id"]), updates)
        refreshed = await self.bot.db.get_voice_point_session(int(session["id"]))
        if refreshed:
            self._schedule_grace_timeout(refreshed, self._parse_dt(refreshed["grace_deadline_at"]))
        guild = self.bot.get_guild(int(session["guild_id"]))
        await self._dispatch_voice_log("Tolerancia Iniciada", f"<@{session['user_id']}> entrou em tolerancia.", fields=[("Motivo", reason, False)])
        if guild:
            await self.refresh_panel_message(guild)
            await self.refresh_management_dashboard(guild)

    async def _return_from_grace(self, session: dict[str, Any], channel: discord.VoiceChannel | discord.StageChannel) -> None:
        self._cancel_grace_task(int(session["user_id"]))
        now = self._utcnow()
        grace_started = self._parse_dt(session["grace_started_at"])
        grace_duration = max(0, int((now - grace_started).total_seconds()))
        await self.bot.db.add_voice_point_segment(
            session_id=int(session["id"]),
            channel_id=None,
            channel_group="grace",
            segment_kind="grace",
            started_at=self._iso(grace_started),
            ended_at=self._iso(now),
            duration_seconds=grace_duration,
        )
        group = self.channel_group(channel.id)
        await self.bot.db.update_voice_point_session(
            int(session["id"]),
            {
                "grace_started_at": None,
                "grace_deadline_at": None,
                "grace_seconds": int(session["grace_seconds"]) + grace_duration,
                "total_seconds": int(session["total_seconds"]) + grace_duration,
                "active_channel_id": channel.id,
                "active_channel_group": group,
                "last_valid_channel_id": channel.id,
                "last_valid_channel_group": group,
                "current_segment_started_at": self._iso(now),
                "updated_at": self._iso(now),
            },
        )
        guild = self.bot.get_guild(int(session["guild_id"]))
        await self._dispatch_voice_log("Retorno Durante a Tolerancia", f"<@{session['user_id']}> retornou a call valida.")
        if guild:
            await self.refresh_panel_message(guild)
            await self.refresh_management_dashboard(guild)

    async def _close_session_by_row(
        self,
        session: dict[str, Any],
        *,
        close_mode: str,
        close_reason: str,
        ended_by_user_id: int | None,
    ) -> dict[str, Any]:
        self._cancel_grace_task(int(session["user_id"]))
        now = self._utcnow()
        updates: dict[str, Any] = {
            "status": "closed",
            "ended_at": self._iso(now),
            "close_mode": close_mode,
            "close_reason": close_reason,
            "ended_by_user_id": ended_by_user_id,
            "active_channel_id": None,
            "active_channel_group": None,
            "current_segment_started_at": None,
            "grace_started_at": None,
            "grace_deadline_at": None,
            "updated_at": self._iso(now),
        }
        if session["grace_started_at"]:
            gs = self._parse_dt(session["grace_started_at"])
            gd = max(0, int((now - gs).total_seconds()))
            await self.bot.db.add_voice_point_segment(
                session_id=int(session["id"]),
                channel_id=None,
                channel_group="grace",
                segment_kind="grace",
                started_at=self._iso(gs),
                ended_at=self._iso(now),
                duration_seconds=gd,
            )
            updates["grace_seconds"] = int(session["grace_seconds"]) + gd
            updates["total_seconds"] = int(session["total_seconds"]) + gd
        elif session["current_segment_started_at"] and session["last_valid_channel_id"] and session["last_valid_channel_group"]:
            ss = self._parse_dt(session["current_segment_started_at"])
            d = max(0, int((now - ss).total_seconds()))
            await self.bot.db.add_voice_point_segment(
                session_id=int(session["id"]),
                channel_id=int(session["last_valid_channel_id"]),
                channel_group=str(session["last_valid_channel_group"]),
                segment_kind="voice",
                started_at=self._iso(ss),
                ended_at=self._iso(now),
                duration_seconds=d,
            )
            updates["total_seconds"] = int(session["total_seconds"]) + d
            updates.update(self._build_group_updates(session, str(session["last_valid_channel_group"]), d))
        await self.bot.db.update_voice_point_session(int(session["id"]), updates)
        closed = await self.bot.db.get_voice_point_session(int(session["id"]))
        guild = self.bot.get_guild(int(session["guild_id"]))
        if closed:
            await self._send_report(closed, guild)
        await self._dispatch_voice_log("Encerramento de Expediente", f"<@{session['user_id']}> teve o expediente encerrado por **{close_mode}**.")
        if guild:
            await self.refresh_panel_message(guild)
            await self.refresh_management_dashboard(guild)
        return closed or session

    async def _send_report(self, session: dict[str, Any], guild: discord.Guild | None) -> None:
        channel_id = self.bot.server_map.voice_point_report_channel_id()
        channel = guild.get_channel(channel_id) if guild and channel_id else self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.bot.embeds.make(
            title="Relatorio Oficial de Encerramento da Staff",
            description=f"Consolidado administrativo da sessao de <@{session['user_id']}>.",
            fields=[
                ("Membro", f"<@{session['user_id']}>", True),
                ("User ID", f"indisponível", True),
                ("Inicio", self._format_dt(self._parse_dt(session["started_at"])), True),
                ("Fim", self._format_dt(self._parse_dt(session["ended_at"])), True),
                ("Duracao Total", self._format_duration(int(session["total_seconds"])), True),
                ("Tempo em Atendimento", self._format_duration(int(session["attendance_seconds"])), True),
                ("Tempo em Reuniao", self._format_duration(int(session["meeting_seconds"])), True),
                ("Tempo em Lideranca", self._format_duration(int(session["leadership_seconds"])), True),
                ("Tempo em Desenvolvimento", self._format_duration(int(session["development_seconds"])), True),
                ("Tempo em Tolerancia", self._format_duration(int(session["grace_seconds"])), True),
                ("Call Inicial", self._render_channel(guild, session["initial_channel_id"]), True),
                ("Call Final", self._render_channel(guild, session["last_valid_channel_id"]), True),
                ("Tipo Inicial", self._group_label(session["initial_channel_group"]), True),
                ("Tipo Final", self._group_label(session["last_valid_channel_group"]), True),
                ("Abertura", str(session["start_mode"]).replace("_", " ").title(), True),
                ("Encerramento", str(session["close_mode"]).replace("_", " ").title(), True),
                ("Transicoes", str(session["transition_count"]), True),
                ("Observacoes", session["close_reason"] or session["notes"] or "Nenhuma observacao.", False),
            ],
        )
        await channel.send(embed=embed)

    async def _dispatch_voice_log(
        self,
        title: str,
        description: str,
        *,
        fields: list[tuple[str, str, bool]] | None = None,
        color: int | None = None,
    ) -> None:
        channel_id = self.bot.server_map.voice_point_log_channel_id()
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.bot.embeds.make(title=title, description=description, color=color or self.bot.embeds.default_color, fields=fields)
        embed.timestamp = self._utcnow()
        await channel.send(embed=embed)

    async def _voice_seconds_for_staff(self, guild_id: int, user_id: int, start_at: datetime, end_at: datetime) -> int:
        segments = await self.bot.db.list_voice_segments_in_range(guild_id, self._iso(start_at), self._iso(end_at), user_id=user_id)
        total = 0
        for seg in segments:
            seg_start = self._parse_dt(seg["started_at"])
            seg_end = self._parse_dt(seg["ended_at"])
            total += self._overlap_seconds(seg_start, seg_end, start_at, end_at)
        active = await self.bot.db.get_active_voice_point_session(guild_id, user_id)
        if active:
            now = min(self._utcnow(), end_at)
            if active.get("grace_started_at"):
                gs = self._parse_dt(active["grace_started_at"])
                total += self._overlap_seconds(gs, now, start_at, end_at)
            elif active.get("current_segment_started_at"):
                cs = self._parse_dt(active["current_segment_started_at"])
                total += self._overlap_seconds(cs, now, start_at, end_at)
        return total

    async def _ticket_stats_for_staff(self, guild_id: int, user_id: int, start_at: datetime, end_at: datetime) -> dict[str, Any]:
        resolved = await self.bot.db.list_staff_tickets_by_period(guild_id, self._iso(start_at), self._iso(end_at), staff_user_id=user_id)
        claims = await self.bot.db.list_staff_ticket_claims_by_period(guild_id, self._iso(start_at), self._iso(end_at), staff_user_id=user_id)
        closed = [row for row in resolved if int(row.get("closed_by_id") or row.get("closed_by") or 0) == user_id]
        by_type: dict[str, int] = {}
        total_dur = 0
        dur_count = 0
        for row in resolved:
            key = str(row.get("ticket_type") or "desconhecido")
            by_type[key] = by_type.get(key, 0) + 1
            opened = self._parse_optional_dt(row.get("opened_at"))
            ended = self._parse_optional_dt(row.get("closed_at"))
            if opened and ended and ended >= opened:
                total_dur += int((ended - opened).total_seconds())
                dur_count += 1
        text = " | ".join(f"{k}: {v}" for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:6]) if by_type else "Sem tickets"
        return {
            "resolved": len(resolved),
            "claimed": len(claims),
            "closed": len(closed),
            "avg_resolution_seconds": int(total_dur / dur_count) if dur_count else 0,
            "by_type": text,
        }

    def _render_rank(self, rows: list[dict[str, Any]], metric_key: str) -> str:
        if not rows:
            return "Sem dados no periodo."
        lines = []
        for idx, row in enumerate(rows, start=1):
            metric = self._format_duration(int(row.get("seconds", 0))) if metric_key == "seconds" else str(int(row.get("tickets", 0)))
            lines.append(f"{idx}. <@{row['user_id']}> - `{metric}`")
        return "\n".join(lines)

    def _schedule_grace_timeout(self, session: dict[str, Any], deadline: datetime) -> None:
        user_id = int(session["user_id"])
        self._cancel_grace_task(user_id)

        async def runner() -> None:
            try:
                await asyncio.sleep(max(0, (deadline - self._utcnow()).total_seconds()))
                async with self._lock_for(user_id):
                    refreshed = await self.bot.db.get_active_voice_point_session(int(session["guild_id"]), user_id)
                    if refreshed and refreshed["grace_started_at"] and self._utcnow() >= self._parse_dt(refreshed["grace_deadline_at"]):
                        await self._close_session_by_row(
                            refreshed,
                            close_mode="automatic",
                            close_reason="Tolerancia expirada sem retorno a call valida.",
                            ended_by_user_id=self.bot.user.id if self.bot.user else None,
                        )
            finally:
                self._grace_tasks.pop(user_id, None)

        self._grace_tasks[user_id] = asyncio.create_task(runner(), name=f"voice-point-grace-{user_id}")

    def _cancel_grace_task(self, user_id: int) -> None:
        task = self._grace_tasks.pop(user_id, None)
        if task:
            task.cancel()

    def _ensure_maintenance_task(self) -> None:
        if self._maintenance_task and not self._maintenance_task.done():
            return

        async def runner() -> None:
            while True:
                try:
                    await asyncio.sleep(90)
                    guild = self.bot.get_guild(self.bot.server_map.guild_id())
                    if guild and self.enabled():
                        await self.reconcile_active_sessions(guild)
                        await self.refresh_panel_message(guild)
                        await self.refresh_management_dashboard(guild)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.bot.log.exception("Falha na ronda de reconciliacao do expediente por voz.")

        self._maintenance_task = asyncio.create_task(runner(), name="voice-point-maintenance")

    def _period_bounds(self, periodo: str) -> tuple[datetime, datetime]:
        now = self._utcnow()
        key = str(periodo).strip().lower()
        if key in {"semanal", "semana", "weekly"}:
            return self._start_of_week(now), now
        if key in {"mensal", "mes", "monthly"}:
            return self._start_of_month(now), now
        raise RuntimeError("Periodo invalido. Use semanal ou mensal.")

    def _lock_for(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_dt(raw: str) -> datetime:
        return datetime.fromisoformat(str(raw)).astimezone(UTC)

    @staticmethod
    def _parse_optional_dt(raw: Any) -> datetime | None:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw)).astimezone(UTC)
        except ValueError:
            return None

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.astimezone(BRASILIA_TZ).strftime("%d/%m/%Y %H:%M:%S (Horario de Brasilia)")

    @staticmethod
    def _format_duration(seconds: int) -> str:
        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}h {minutes:02d}m {secs:02d}s"

    @staticmethod
    def _start_of_day(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _start_of_week(value: datetime) -> datetime:
        start = PointService._start_of_day(value)
        return start - timedelta(days=start.weekday())

    @staticmethod
    def _start_of_month(value: datetime) -> datetime:
        start = PointService._start_of_day(value)
        return start.replace(day=1)

    @staticmethod
    def _overlap_seconds(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> int:
        start = max(start_a, start_b)
        end = min(end_a, end_b)
        return max(0, int((end - start).total_seconds()))

    @staticmethod
    def _group_label(group_name: str | None) -> str:
        if group_name is None:
            return "Nao classificado"
        return GROUP_TO_LABEL.get(group_name, group_name.replace("_", " ").title())

    def _build_group_updates(self, session: dict[str, Any], group_name: str, duration: int) -> dict[str, Any]:
        column = GROUP_TO_COLUMN.get(group_name)
        if not column:
            return {}
        return {column: int(session[column]) + duration}

    def _live_total_seconds(self, session: dict[str, Any]) -> int:
        total = int(session["total_seconds"])
        now = self._utcnow()
        if session["grace_started_at"]:
            total += max(0, int((now - self._parse_dt(session["grace_started_at"])).total_seconds()))
        elif session["current_segment_started_at"]:
            total += max(0, int((now - self._parse_dt(session["current_segment_started_at"])).total_seconds()))
        return total

    def _render_channel(self, guild: discord.Guild | None, channel_id: Any) -> str:
        if not channel_id:
            return "`Nao registrado`"
        channel = guild.get_channel(int(channel_id)) if guild else self.bot.get_channel(int(channel_id))
        if channel is None:
            return f"indisponível (ausente)"
        return f"{channel.mention}"

    async def _fetch_message(self, channel: discord.TextChannel, message_id: int) -> discord.Message | None:
        try:
            return await channel.fetch_message(message_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    def _grace_delta(self) -> timedelta:
        return timedelta(seconds=self.bot.server_map.voice_point_grace_period_seconds())



