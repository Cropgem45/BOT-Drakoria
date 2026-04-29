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


def _fmt(seconds: int) -> str:
    h, rem = divmod(max(0, int(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"
