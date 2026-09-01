from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app.core.suggestion_views import SuggestionModal


class SuggestionCog(commands.GroupCog, group_name="sugestoes", group_description="Central de sugestões da comunidade"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="painel", description="Publica ou sincroniza a Central de Sugestões")
    @app_commands.guild_only()
    async def painel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Este comando só pode ser usado dentro do servidor oficial.")
        if not self.bot.permission_service.has(interaction.user, "publish_panel"):
            raise app_commands.CheckFailure("Você não possui permissão para publicar painéis.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            message = await self.bot.suggestion_service.publish_panel(interaction.guild)
        except RuntimeError as exc:
            raise app_commands.CheckFailure(str(exc)) from exc
        await interaction.followup.send(embed=self.bot.embeds.success("Central de Sugestões Publicada", f"O painel foi sincronizado em {message.channel.mention}."), ephemeral=True)


class SuggestionShortcutCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="sugestao", description="Abre diretamente o formulário de sugestões")
    @app_commands.guild_only()
    async def sugestao(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SuggestionModal(self.bot))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SuggestionCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))
    await bot.add_cog(SuggestionShortcutCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))
