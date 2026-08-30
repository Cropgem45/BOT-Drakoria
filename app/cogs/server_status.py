from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class ServerStatusCog(
    commands.GroupCog,
    group_name="server_status",
    group_description="Painel de status do servidor Drakoria",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="publicar_painel", description="Publica ou sincroniza o painel de status do servidor")
    @app_commands.guild_only()
    async def publicar_painel(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(
            interaction.user,
            "manage_server_status",
        ):
            raise app_commands.CheckFailure("Sem permissao para publicar o painel de status.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self.bot.server_status_service.publish_panel(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Painel de Status Sincronizado",
                f"O painel foi publicado em {message.channel.mention} e sera atualizado automaticamente.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="atualizar", description="Forca uma atualizacao imediata do painel de status")
    @app_commands.guild_only()
    async def atualizar(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(
            interaction.user,
            "manage_server_status",
        ):
            raise app_commands.CheckFailure("Sem permissao para atualizar o painel de status.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.bot.server_status_service.refresh_panel(interaction.guild)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Status Atualizado", "A embed do status foi sincronizada agora."),
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha no Status", str(error)),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no Status", str(error)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerStatusCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))
