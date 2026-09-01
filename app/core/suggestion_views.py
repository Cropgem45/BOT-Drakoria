from __future__ import annotations

from typing import Any

import discord


class SuggestionModal(discord.ui.Modal, title="Enviar Sugestão"):
    titulo = discord.ui.TextInput(label="💡 Título", placeholder="Resumo curto da tua ideia", max_length=120)
    sugestao = discord.ui.TextInput(label="📝 Sugestão", style=discord.TextStyle.paragraph, placeholder="Explique o que você quer e por que isso ajudaria.", max_length=3800)

    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            message = await self.bot.suggestion_service.create_suggestion(interaction, title=str(self.titulo.value), body=str(self.sugestao.value))
        except (RuntimeError, discord.HTTPException) as exc:
            self.bot.log.exception("Falha ao criar sugestão", exc_info=exc)
            await interaction.followup.send(embed=self.bot.embeds.error("Sugestão não enviada", "Não foi possível publicar a sugestão. Verifique o canal e as permissões do bot."), ephemeral=True)
            return
        await interaction.followup.send(embed=self.bot.embeds.success("💡 Sugestão enviada", f"Tua sugestão foi publicada em {message.channel.mention} e já tem um tópico para discussão. 💬"), ephemeral=True)


class SuggestionPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Criar sugestão", emoji="💡", style=discord.ButtonStyle.success, custom_id="drakoria:suggestions:panel:create")
    async def create_suggestion_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(SuggestionModal(self.bot))


class SuggestionVoteView(discord.ui.View):
    def __init__(self, bot: Any, counts: dict[str, int] | None = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        counts = counts or {"yes": 0, "no": 0}
        self.yes_button.label = f"Sim ({int(counts.get('yes', 0))})"
        self.no_button.label = f"Não ({int(counts.get('no', 0))})"

    @discord.ui.button(label="Sim (0)", emoji="✅", style=discord.ButtonStyle.success, custom_id="drakoria:suggestions:vote:yes")
    async def yes_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.bot.suggestion_service.register_vote(interaction, "yes")

    @discord.ui.button(label="Não (0)", emoji="❌", style=discord.ButtonStyle.danger, custom_id="drakoria:suggestions:vote:no")
    async def no_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.bot.suggestion_service.register_vote(interaction, "no")
