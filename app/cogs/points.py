from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class PointCog(
    commands.GroupCog,
    group_name="pontos",
    group_description="Quadro de méritos e expediente da staff",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="estado", description="Consulta o estado do expediente por voz")
    @app_commands.guild_only()
    async def status_expediente(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        target = membro or interaction.user
        if target != interaction.user and not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Somente a administração pode consultar o expediente de outros membros.")
        status = await self.bot.point_service.describe_member_status(target)
        await interaction.response.send_message(
            embed=self.bot.embeds.make(
                title="Estado do Expediente",
                description=f"{target.mention}\n\n{status.summary}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="encerrar", description="Encerra manualmente um expediente por voz")
    @app_commands.guild_only()
    async def encerrar_expediente(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        observacao: str | None = None,
    ) -> None:
        target = membro or interaction.user
        if target != interaction.user and not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Somente a administração pode encerrar o expediente de outro membro.")
        session = await self.bot.point_service.manual_close(target, interaction.user, close_reason=observacao)
        await interaction.response.send_message(
            embed=self.bot.embeds.success(
                "Expediente Encerrado",
                f"A sessão **** de {target.mention} foi encerrada e o relatório foi enviado.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="listar", description="Lista as sessoes ativas do expediente por voz")
    @app_commands.guild_only()
    async def listar_expedientes(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para listar sessões ativas.")
        sessions = await self.bot.point_service.list_active_session_rows(interaction.guild)
        if not sessions:
            await interaction.response.send_message(
                embed=self.bot.embeds.make(
                    title="Sessões Ativas",
                    description="Nenhum expediente ativo foi encontrado no momento.",
                ),
                ephemeral=True,
            )
            return
        lines = []
        for session in sessions[:15]:
            state = "Tolerancia" if session["grace_started_at"] else self.bot.point_service._group_label(self.bot.point_service._resolve_runtime_group(session))
            duration = self.bot.point_service._format_duration(self.bot.point_service._live_total_seconds(session))
            lines.append(f"<@{session['user_id']}> | sessão `` | `{state}` | `{duration}`")
        await interaction.response.send_message(
            embed=self.bot.embeds.make(
                title="Sessões Ativas do Expediente",
                description="Relação administrativa das sessões ativas monitoradas por voz.\n\n" + "\n".join(lines),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="tolerancias", description="Lista membros atualmente em tolerancia")
    @app_commands.guild_only()
    async def listar_tolerancias(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para listar tolerâncias.")
        sessions = await self.bot.point_service.list_grace_session_rows(interaction.guild)
        if not sessions:
            await interaction.response.send_message(
                embed=self.bot.embeds.make(
                    title="Janelas de Tolerância",
                    description="Nenhum membro se encontra em tolerância no momento.",
                ),
                ephemeral=True,
            )
            return
        lines = []
        for session in sessions[:15]:
            deadline = self.bot.point_service._format_dt(self.bot.point_service._parse_dt(session["grace_deadline_at"]))
            lines.append(f"<@{session['user_id']}> | sessão `` | prazo `{deadline}`")
        await interaction.response.send_message(
            embed=self.bot.embeds.make(
                title="Membros em Tolerância",
                description="Expedientes atualmente na janela oficial de retorno.\n\n" + "\n".join(lines),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="diagnosticar", description="Diagnostica o estado do expediente de um membro")
    @app_commands.guild_only()
    async def diagnosticar_expediente(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para diagnosticar membros.")
        status = await self.bot.point_service.describe_member_status(membro)
        audits = await self.bot.point_service.audit_active_sessions(interaction.guild)
        detail = next((audit.detail for audit in audits if int(audit.session["user_id"]) == membro.id), "Nenhum alerta operacional encontrado.")
        embed = self.bot.embeds.make(
            title="Diagnóstico de Expediente",
            description=f"{membro.mention}\n\n{status.summary}",
            fields=[("Auditoria", detail, False)],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="limpar", description="Encerra com seguranca uma sessao stale do expediente")
    @app_commands.guild_only()
    async def limpar_sessao_stale(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        sessao_id: int | None = None,
        motivo: str | None = None,
    ) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para limpar sessões stale.")
        if membro is None and sessao_id is None:
            raise app_commands.CheckFailure("Informe um membro ou um ID de sessão para limpar.")
        session = await self.bot.point_service.cleanup_stale_session(
            interaction.guild,
            member=membro,
            session_id=sessao_id,
            actor=interaction.user,
            reason=motivo,
        )
        await interaction.response.send_message(
            embed=self.bot.embeds.warning(
                "Sessão Limpa com Segurança",
                f"A sessão **** foi encerrada por limpeza operacional e o relatório foi registrado.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="staff", description="Relatorio premium de expediente e tickets por staff")
    @app_commands.guild_only()
    async def relatorio_staff(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para consultar relatório de staff.")
        embeds = await self.bot.point_service.build_staff_report_embeds(interaction.guild, membro)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    @app_commands.command(name="gestao", description="Publica ou sincroniza o dashboard executivo da gestao")
    @app_commands.guild_only()
    async def quadro_gestao(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para acessar o quadro da gestão.")
        message = await self.bot.point_service.publish_management_dashboard(interaction.guild, actor=interaction.user)
        await interaction.response.send_message(
            embed=self.bot.embeds.success("Dashboard Sincronizado", f"Quadro executivo atualizado em {message.channel.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="resumo", description="Resumo executivo de horas e tickets no periodo semanal ou mensal")
    @app_commands.guild_only()
    async def resumo_executivo(self, interaction: discord.Interaction, periodo: str) -> None:
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            raise app_commands.CheckFailure("Não possuis autoridade para consultar resumo executivo.")
        summary = await self.bot.point_service.resumo_executivo(interaction.guild, periodo)
        embed = self.bot.embeds.make(
            title=f"Resumo Executivo ({periodo.title()})",
            description=(
                f"Horas totais da equipe: **{self.bot.point_service._format_duration(summary['total_seconds'])}**\n"
                f"Tickets resolvidos: **{summary['total_tickets']}**\n"
                f"Média de horas por staff: **{self.bot.point_service._format_duration(summary['average_seconds_per_staff'])}**\n"
                f"Média de tickets por staff: **{summary['average_tickets_per_staff']:.2f}**"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @resumo_executivo.autocomplete("periodo")
    async def resumo_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        options = [("Semanal", "semanal"), ("Mensal", "mensal")]
        return [app_commands.Choice(name=name, value=value) for name, value in options if current.lower() in name.lower()]

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha no Sistema de Pontos", str(error)),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no Sistema de Pontos", str(error)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PointCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))


