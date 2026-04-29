from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from app.services.staff_timeclock_service import ACTIVITIES, CHANNEL_RULE_LABELS, StaffTimeclockService


def _fmt(seconds: int) -> str:
    h, rem = divmod(max(0, int(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


class StaffTimeclockCog(
    commands.GroupCog,
    group_name="ponto",
    group_description="Sistema de jornada da staff — expediente validado por atividade",
):
    jornada = app_commands.Group(name="jornada", description="Controle do expediente pessoal")
    atividade = app_commands.Group(name="atividade", description="Controle de atividade atual")
    relatorio = app_commands.Group(name="relatorio", description="Relatorios e consultas de horas")
    admin = app_commands.Group(name="admin", description="Administracao da Central de Ponto")
    config = app_commands.Group(name="config", description="Configuracoes do sistema de ponto")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def svc(self) -> StaffTimeclockService:
        return self.bot.staff_timeclock_service  # type: ignore[attr-defined]

    # ── /ponto painel ──────────────────────────────────────────────────────────

    @app_commands.command(name="painel", description="Cria ou atualiza o painel de expediente da staff")
    @app_commands.guild_only()
    async def cmd_painel(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode publicar o painel.")
        await interaction.response.defer(ephemeral=True)
        msg = await self.svc.publish_panel(interaction.guild)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Painel Publicado", f"Painel de expediente criado/atualizado em {msg.channel.mention}."),
            ephemeral=True,
        )

    # ── /ponto iniciar ─────────────────────────────────────────────────────────

    @jornada.command(name="iniciar", description="Inicia seu expediente")
    @app_commands.guild_only()
    async def cmd_iniciar(self, interaction: discord.Interaction, observacao: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        session = await self.svc.start_session(interaction.user, notes=observacao)
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Expediente Iniciado",
                f"Seu expediente foi iniciado.\nAtividade inicial: **Não classificado**\nUse `/ponto atividade trocar` para classificar o que está fazendo.",
            ),
            ephemeral=True,
        )

    # ── /ponto pausar ──────────────────────────────────────────────────────────

    @jornada.command(name="pausar", description="Pausa o expediente atual")
    @app_commands.guild_only()
    async def cmd_pausar(self, interaction: discord.Interaction, motivo: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.svc.pause_session(interaction.user, reason=motivo)
        await interaction.followup.send(
            embed=self.bot.embeds.make(title="Expediente Pausado", description="Seu expediente foi pausado. Use `/ponto jornada retomar` para continuar."),
            ephemeral=True,
        )

    # ── /ponto retomar ─────────────────────────────────────────────────────────

    @jornada.command(name="retomar", description="Retoma o expediente pausado")
    @app_commands.guild_only()
    async def cmd_retomar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.svc.resume_session(interaction.user)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Expediente Retomado", "Seu expediente foi retomado."),
            ephemeral=True,
        )

    # ── /ponto encerrar ────────────────────────────────────────────────────────

    @jornada.command(name="encerrar", description="Encerra o expediente atual")
    @app_commands.guild_only()
    async def cmd_encerrar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        motivo: str | None = None,
    ) -> None:
        target = membro or interaction.user
        if target != interaction.user and not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode encerrar expediente de outro membro.")
        await interaction.response.defer(ephemeral=True)
        closed = await self.svc.end_session(target, actor=interaction.user, reason=motivo)
        segments = await self.bot.db.get_session_segments(int(closed["id"]))
        by_act: dict[str, int] = {}
        for seg in segments:
            if seg["ended_at"] and seg["duration_seconds"]:
                by_act[str(seg["activity"])] = by_act.get(str(seg["activity"]), 0) + int(seg["duration_seconds"])
        total = sum(by_act.values())
        act_text = "\n".join(f"— **{a}:** {_fmt(s)}" for a, s in sorted(by_act.items(), key=lambda x: x[1], reverse=True) if s > 0) or "Sem atividades classificadas."
        embed = self.bot.embeds.make(
            title="Expediente Encerrado",
            description=f"Expediente de {target.mention} encerrado.",
            fields=[
                ("Total Validado", _fmt(total), True),
                ("Por Atividade", act_text, False),
            ],
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ponto atividade ───────────────────────────────────────────────────────

    @atividade.command(name="trocar", description="Marca ou troca a atividade atual do expediente")
    @app_commands.guild_only()
    async def cmd_atividade(self, interaction: discord.Interaction, atividade: str) -> None:
        if atividade not in ACTIVITIES:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Atividade inválida", f"Escolha uma das opções: {', '.join(ACTIVITIES)}"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.svc.change_activity(interaction.user, atividade)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Atividade Alterada", f"Atividade atual definida como: **{atividade}**"),
            ephemeral=True,
        )

    @cmd_atividade.autocomplete("atividade")
    async def activity_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=a, value=a) for a in ACTIVITIES if current.lower() in a.lower()][:25]

    # ── /ponto minhas_horas ────────────────────────────────────────────────────

    @relatorio.command(name="minhas_horas", description="Mostra seu relatório individual de horas")
    @app_commands.guild_only()
    async def cmd_minhas_horas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = await self.svc.build_member_hours_embed(interaction.guild, interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ponto staff ───────────────────────────────────────────────────────────

    @relatorio.command(name="staff", description="Relatório individual de outro membro da staff")
    @app_commands.guild_only()
    async def cmd_staff(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode consultar relatório de outros membros.")
        await interaction.response.defer(ephemeral=True)
        embed = await self.svc.build_member_hours_embed(interaction.guild, membro)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ponto status ──────────────────────────────────────────────────────────

    @relatorio.command(name="status", description="Mostra quem está em expediente, pausado ou pendente agora")
    @app_commands.guild_only()
    async def cmd_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = await self.svc.build_status_embed(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ponto ranking ─────────────────────────────────────────────────────────

    @relatorio.command(name="ranking", description="Ranking de horas da staff por período")
    @app_commands.guild_only()
    async def cmd_ranking(self, interaction: discord.Interaction, periodo: str = "semana") -> None:
        await interaction.response.defer(ephemeral=True)
        embed = await self.svc.build_ranking_embed(interaction.guild, periodo)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @cmd_ranking.autocomplete("periodo")
    async def period_autocomplete_ranking(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        options = [("Hoje", "hoje"), ("Semana Atual", "semana"), ("Mês Atual", "mes"), ("Semana Passada", "semana_passada"), ("Mês Passado", "mes_passado")]
        return [app_commands.Choice(name=n, value=v) for n, v in options if current.lower() in n.lower()]

    # ── /ponto relatorio ───────────────────────────────────────────────────────

    @relatorio.command(name="geral", description="Relatório geral da staff por período")
    @app_commands.guild_only()
    async def cmd_relatorio(self, interaction: discord.Interaction, periodo: str = "semana") -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode acessar relatório geral.")
        await interaction.response.defer(ephemeral=True)
        embed = await self.svc.build_general_report_embed(interaction.guild, periodo)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @cmd_relatorio.autocomplete("periodo")
    async def period_autocomplete_relatorio(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        options = [("Hoje", "hoje"), ("Semana Atual", "semana"), ("Mês Atual", "mes"), ("Semana Passada", "semana_passada"), ("Mês Passado", "mes_passado")]
        return [app_commands.Choice(name=n, value=v) for n, v in options if current.lower() in n.lower()]

    # ── /ponto pendentes ───────────────────────────────────────────────────────

    @admin.command(name="pendentes", description="Lista sessões pendentes de validação")
    @app_commands.guild_only()
    async def cmd_pendentes(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode listar pendências.")
        await interaction.response.defer(ephemeral=True)
        sessions = await self.bot.db.list_open_staff_sessions(interaction.guild.id)
        pending = [s for s in sessions if s["status"] == "pending"]
        if not pending:
            await interaction.followup.send(
                embed=self.bot.embeds.make(title="Sessões Pendentes", description="Nenhuma sessão pendente de validação."),
                ephemeral=True,
            )
            return
        lines = [
            f"ID `{s['id']}` | <@{s['user_id']}> | iniciada {StaffTimeclockService._format_dt(StaffTimeclockService._parse_dt(s['started_at']))}"
            for s in pending[:15]
        ]
        await interaction.followup.send(
            embed=self.bot.embeds.make(
                title="Sessões Pendentes de Validação",
                description="\n".join(lines),
                fields=[("Ação", "Use `/ponto admin revisar session_id:ID` para aprovar ou invalidar.", False)],
            ),
            ephemeral=True,
        )

    # ── /ponto revisar ─────────────────────────────────────────────────────────

    @admin.command(name="revisar", description="Aprova ou invalida uma sessão pendente")
    @app_commands.guild_only()
    async def cmd_revisar(
        self,
        interaction: discord.Interaction,
        session_id: int,
        acao: str,
        observacao: str | None = None,
    ) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode revisar sessões.")
        await interaction.response.defer(ephemeral=True)
        result = await self.svc.review_pending_session(interaction.guild, session_id, interaction.user, acao, observacao)
        await interaction.followup.send(embed=self.bot.embeds.success("Revisão Concluída", result), ephemeral=True)

    @cmd_revisar.autocomplete("acao")
    async def review_action_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        options = [("Aprovar", "approve"), ("Invalidar", "invalidate")]
        return [app_commands.Choice(name=n, value=v) for n, v in options if current.lower() in n.lower()]

    # ── /ponto ajustar ─────────────────────────────────────────────────────────

    @admin.command(name="ajustar", description="Adiciona ou remove horas manualmente de um membro da staff")
    @app_commands.guild_only()
    async def cmd_ajustar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        minutos: int,
        motivo: str,
    ) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode ajustar horas.")
        await interaction.response.defer(ephemeral=True)
        seconds = minutos * 60
        await self.svc.admin_adjust(interaction.guild, membro, interaction.user, seconds, motivo)
        sign = "+" if minutos >= 0 else ""
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Horas Ajustadas",
                f"Horas de {membro.mention} ajustadas em {sign}{minutos} minuto(s).\nMotivo: {motivo}",
            ),
            ephemeral=True,
        )

    # ── /ponto configurar_cargo ────────────────────────────────────────────────

    @config.command(name="cargo", description="Adiciona ou remove um cargo como staff no sistema de jornada")
    @app_commands.guild_only()
    async def cmd_configurar_cargo(
        self,
        interaction: discord.Interaction,
        cargo: discord.Role,
        acao: str = "adicionar",
    ) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode configurar cargos de staff.")
        await interaction.response.defer(ephemeral=True)
        if acao == "adicionar":
            await self.bot.db.add_staff_role(interaction.guild.id, cargo.id)
            await interaction.followup.send(
                embed=self.bot.embeds.success("Cargo Configurado", f"{cargo.mention} adicionado como cargo de staff."),
                ephemeral=True,
            )
        elif acao == "remover":
            await self.bot.db.remove_staff_role(interaction.guild.id, cargo.id)
            await interaction.followup.send(
                embed=self.bot.embeds.success("Cargo Removido", f"{cargo.mention} removido dos cargos de staff."),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(embed=self.bot.embeds.error("Ação inválida", "Use 'adicionar' ou 'remover'."), ephemeral=True)

    @cmd_configurar_cargo.autocomplete("acao")
    async def cargo_action_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=n, value=v) for n, v in [("Adicionar", "adicionar"), ("Remover", "remover")] if current.lower() in n.lower()]

    # ── /ponto configurar_canal ────────────────────────────────────────────────

    @config.command(name="canal", description="Define a regra de um canal de voz para o expediente")
    @app_commands.guild_only()
    async def cmd_configurar_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.VoiceChannel,
        tipo: str,
        atividade_sugerida: str | None = None,
    ) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode configurar canais.")
        if tipo not in CHANNEL_RULE_LABELS:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Tipo inválido", f"Use: {', '.join(CHANNEL_RULE_LABELS.keys())}"),
                ephemeral=True,
            )
            return
        if atividade_sugerida and atividade_sugerida not in ACTIVITIES:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Atividade invalida", f"Use uma atividade valida: {', '.join(ACTIVITIES)}"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.set_channel_rule_v3(interaction.guild.id, canal.id, tipo, atividade_sugerida)
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Canal Configurado",
                f"{canal.mention} configurado como: **{CHANNEL_RULE_LABELS[tipo]}**"
                + (f"\nAtividade sugerida: **{atividade_sugerida}**" if atividade_sugerida else ""),
            ),
            ephemeral=True,
        )

    @cmd_configurar_canal.autocomplete("tipo")
    async def canal_tipo_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=label, value=key) for key, label in CHANNEL_RULE_LABELS.items() if current.lower() in label.lower()]

    @cmd_configurar_canal.autocomplete("atividade_sugerida")
    async def canal_activity_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=a, value=a) for a in ACTIVITIES if current.lower() in a.lower()][:25]

    # ── /ponto remover_canal ───────────────────────────────────────────────────

    @config.command(name="remover_canal", description="Remove a regra de um canal de voz")
    @app_commands.guild_only()
    async def cmd_remover_canal(self, interaction: discord.Interaction, canal: discord.VoiceChannel) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode remover regras de canais.")
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.remove_channel_rule(interaction.guild.id, canal.id)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Regra Removida", f"Regra do canal {canal.mention} foi removida."),
            ephemeral=True,
        )

    # ── /ponto listar_canais ───────────────────────────────────────────────────

    @config.command(name="listar_canais", description="Lista os canais configurados para o expediente")
    @app_commands.guild_only()
    async def cmd_listar_canais(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode listar configurações.")
        await interaction.response.defer(ephemeral=True)
        rules = await self.bot.db.get_all_channel_rules(interaction.guild.id)
        if not rules:
            await interaction.followup.send(
                embed=self.bot.embeds.make(title="Canais Configurados", description="Nenhum canal configurado via comando. O sistema usa as regras do `voice_points` na config."),
                ephemeral=True,
            )
            return
        lines = []
        for rule in rules:
            ch = interaction.guild.get_channel(int(rule["channel_id"]))
            ch_ref = ch.mention if ch else "<#" + str(rule["channel_id"]) + ">"
            label = CHANNEL_RULE_LABELS.get(str(rule["rule_type"]), rule["rule_type"])
            lines.append(f"{ch_ref} → **{label}**")
        await interaction.followup.send(
            embed=self.bot.embeds.make(title="Canais Configurados para Expediente", description="\n".join(lines)),
            ephemeral=True,
        )

    # ── /ponto listar_cargos ───────────────────────────────────────────────────

    @config.command(name="listar_cargos", description="Lista os cargos de staff configurados")
    @app_commands.guild_only()
    async def cmd_listar_cargos(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode listar cargos de staff.")
        await interaction.response.defer(ephemeral=True)
        roles = await self.bot.db.get_staff_roles(interaction.guild.id)
        if not roles:
            fallback = self.bot.server_map.voice_point_allowed_role_ids()
            desc = "Nenhum cargo configurado via banco. Usando `voice_points.allowed_role_ids` do config:\n"
            desc += "\n".join(f"<@&{rid}>" for rid in fallback) or "Nenhum."
        else:
            desc = "\n".join(f"<@&{row['role_id']}>" for row in roles)
        await interaction.followup.send(
            embed=self.bot.embeds.make(title="Cargos de Staff Configurados", description=desc),
            ephemeral=True,
        )

    # ── /ponto exportar ────────────────────────────────────────────────────────

    @relatorio.command(name="exportar", description="Exporta relatório da staff em CSV")
    @app_commands.guild_only()
    async def cmd_exportar(self, interaction: discord.Interaction, periodo: str = "semana") -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administração pode exportar relatórios.")
        await interaction.response.defer(ephemeral=True)
        file = await self.svc.export_csv(interaction.guild, periodo)
        await interaction.followup.send(file=file, ephemeral=True)

    @cmd_exportar.autocomplete("periodo")
    async def period_autocomplete_exportar(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        options = [("Hoje", "hoje"), ("Semana Atual", "semana"), ("Mês Atual", "mes"), ("Semana Passada", "semana_passada"), ("Mês Passado", "mes_passado")]
        return [app_commands.Choice(name=n, value=v) for n, v in options if current.lower() in n.lower()]

    # ── /ponto meu_estado ──────────────────────────────────────────────────────

    @jornada.command(name="estado", description="Verifica o estado atual do seu expediente")
    @app_commands.guild_only()
    async def cmd_meu_estado(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        status = await self.svc.describe_member_status(interaction.user)
        embed = self.bot.embeds.make(
            title="Estado do Meu Expediente",
            description=status.summary,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Error handler ──────────────────────────────────────────────────────────

    @admin.command(name="painel", description="Mostra o painel administrativo geral do ponto")
    @app_commands.guild_only()
    async def cmd_admin(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode acessar o painel admin.")
        await interaction.response.defer(ephemeral=True)
        msg = await self.svc.publish_admin_panel(interaction.guild)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Painel Admin Publicado", f"Painel administrativo atualizado em {msg.channel.mention}."),
            ephemeral=True,
        )

    @config.command(name="central", description="Define o canal da Central de Ponto da Staff")
    @app_commands.guild_only()
    async def cmd_configurar_central(self, interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administracao pode configurar a central.")
        await interaction.response.defer(ephemeral=True)
        await self.svc.configure_control_channel(interaction.guild, canal)
        await interaction.followup.send(embed=self.bot.embeds.success("Central Configurada", f"A Central de Ponto da Staff agora e {canal.mention}."), ephemeral=True)

    @config.command(name="logs", description="Define o canal de logs administrativos do ponto")
    @app_commands.guild_only()
    async def cmd_configurar_logs(self, interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas administracao pode configurar logs.")
        await interaction.response.defer(ephemeral=True)
        await self.svc.configure_logs_channel(interaction.guild, canal)
        await interaction.followup.send(embed=self.bot.embeds.success("Logs Configurados", f"Os logs administrativos do ponto agora vao para {canal.mention}."), ephemeral=True)

    @admin.command(name="lembrar", description="Envia lembrete de ponto para uma staff")
    @app_commands.guild_only()
    async def cmd_lembrar(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode enviar lembretes.")
        await interaction.response.defer(ephemeral=True)
        await self.svc.remind_member(interaction.guild, usuario, interaction.user)
        await interaction.followup.send(embed=self.bot.embeds.success("Lembrete Enviado", f"Lembrete enviado para {usuario.mention} na Central de Ponto."), ephemeral=True)

    @admin.command(name="lembrar_todos", description="Lembra todos em call valida sem expediente ativo")
    @app_commands.guild_only()
    async def cmd_lembrar_todos(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode enviar lembretes.")
        await interaction.response.defer(ephemeral=True)
        count = await self.svc.remind_all_voice_without_session(interaction.guild, interaction.user)
        await interaction.followup.send(embed=self.bot.embeds.success("Lembretes Enviados", f"{count} staff(s) lembrado(s)."), ephemeral=True)

    @admin.command(name="forcar_pausa", description="Pausa o expediente de uma staff com motivo obrigatorio")
    @app_commands.guild_only()
    async def cmd_forcar_pausa(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode forcar pausa.")
        await interaction.response.defer(ephemeral=True)
        await self.svc.force_pause(interaction.guild, usuario, interaction.user, motivo)
        await interaction.followup.send(embed=self.bot.embeds.success("Expediente Pausado", f"Expediente de {usuario.mention} pausado.\nMotivo: {motivo}"), ephemeral=True)

    @admin.command(name="forcar_encerrar", description="Encerra o expediente de uma staff com motivo obrigatorio")
    @app_commands.guild_only()
    async def cmd_forcar_encerrar(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode forcar encerramento.")
        await interaction.response.defer(ephemeral=True)
        await self.svc.force_end(interaction.guild, usuario, interaction.user, motivo)
        await interaction.followup.send(embed=self.bot.embeds.success("Expediente Encerrado", f"Expediente de {usuario.mention} encerrado.\nMotivo: {motivo}"), ephemeral=True)

    async def cmd_revisar_pendentes(self, interaction: discord.Interaction) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode revisar pendencias.")
        await interaction.response.defer(ephemeral=True)
        embed = await self.svc.build_pending_review_embed(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="aprovar_pendente", description="Aprova uma sessao pendente")
    @app_commands.guild_only()
    async def cmd_aprovar_pendente(self, interaction: discord.Interaction, session_id: int, observacao: str | None = None) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode revisar pendencias.")
        await interaction.response.defer(ephemeral=True)
        result = await self.svc.review_pending_session(interaction.guild, session_id, interaction.user, "approve", observacao)
        await interaction.followup.send(embed=self.bot.embeds.success("Pendente Aprovado", result), ephemeral=True)

    @admin.command(name="reprovar_pendente", description="Reprova/invalida uma sessao pendente")
    @app_commands.guild_only()
    async def cmd_reprovar_pendente(self, interaction: discord.Interaction, session_id: int, observacao: str | None = None) -> None:
        if not self.svc.has_manage_permission(interaction.user):
            raise app_commands.CheckFailure("Apenas lideranca pode revisar pendencias.")
        await interaction.response.defer(ephemeral=True)
        result = await self.svc.review_pending_session(interaction.guild, session_id, interaction.user, "invalidate", observacao)
        await interaction.followup.send(embed=self.bot.embeds.success("Pendente Reprovado", result), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        root = getattr(error, "original", error)
        msg = str(root)[:500] or "Erro ao processar o comando."
        embed = self.bot.embeds.error("Erro no Sistema de Ponto", msg)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StaffTimeclockCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))
