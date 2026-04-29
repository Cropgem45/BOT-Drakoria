from __future__ import annotations

from typing import Any

import discord

from app.services.staff_timeclock_service import ACTIVITIES


class StaffTimeclockPanelView(discord.ui.View):
    """Painel principal do expediente — persistente."""

    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _ensure_guild_member(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto Inválido", "Este painel só pode ser usado dentro do servidor."),
                ephemeral=True,
            )
            return False
        if interaction.guild_id != self.bot.server_map.guild_id():
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Servidor Incorreto", "Este painel não pertence a este servidor."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Iniciar Expediente",
        emoji="▶️",
        style=discord.ButtonStyle.success,
        custom_id="timeclock:panel:start",
        row=0,
    )
    async def start_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_guild_member(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.start_session(interaction.user)
            await interaction.followup.send(
                embed=self.bot.embeds.success(
                    "Expediente Iniciado",
                    "Seu expediente foi iniciado com atividade **Não classificado**.\nUse o botão **Marcar Atividade** para classificar o que está fazendo.",
                ),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(
        label="Pausar",
        emoji="⏸️",
        style=discord.ButtonStyle.secondary,
        custom_id="timeclock:panel:pause",
        row=0,
    )
    async def pause_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_guild_member(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.pause_session(interaction.user)
            await interaction.followup.send(
                embed=self.bot.embeds.make(title="Expediente Pausado", description="Use **Retomar** quando voltar ao trabalho."),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(
        label="Retomar",
        emoji="▶️",
        style=discord.ButtonStyle.primary,
        custom_id="timeclock:panel:resume",
        row=0,
    )
    async def resume_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_guild_member(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.resume_session(interaction.user)
            await interaction.followup.send(
                embed=self.bot.embeds.success("Expediente Retomado", "Bem-vindo de volta! Seu expediente foi retomado."),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(
        label="Encerrar Expediente",
        emoji="⏹️",
        style=discord.ButtonStyle.danger,
        custom_id="timeclock:panel:end",
        row=1,
    )
    async def end_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_guild_member(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            closed = await self.bot.staff_timeclock_service.end_session(interaction.user, reason="Encerrado pelo painel.")
            segments = await self.bot.db.get_session_segments(int(closed["id"]))
            by_act: dict[str, int] = {}
            for seg in segments:
                if seg["ended_at"] and seg["duration_seconds"]:
                    act = str(seg["activity"])
                    by_act[act] = by_act.get(act, 0) + int(seg["duration_seconds"])
            total = sum(by_act.values())
            act_text = "\n".join(f"— **{a}:** {_fmt(s)}" for a, s in sorted(by_act.items(), key=lambda x: x[1], reverse=True) if s > 0) or "Sem atividades classificadas."
            embed = self.bot.embeds.make(
                title="Expediente Encerrado",
                description="Sua sessão foi finalizada. Resumo abaixo:",
                fields=[
                    ("Total Validado", _fmt(total), True),
                    ("Por Atividade", act_text, False),
                ],
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(
        label="Marcar Atividade",
        emoji="🏷️",
        style=discord.ButtonStyle.secondary,
        custom_id="timeclock:panel:activity",
        row=1,
    )
    async def activity_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_guild_member(interaction):
            return
        session = await self.bot.db.get_staff_open_session(interaction.guild_id, interaction.user.id)
        if session is None or session["status"] != "active":
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Sem expediente ativo", "Você precisa estar em expediente ativo para trocar atividade."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=self.bot.embeds.make(
                title="Selecionar Atividade",
                description="Escolha no menu abaixo a atividade que está realizando.",
            ),
            view=ActivitySelectView(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Minhas Horas",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="timeclock:panel:myhours",
        row=1,
    )
    async def my_hours_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_guild_member(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        embed = await self.bot.staff_timeclock_service.build_member_hours_embed(interaction.guild, interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)


class ActivitySelectView(discord.ui.View):
    """View temporária para seleção de atividade."""

    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.add_item(ActivitySelect(bot))


class ActivitySelect(discord.ui.Select):
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        options = [
            discord.SelectOption(label=a, value=a)
            for a in ACTIVITIES
        ]
        super().__init__(
            placeholder="Selecione a atividade atual...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        activity = self.values[0]
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.change_activity(interaction.user, activity)
            await interaction.followup.send(
                embed=self.bot.embeds.success("Atividade Alterada", f"Atividade atual: **{activity}**"),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)


class StaffCheckinView(discord.ui.View):
    """View para check-in periódico — não-persistente, timeout de 5 minutos."""

    def __init__(self, bot: Any, session_id: int, checkin_id: int) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.session_id = session_id
        self.checkin_id = checkin_id
        self._answered = False

    @discord.ui.button(label="Continuar trabalhando", style=discord.ButtonStyle.success)
    async def continue_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self._answered:
            await interaction.response.send_message("Você já respondeu a este check-in.", ephemeral=True)
            return
        self._answered = True
        self.stop()
        result = await self.bot.staff_timeclock_service.process_checkin_response(
            self.session_id, self.checkin_id, "continue", interaction.user.id
        )
        await interaction.response.send_message(
            embed=self.bot.embeds.success("Check-in Respondido", f"✅ {result}"),
            ephemeral=True,
        )

    @discord.ui.button(label="Pausar", style=discord.ButtonStyle.secondary)
    async def pause_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self._answered:
            await interaction.response.send_message("Você já respondeu a este check-in.", ephemeral=True)
            return
        self._answered = True
        self.stop()
        result = await self.bot.staff_timeclock_service.process_checkin_response(
            self.session_id, self.checkin_id, "pause", interaction.user.id
        )
        await interaction.response.send_message(
            embed=self.bot.embeds.make(title="Check-in Respondido", description=f"⏸️ {result}"),
            ephemeral=True,
        )

    @discord.ui.button(label="Encerrar expediente", style=discord.ButtonStyle.danger)
    async def end_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self._answered:
            await interaction.response.send_message("Você já respondeu a este check-in.", ephemeral=True)
            return
        self._answered = True
        self.stop()
        result = await self.bot.staff_timeclock_service.process_checkin_response(
            self.session_id, self.checkin_id, "end", interaction.user.id
        )
        await interaction.response.send_message(
            embed=self.bot.embeds.make(title="Check-in Respondido", description=f"⏹️ {result}"),
            ephemeral=True,
        )

    async def on_timeout(self) -> None:
        pass


class VoiceWithoutSessionAlertView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este botao dentro do servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Iniciar expediente", style=discord.ButtonStyle.success, custom_id="timeclock:alert:voice_without:start")
    async def start_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.start_session(interaction.user, notes="Iniciado pelo alerta da Central de Ponto.")
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "voice_without_session", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.success("Expediente Iniciado", "Seu expediente foi iniciado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(label="Nao estou trabalhando", style=discord.ButtonStyle.secondary, custom_id="timeclock:alert:voice_without:not_working")
    async def not_working_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.staff_timeclock_service.mark_not_working(interaction.user)
        await interaction.followup.send(embed=self.bot.embeds.make(title="Registrado", description="Voce informou que nao esta trabalhando. O alerta foi resolvido."), ephemeral=True)

    @discord.ui.button(label="Ignorar por enquanto", style=discord.ButtonStyle.secondary, custom_id="timeclock:alert:voice_without:ignore")
    async def ignore_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.staff_timeclock_service.ignore_alert_for_now(interaction.user, "voice_without_session")
        await interaction.followup.send(embed=self.bot.embeds.make(title="Lembrete adiado", description="Se voce continuar na call sem expediente, eu lembro de novo depois."), ephemeral=True)


class LeftVoiceActiveAlertView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este botao dentro do servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pausar expediente", style=discord.ButtonStyle.secondary, custom_id="timeclock:alert:left_voice:pause")
    async def pause_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.pause_session(interaction.user, reason="Pausado pelo alerta de saida da call.")
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "left_voice_with_active_session", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.make(title="Expediente Pausado", description="Seu expediente foi pausado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(label="Encerrar expediente", style=discord.ButtonStyle.danger, custom_id="timeclock:alert:left_voice:end")
    async def end_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.end_session(interaction.user, reason="Encerrado pelo alerta de saida da call.", close_mode="left_voice_button")
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "left_voice_with_active_session", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.success("Expediente Encerrado", "Seu expediente foi encerrado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(label="Continuar externo", style=discord.ButtonStyle.primary, custom_id="timeclock:alert:left_voice:external")
    async def external_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.staff_timeclock_service.set_external_work(interaction.user)
        await interaction.followup.send(embed=self.bot.embeds.success("Trabalho Externo", "Seu expediente continua ativo como trabalho externo."), ephemeral=True)


class PausedInValidVoiceAlertView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este botao dentro do servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Retomar expediente", style=discord.ButtonStyle.success, custom_id="timeclock:alert:paused_valid:resume")
    async def resume_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.resume_session(interaction.user)
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "paused_in_valid_voice", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.success("Expediente Retomado", "Seu expediente foi retomado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(label="Continuar pausado", style=discord.ButtonStyle.secondary, custom_id="timeclock:alert:paused_valid:stay")
    async def stay_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.staff_timeclock_service.ignore_alert_for_now(interaction.user, "paused_in_valid_voice")
        await interaction.followup.send(embed=self.bot.embeds.make(title="Combinado", description="Voce continua pausado por enquanto."), ephemeral=True)

    @discord.ui.button(label="Encerrar expediente", style=discord.ButtonStyle.danger, custom_id="timeclock:alert:paused_valid:end")
    async def end_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.end_session(interaction.user, reason="Encerrado pelo alerta de retorno a call.", close_mode="paused_voice_button")
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "paused_in_valid_voice", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.success("Expediente Encerrado", "Seu expediente foi encerrado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)


class AfkAutoPausedAlertView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Retomar expediente", style=discord.ButtonStyle.success, custom_id="timeclock:alert:afk:resume")
    async def resume_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este botao dentro do servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.resume_session(interaction.user)
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "afk_with_active_session", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.success("Expediente Retomado", "Seu expediente foi retomado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(label="Encerrar expediente", style=discord.ButtonStyle.danger, custom_id="timeclock:alert:afk:end")
    async def end_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este botao dentro do servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.staff_timeclock_service.end_session(interaction.user, reason="Encerrado apos pausa automatica.", close_mode="afk_button")
            await self.bot.staff_timeclock_service.resolve_alert(interaction.guild, interaction.user.id, "afk_with_active_session", "resolved")
            await interaction.followup.send(embed=self.bot.embeds.success("Expediente Encerrado", "Seu expediente foi encerrado."), ephemeral=True)
        except RuntimeError as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Erro", str(exc)), ephemeral=True)

    @discord.ui.button(label="Ver minhas horas", style=discord.ButtonStyle.secondary, custom_id="timeclock:alert:afk:hours")
    async def hours_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este botao dentro do servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = await self.bot.staff_timeclock_service.build_member_hours_embed(interaction.guild, interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)


class StaffTimeclockAdminPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use este painel dentro do servidor.", ephemeral=True)
            return False
        if not self.bot.staff_timeclock_service.has_manage_permission(interaction.user):
            await interaction.response.send_message("Apenas lideranca pode usar este painel.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Atualizar painel", style=discord.ButtonStyle.primary, custom_id="timeclock:admin:refresh")
    async def refresh_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._is_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.staff_timeclock_service.refresh_admin_panel(interaction.guild)
        await interaction.followup.send("Painel atualizado.", ephemeral=True)

    @discord.ui.button(label="Lembrar todos", style=discord.ButtonStyle.secondary, custom_id="timeclock:admin:remind_all")
    async def remind_all_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._is_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        count = await self.bot.staff_timeclock_service.remind_all_voice_without_session(interaction.guild, interaction.user)
        await interaction.followup.send(f"Lembrete enviado para {count} staff(s).", ephemeral=True)

    @discord.ui.button(label="Pendentes", style=discord.ButtonStyle.secondary, custom_id="timeclock:admin:pending")
    async def pending_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._is_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        embed = await self.bot.staff_timeclock_service.build_pending_review_embed(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Ranking semanal", style=discord.ButtonStyle.secondary, custom_id="timeclock:admin:ranking")
    async def ranking_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._is_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        embed = await self.bot.staff_timeclock_service.build_ranking_embed(interaction.guild, "semana")
        await interaction.followup.send(embed=embed, ephemeral=True)


def _fmt(seconds: int) -> str:
    h, rem = divmod(max(0, int(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"
