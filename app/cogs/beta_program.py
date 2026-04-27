from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class BetaProgramCog(
    commands.GroupCog,
    group_name="beta_program",
    group_description="Gestao do Programa Oficial de Beta Testers",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="publicar_painel", description="Publica ou sincroniza o painel do Programa Beta")
    @app_commands.guild_only()
    async def publicar_painel(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para publicar o painel beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self.bot.beta_program_service.publish_panel(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Painel Beta Sincronizado",
                f"O painel oficial foi publicado em {message.channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="reemitir_carteirinha", description="Reemite a carteirinha de um Beta Tester aprovado")
    @app_commands.guild_only()
    @app_commands.describe(
        usuario="Usuário aprovado no Programa Beta",
        candidatura_id="ID da candidatura aprovada; deixe vazio para usar a mais recente",
        emissao="Texto opcional de emissão preservada, ex: 27/04/2026 03:45 UTC",
        ingresso="Texto opcional de ingresso preservado, ex: 24/04/2026",
        codigo_autenticacao="Código opcional já emitido; deixe vazio para recalcular pelo protocolo",
    )
    async def reemitir_carteirinha(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        candidatura_id: int | None = None,
        emissao: str | None = None,
        ingresso: str | None = None,
        codigo_autenticacao: str | None = None,
    ) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para reemitir carteirinhas beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.beta_program_service.reissue_tester_card(
            interaction.guild,
            usuario,
            actor=interaction.user,
            application_id=candidatura_id,
            issued_label=emissao,
            joined_label=ingresso,
            auth_code=codigo_autenticacao,
        )
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Carteirinha Reemitida",
                (
                    f"Candidatura `BT-{result['application_id']:06d}` reemitida para {usuario.mention}.\n"
                    f"DM: {'enviada' if result['dm_sent'] else 'falhou'}\n"
                    f"Canal <#{result['channel_id']}>: {'enviado' if result['channel_sent'] else 'falhou'}"
                ),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="reemitir_todas_carteirinhas",
        description="Reenvia as carteirinhas de todos os Beta Testers aprovados",
    )
    @app_commands.guild_only()
    async def reemitir_todas_carteirinhas(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para reemitir carteirinhas beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.bot.beta_program_service.reissue_all_tester_cards(
            interaction.guild,
            actor=interaction.user,
        )
        details: list[str] = []
        for item in result["results"][:10]:
            if item["status"] == "ok":
                details.append(
                    f"<@{item['user_id']}> | BT-{item['application_id']:06d} | "
                    f"DM: {'ok' if item.get('dm_sent') else 'falhou'} | "
                    f"Canal: {'ok' if item.get('channel_sent') else 'falhou'}"
                )
            elif item["status"] == "member_not_found":
                details.append(f"<@{item['user_id']}> | BT-{item['application_id']:06d} | membro não encontrado")
            else:
                details.append(f"<@{item['user_id']}> | BT-{item['application_id']:06d} | erro: {item.get('error', '-')}")

        description = (
            f"Processadas: **{result['total']}**\n"
            f"Sucesso: **{result['success_count']}**\n"
            f"Falhas: **{result['fail_count']}**"
        )
        if details:
            description += "\n\n" + "\n".join(details)
            if result["total"] > len(details):
                description += f"\n... e mais {result['total'] - len(details)} registro(s)."

        await interaction.followup.send(
            embed=self.bot.embeds.success("Reemissão em Lote Concluída", description),
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha no Programa Beta", str(error)),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no Programa Beta", str(error)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BetaProgramCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))



