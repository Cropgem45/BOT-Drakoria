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
                "✅ Painel Beta Sincronizado",
                f"🎟️ O painel fechado por convite e vagas limitadas foi publicado em {message.channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="cadastrar_influencer", description="Cria ou atualiza um código de influencer para o Programa Beta")
    @app_commands.guild_only()
    @app_commands.describe(
        codigo="Código que os convidados irão informar no painel beta",
        nome="Nome público do influencer",
        usuario="Usuário Discord do influencer, se estiver no servidor",
        vagas="Quantidade de vagas disponíveis para este código; padrão: 5",
    )
    async def cadastrar_influencer(
        self,
        interaction: discord.Interaction,
        codigo: str,
        nome: str,
        usuario: discord.Member | None = None,
        vagas: int | None = None,
    ) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        normalized = await self.bot.beta_program_service.register_influencer_code(
            interaction.guild.id,
            code=codigo,
            influencer_name=nome,
            owner_user_id=usuario.id if usuario else None,
            created_by_id=interaction.user.id,
            slot_limit=vagas,
        )
        owner = usuario.mention if usuario else "sem usuário vinculado"
        slot_label = vagas if vagas is not None else 5
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "✅ Código de Influencer Salvo",
                (
                    f"🎟️ Código `{normalized}` vinculado a **{nome.strip()}** ({owner}).\n"
                    f"📊 Vagas disponíveis: **{slot_label}**.\n"
                    "🧪 Ele já pode ser usado no painel beta."
                ),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ativar_influencer", description="Ativa um código de influencer do Programa Beta")
    @app_commands.guild_only()
    async def ativar_influencer(self, interaction: discord.Interaction, codigo: str) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        normalized = await self.bot.beta_program_service.set_influencer_code_active(interaction.guild.id, codigo, True)
        await interaction.followup.send(
            embed=self.bot.embeds.success("✅ Código Ativado", f"🎟️ O código `{normalized}` voltou a liberar ingresso beta."),
            ephemeral=True,
        )

    @app_commands.command(name="desativar_influencer", description="Desativa um código de influencer do Programa Beta")
    @app_commands.guild_only()
    async def desativar_influencer(self, interaction: discord.Interaction, codigo: str) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        normalized = await self.bot.beta_program_service.set_influencer_code_active(interaction.guild.id, codigo, False)
        await interaction.followup.send(
            embed=self.bot.embeds.success("🚫 Código Desativado", f"🎟️ O código `{normalized}` não libera mais ingresso beta."),
            ephemeral=True,
        )

    @app_commands.command(name="resetar_vagas", description="Reseta vagas usadas de um código ou de todos os influencers")
    @app_commands.guild_only()
    @app_commands.describe(codigo="Código específico para resetar; deixe vazio para resetar todos")
    async def resetar_vagas(self, interaction: discord.Interaction, codigo: str | None = None) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        normalized, changed = await self.bot.beta_program_service.reset_influencer_slots(
            interaction.guild.id,
            codigo,
        )
        if normalized:
            description = f"🔄 As vagas usadas do código `{normalized}` foram zeradas."
        else:
            description = f"🔄 As vagas usadas de **{changed}** código(s) de influencer foram zeradas."
        await interaction.followup.send(
            embed=self.bot.embeds.success("🎟️ Vagas Resetadas", description),
            ephemeral=True,
        )

    @app_commands.command(name="listar_influencers", description="Lista os códigos de influencer do Programa Beta")
    @app_commands.guild_only()
    @app_commands.describe(incluir_inativos="Mostra também códigos desativados")
    async def listar_influencers(self, interaction: discord.Interaction, incluir_inativos: bool = False) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await self.bot.beta_program_service.list_influencer_codes(
            interaction.guild.id,
            include_inactive=incluir_inativos,
        )
        if not rows:
            description = "📭 Nenhum código de influencer cadastrado."
        else:
            lines = []
            for row in rows[:20]:
                owner = f" | <@{row['owner_user_id']}>" if row.get("owner_user_id") else ""
                status = "ativo" if int(row.get("active", 0)) else "inativo"
                slot_limit = int(row.get("slot_limit") or 5)
                used_slots = int(row.get("slot_used") or 0)
                lines.append(
                    f"🎟️ `{row['code']}` - **{row['influencer_name']}** ({status}) "
                    f"| 📊 vagas: **{used_slots}/{slot_limit}**{owner}"
                )
            description = "\n".join(lines)
            if len(rows) > len(lines):
                description += f"\n... e mais {len(rows) - len(lines)} código(s)."
        await interaction.followup.send(
            embed=self.bot.embeds.make(title="🎟️ Influencers Beta", description=description),
            ephemeral=True,
        )

    @app_commands.command(name="stats_influencer", description="Mostra estatísticas de candidaturas por código de influencer")
    @app_commands.guild_only()
    async def stats_influencer(self, interaction: discord.Interaction, codigo: str) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        influencer, stats = await self.bot.beta_program_service.influencer_code_stats(interaction.guild.id, codigo)
        description = (
            f"👤 Influencer: **{influencer['influencer_name']}**\n"
            f"🎟️ Código: `{influencer['code']}`\n"
            f"📌 Status: **{'ativo' if int(influencer.get('active', 0)) else 'inativo'}**\n\n"
            f"📊 Vagas usadas: **{int(influencer.get('slot_used') or 0)}/{int(influencer.get('slot_limit') or 5)}**\n"
            f"🧾 Total: **{stats['total']}**\n"
            f"📝 Em andamento: **{stats['in_progress']}**\n"
            f"⏳ Pendentes: **{stats['pending']}**\n"
            f"✅ Aprovadas: **{stats['approved']}**\n"
            f"🚫 Reprovadas: **{stats['rejected']}**"
        )
        await interaction.followup.send(
            embed=self.bot.embeds.make(title="📊 Estatísticas do Influencer", description=description),
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
        root_error = getattr(error, "original", error)
        if isinstance(root_error, discord.HTTPException) and getattr(root_error, "code", None) in {40060, 10062}:
            self.bot.log.warning(
                "Interacao beta indisponivel no error handler (code=%s).",
                getattr(root_error, "code", None),
            )
            return
        try:
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
        except discord.HTTPException as exc:
            if getattr(exc, "code", None) in {40060, 10062}:
                self.bot.log.warning(
                    "Nao foi possivel responder erro beta para interaction %s (code=%s).",
                    interaction.id,
                    getattr(exc, "code", None),
                )
                return
            raise


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BetaProgramCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))



