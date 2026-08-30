from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class DiscordGuildsCog(
    commands.GroupCog,
    group_name="guilda",
    group_description="Sistema social oficial de guildas do Discord",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _safe_error_response(self, interaction: discord.Interaction, message: str) -> None:
        embed = self.bot.embeds.error("Falha na Guilda", message)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as exc:
            if getattr(exc, "code", None) not in {40060, 10062}:
                raise
            self.bot.log.warning(
                "Nao foi possivel responder erro da guilda para interaction %s (code=%s).",
                interaction.id,
                getattr(exc, "code", None),
            )

    @app_commands.command(name="criar", description="Cria uma nova guilda social no Discord")
    @app_commands.guild_only()
    async def criar(self, interaction: discord.Interaction, nome: str, emoji: str, descricao: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.discord_guild_service.create_guild(
            interaction,
            interaction.user,
            name=nome,
            emoji=emoji,
            description=descricao,
        )
        title = "Guilda Oficializada" if result.status == "approved" else "Guilda Enviada"
        await interaction.followup.send(embed=self.bot.embeds.success(title, result.detail), ephemeral=True)

    @app_commands.command(name="perfil", description="Mostra o perfil oficial de uma guilda")
    @app_commands.guild_only()
    async def perfil(self, interaction: discord.Interaction, nome: str | None = None) -> None:
        if not interaction.guild:
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        profile = (
            await self.bot.discord_guild_service.get_profile_by_name(interaction.guild.id, nome)
            if nome
            else await self.bot.discord_guild_service.get_profile_for_member(interaction.guild.id, interaction.user.id)
        )
        if not profile:
            raise RuntimeError("Guilda nao encontrada.")
        embed = await self.bot.discord_guild_service.build_profile_embed(interaction.guild, profile)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="painel", description="Abre o painel privado da lideranca da sua guilda")
    @app_commands.guild_only()
    async def painel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        membership = await self.bot.discord_guild_service.get_profile_for_member(interaction.guild.id, interaction.user.id)
        if not membership:
            raise RuntimeError("Voce nao participa de nenhuma guilda.")
        if str(membership.get("hierarchy")) not in {"leader", "subleader", "officer"}:
            raise RuntimeError("Apenas lideranca da guilda pode abrir este painel.")
        embed = await self.bot.discord_guild_service.build_profile_embed(interaction.guild, membership)
        await interaction.followup.send(
            embed=embed,
            view=self.bot.view_factory.build_discord_guild_leader_panel_view(),
            ephemeral=True,
        )

    @app_commands.command(name="convidar", description="Convida um usuario para a sua guilda")
    @app_commands.guild_only()
    async def convidar(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        invite_id = await self.bot.discord_guild_service.invite_member(interaction, interaction.user, usuario)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Convite Enviado", f"Convite `{invite_id}` enviado para {usuario.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="sair", description="Sai da sua guilda atual")
    @app_commands.guild_only()
    async def sair(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.discord_guild_service.leave_guild(interaction.guild, interaction.user)
        await interaction.followup.send(embed=self.bot.embeds.success("Saida Concluida", result), ephemeral=True)

    @app_commands.command(name="remover", description="Remove um membro da sua guilda")
    @app_commands.guild_only()
    async def remover(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.discord_guild_service.remove_member(interaction.guild, interaction.user, usuario)
        await interaction.followup.send(embed=self.bot.embeds.success("Membro Removido", result), ephemeral=True)

    @app_commands.command(name="promover", description="Altera a hierarquia de um membro da guilda")
    @app_commands.guild_only()
    @app_commands.choices(
        cargo=[
            app_commands.Choice(name="Sub-Lider", value="subleader"),
            app_commands.Choice(name="Oficial", value="officer"),
            app_commands.Choice(name="Membro", value="member"),
        ]
    )
    async def promover(self, interaction: discord.Interaction, usuario: discord.Member, cargo: app_commands.Choice[str]) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.discord_guild_service.update_member_hierarchy(interaction.guild, interaction.user, usuario, cargo.value)
        await interaction.followup.send(embed=self.bot.embeds.success("Hierarquia Atualizada", result), ephemeral=True)

    @app_commands.command(name="transferir_lideranca", description="Transfere a lideranca da guilda para outro membro")
    @app_commands.guild_only()
    async def transferir_lideranca(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.discord_guild_service.transfer_leadership(interaction.guild, interaction.user, usuario)
        await interaction.followup.send(embed=self.bot.embeds.success("Lideranca Transferida", result), ephemeral=True)

    @app_commands.command(name="recrutamento", description="Abre ou fecha o recrutamento da sua guilda")
    @app_commands.guild_only()
    async def recrutamento(self, interaction: discord.Interaction, aberto: bool) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.discord_guild_service.set_recruitment_state(interaction.guild, interaction.user, aberto)
        await interaction.followup.send(embed=self.bot.embeds.success("Recrutamento", result), ephemeral=True)

    @app_commands.command(name="ranking", description="Mostra o ranking atual das guildas")
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self.bot.discord_guild_service.build_ranking_embed(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="publicar_mural", description="Publica ou sincroniza o mural das guildas")
    @app_commands.guild_only()
    async def publicar_mural(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(interaction.user, "manage_discord_guilds"):
            raise app_commands.CheckFailure("Sem permissao para publicar o mural das guildas.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Use este comando dentro do servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self.bot.discord_guild_service.publish_mural(interaction.guild)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Mural Sincronizado", f"O mural das guildas esta em {message.channel.mention}."),
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        root_error = getattr(error, "original", error)
        message = str(root_error).strip() or "Erro inesperado ao processar o comando da guilda."
        await self._safe_error_response(interaction, message[:1800])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiscordGuildsCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))
