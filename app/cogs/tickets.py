from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class TicketCog(
    commands.GroupCog,
    group_name="ticket",
    group_description="Ferramentas oficiais de suporte",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="painel", description="Publica ou sincroniza o Painel Tickets")
    @app_commands.guild_only()
    async def painel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Este comando só pode ser executado dentro do servidor oficial.")
        if not self.bot.permission_service.has(interaction.user, "manage_tickets"):
            raise app_commands.CheckFailure("Você não possui permissão para publicar o Painel Tickets.")
        await interaction.response.defer(ephemeral=True)
        try:
            message = await self.bot.ticket_service.publish_panel(interaction.guild, actor=interaction.user)
        except RuntimeError as exc:
            raise app_commands.CheckFailure(str(exc)) from exc
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Painel Tickets Sincronizado",
                f"O Painel Tickets foi publicado ou atualizado em {message.channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="abrir", description="Abre um ticket manualmente pelo tipo configurado")
    @app_commands.guild_only()
    async def abrir(self, interaction: discord.Interaction, tipo: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Este comando só pode ser usado dentro do servidor oficial.")
        await interaction.response.defer(ephemeral=True)
        try:
            channel = await self.bot.ticket_service.open_ticket(interaction.user, tipo, origin="Comando /ticket abrir")
        except RuntimeError as exc:
            raise app_commands.CheckFailure(str(exc)) from exc
        await interaction.followup.send(
            embed=self.bot.embeds.success("Ticket Criado", f"Teu atendimento foi aberto em {channel.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="fechar", description="Fecha o ticket atual com motivo administrativo")
    @app_commands.guild_only()
    async def fechar(self, interaction: discord.Interaction, motivo: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Este comando só pode ser usado dentro do servidor oficial.")
        if not self.bot.permission_service.has(interaction.user, "manage_tickets"):
            raise app_commands.CheckFailure("Você não possui permissão para encerrar tickets.")
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.ticket_service.close_ticket(interaction, motivo)
        except RuntimeError as exc:
            raise app_commands.CheckFailure(str(exc)) from exc
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Ticket Encerrado",
                (
                    f"O ticket foi encerrado com sucesso.\n"
                    f"Status da DM ao usuário: **{result.dm_status}**.\n"
                    f"Comportamento final: **{result.close_behavior}**."
                ),
            ),
            ephemeral=True,
        )
        if isinstance(interaction.channel, discord.TextChannel):
            if result.close_behavior == "archive":
                ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
                await interaction.channel.edit(
                    name=f"encerrado-{interaction.channel.name}"[:90],
                    reason=f"Ticket encerrado por {interaction.user}",
                )
                if ticket:
                    author = interaction.guild.get_member(int(ticket["user_id"])) if interaction.guild else None
                    if author is not None:
                        await interaction.channel.set_permissions(
                            author,
                            overwrite=discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=False,
                                read_message_history=True,
                                attach_files=False,
                            ),
                            reason="Arquivamento administrativo do ticket",
                        )
                    for role_id in self.bot.server_map.ticket_support_role_ids():
                        role = interaction.guild.get_role(int(role_id)) if interaction.guild else None
                        if role is not None:
                            await interaction.channel.set_permissions(
                                role,
                                overwrite=discord.PermissionOverwrite(
                                    view_channel=True,
                                    send_messages=False,
                                    read_message_history=True,
                                    attach_files=False,
                                    manage_messages=True,
                                ),
                                reason="Arquivamento administrativo do ticket",
                            )
            else:
                await interaction.channel.delete(reason=f"Ticket encerrado por {interaction.user}")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        message = str(getattr(error, "original", error) or error)
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha no sistema de tickets", message),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no sistema de tickets", message),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))




