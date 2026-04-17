from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class MemberRegistrationCog(
    commands.GroupCog,
    group_name="cadastro",
    group_description="Operacao do cadastro oficial de membros",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="status", description="Consulta o status cadastral de um membro")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        target = membro or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Membro Inválido", "Não foi possível localizar o membro solicitado."),
                ephemeral=True,
            )
            return
        if target.id != interaction.user.id and not self.bot.permission_service.has(interaction.user, "view_server_map"):
            raise app_commands.CheckFailure("Sem permissão para consultar cadastro de outros membros.")

        status, session = await self.bot.member_registration_service.describe_status(interaction.guild_id, target.id)
        if session is None:
            embed = self.bot.embeds.make(
                title="Status do Cadastro",
                description=f"{target.mention} ainda não possui sessão de cadastro oficial registrada.",
            )
        else:
            embed = self.bot.embeds.make(
                title="Status do Cadastro",
                description=f"Consulta cadastral de {target.mention}.",
            )
            embed.add_field(
                name="Resumo Técnico",
                value=self.bot.member_registration_service.format_session_for_embed(session)[:1024],
                inline=False,
            )
        embed.add_field(name="Status Atual", value=status, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="publicar_painel", description="Publica ou sincroniza o painel oficial de cadastro")
    @app_commands.guild_only()
    async def publicar_painel(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "publish_panel"):
            raise app_commands.CheckFailure("Sem permissão para publicar o painel de cadastro.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando só pode ser executado no servidor oficial.")

        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self.bot.member_registration_service.publish_panel(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Painel de Cadastro Sincronizado",
                f"O painel oficial de cadastro está ativo em {message.channel.mention}.",
            ),
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha no Cadastro", str(error)),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no Cadastro", str(error)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemberRegistrationCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))




