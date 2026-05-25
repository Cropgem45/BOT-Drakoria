from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


async def can_generate_beta_code(bot: commands.Bot, interaction: discord.Interaction) -> bool:
    checker = getattr(bot, "user_has_permission_role", None)
    if checker is None:
        return False
    return bool(await checker(interaction, "generate_beta_code"))


def build_generated_code_embed(
    bot: commands.Bot,
    *,
    interaction: discord.Interaction,
    code: str,
    influencer_name: str,
    owner: discord.Member | discord.User,
    remaining: int,
) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Código Individual Gerado",
        description=(
            f"🎟️ Código: `{code}`\n"
            f"👤 Influencer: **{influencer_name.strip()}** ({owner.mention})\n"
            "📌 Uso: **1 pessoa, 1 única vez**\n"
            f"📊 Convites restantes para gerar: **{remaining}/5**"
        ),
        color=bot.embeds.success_color,
    )
    embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    embed.set_footer(text="Drakoria | Convite beta individual")
    return embed


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

    async def _send_generated_influencer_code(
        self,
        interaction: discord.Interaction,
        *,
        nome: str,
        usuario: discord.Member | None = None,
    ) -> None:
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        if not await can_generate_beta_code(self.bot, interaction):
            raise app_commands.CheckFailure("Apenas Criadores de Conteúdo podem gerar códigos beta.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        owner = usuario or interaction.user
        result = await self.bot.beta_program_service.generate_single_use_influencer_code(
            interaction.guild.id,
            influencer_name=nome,
            owner_user_id=owner.id,
            created_by_id=interaction.user.id,
        )
        await self.bot.beta_program_service.publish_quota_panel(interaction.guild)
        await interaction.followup.send(
            embed=build_generated_code_embed(
                self.bot,
                interaction=interaction,
                code=str(result["code"]),
                influencer_name=nome,
                owner=owner,
                remaining=int(result["remaining"]),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="gerar_codigo", description="Gera um código individual de ingresso beta")
    @app_commands.guild_only()
    @app_commands.describe(
        nome="Nome público do influencer ou campanha",
        usuario="Marque o influencer; se vazio, usa você como dono das 5 vagas",
    )
    async def gerar_codigo(
        self,
        interaction: discord.Interaction,
        nome: str,
        usuario: discord.Member | None = None,
    ) -> None:
        await self._send_generated_influencer_code(interaction, nome=nome, usuario=usuario)

    async def _handle_cadastrar_influencer_raw(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        if not await can_generate_beta_code(self.bot, interaction):
            raise app_commands.CheckFailure("Apenas Criadores de Conteúdo podem gerar códigos beta.")

        options = self._raw_subcommand_options(interaction, {"cadastrar_influencer", "gerar_codigo"})
        if options is None:
            return False

        nome = str(options.get("nome") or "").strip()
        if not nome:
            raise RuntimeError("Informe o nome público do influencer.")

        usuario = await self._resolve_raw_member(interaction.guild, options.get("usuario"))

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        owner = usuario or interaction.user
        result = await self.bot.beta_program_service.generate_single_use_influencer_code(
            interaction.guild.id,
            influencer_name=nome,
            owner_user_id=owner.id,
            created_by_id=interaction.user.id,
        )
        await self.bot.beta_program_service.publish_quota_panel(interaction.guild)
        await interaction.followup.send(
            embed=build_generated_code_embed(
                self.bot,
                interaction=interaction,
                code=str(result["code"]),
                influencer_name=nome,
                owner=owner,
                remaining=int(result["remaining"]),
            ),
            ephemeral=True,
        )
        return True

    @staticmethod
    def _raw_subcommand_options(interaction: discord.Interaction, subcommand_names: set[str]) -> dict[str, Any] | None:
        data = interaction.data if isinstance(interaction.data, dict) else {}
        if data.get("name") in subcommand_names:
            return {
                str(item.get("name")): item.get("value")
                for item in data.get("options") or []
                if isinstance(item, dict) and item.get("name")
            }
        if data.get("name") != "beta_program":
            return None
        for option in data.get("options") or []:
            if not isinstance(option, dict) or option.get("name") not in subcommand_names:
                continue
            return {
                str(item.get("name")): item.get("value")
                for item in option.get("options") or []
                if isinstance(item, dict) and item.get("name")
            }
        return None

    @staticmethod
    async def _resolve_raw_member(guild: discord.Guild, value: Any) -> discord.Member | None:
        if value is None:
            return None
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            return None
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.HTTPException:
            return None

    @app_commands.command(name="ativar_influencer", description="Ativa um código de influencer do Programa Beta")
    @app_commands.guild_only()
    async def ativar_influencer(self, interaction: discord.Interaction, codigo: str) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            raise app_commands.CheckFailure("Sem permissão para gerenciar influencers beta.")
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        normalized = await self.bot.beta_program_service.set_influencer_code_active(interaction.guild.id, codigo, True)
        await self.bot.beta_program_service.publish_quota_panel(interaction.guild)
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
        await self.bot.beta_program_service.publish_quota_panel(interaction.guild)
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
        await self.bot.beta_program_service.publish_quota_panel(interaction.guild)
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
                used_slots = int(row.get("slot_used") or 0)
                usage = "usado" if used_slots > 0 else "pendente"
                lines.append(
                    f"🎟️ `{row['code']}` - **{row['influencer_name']}** ({status}) "
                    f"| 📌 **{usage}**{owner}"
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
            f"📊 Uso do código: **{'usado' if int(influencer.get('slot_used') or 0) > 0 else 'pendente'}**\n"
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
        if isinstance(root_error, app_commands.CommandSignatureMismatch):
            try:
                if await self._handle_cadastrar_influencer_raw(interaction):
                    self.bot.log.warning(
                        "cadastrar_influencer processado por fallback raw apos signature mismatch: interaction=%s data=%s",
                        interaction.id,
                        interaction.data,
                    )
                    return
            except Exception as exc:
                root_error = exc
                error = exc if isinstance(exc, app_commands.AppCommandError) else error
        if isinstance(root_error, discord.HTTPException) and getattr(root_error, "code", None) in {40060, 10062}:
            self.bot.log.warning(
                "Interacao beta indisponivel no error handler (code=%s).",
                getattr(root_error, "code", None),
            )
            return
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha no Programa Beta", str(root_error)),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha no Programa Beta", str(root_error)),
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


class BetaCreatorCodeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="gerar_codigo", description="Gera um código individual de ingresso beta")
    @app_commands.guild_only()
    @app_commands.describe(
        nome="Nome público do influencer ou campanha",
        usuario="Marque o influencer; se vazio, usa você como dono das 5 vagas",
    )
    async def gerar_codigo(
        self,
        interaction: discord.Interaction,
        nome: str,
        usuario: discord.Member | None = None,
    ) -> None:
        if not interaction.guild:
            raise app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        if not await can_generate_beta_code(self.bot, interaction):
            raise app_commands.CheckFailure("Apenas Criadores de Conteúdo podem gerar códigos beta.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        owner = usuario or interaction.user
        result = await self.bot.beta_program_service.generate_single_use_influencer_code(
            interaction.guild.id,
            influencer_name=nome,
            owner_user_id=owner.id,
            created_by_id=interaction.user.id,
        )
        await self.bot.beta_program_service.publish_quota_panel(interaction.guild)
        await interaction.followup.send(
            embed=build_generated_code_embed(
                self.bot,
                interaction=interaction,
                code=str(result["code"]),
                influencer_name=nome,
                owner=owner,
                remaining=int(result["remaining"]),
            ),
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        root_error = getattr(error, "original", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha ao Gerar Código", str(root_error)),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha ao Gerar Código", str(root_error)),
                    ephemeral=True,
                )
        except discord.HTTPException:
            self.bot.log.exception("Falha ao responder erro do comando gerar_codigo.")


async def setup(bot: commands.Bot) -> None:
    guild = discord.Object(id=bot.server_map.guild_id())
    await bot.add_cog(BetaProgramCog(bot), guild=guild)
    await bot.add_cog(BetaCreatorCodeCog(bot), guild=guild)



