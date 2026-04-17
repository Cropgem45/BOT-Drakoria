from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class RegistrationCog(
    commands.GroupCog,
    group_name="registro",
    group_description="Operação do registro inicial de membros",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="publicar_painel", description="Publica ou sincroniza o painel de registro inicial")
    @app_commands.guild_only()
    async def publicar_painel(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "publish_panel"):
            raise app_commands.CheckFailure("Sem permissão para publicar o painel de registro.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor oficial.")

        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self.bot.registration_service.publish_panel(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Painel de Registro Sincronizado",
                f"O painel Registrar-se foi publicado em {message.channel.mention}.",
            ),
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha no Registro", str(error)),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no Registro", str(error)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RegistrationCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))




