from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import discord

from app.core.settings import ConfigError, validate_config


@dataclass(slots=True)
class DiagnosticEntry:
    name: str
    status: str
    detail: str


class HealthcheckService:
    CHANNEL_PERMISSIONS = ("view_channel", "send_messages", "embed_links", "read_message_history")
    FILE_CHANNEL_PERMISSIONS = CHANNEL_PERMISSIONS + ("attach_files",)
    TICKET_CATEGORY_PERMISSIONS = ("view_channel", "manage_channels")

    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def run(self, guild: discord.Guild | None) -> list[DiagnosticEntry]:
        entries = [
            self._validate_config_entry(),
            await self._database_entry(),
            await self._views_entry(),
            self._cogs_entry(),
            await self._announcements_runtime_entry(guild),
            await self._registration_runtime_entry(guild),
            await self._member_registration_runtime_entry(guild),
            await self._beta_program_runtime_entry(guild),
            await self._ticket_runtime_entry(guild),
            await self._voice_point_runtime_entry(guild),
            await self._management_dashboard_runtime_entry(guild),
        ]

        if guild is None:
            entries.extend(
                [
                    DiagnosticEntry(
                        "Servidor",
                        "fail",
                        (
                            "A guild configurada nao esta acessivel para o bot no momento. "
                            "Confere se o bot esta no servidor correto e se o ID da guild esta certo."
                        ),
                    ),
                    DiagnosticEntry(
                        "Mapa Operacional",
                        "fail",
                        "Nao foi possivel validar canais, categorias e cargos sem acesso ao servidor configurado.",
                    ),
                    DiagnosticEntry(
                        "Permissoes do Bot",
                        "fail",
                        "Nao foi possivel medir as permissoes do bot porque a guild nao foi localizada.",
                    ),
                ]
            )
            return entries

        entries.append(self._guild_entry(guild))
        entries.append(self._server_map_entry(guild))
        entries.append(self._bot_permissions_entry(guild))
        return entries

    def build_embed(self, guild: discord.Guild | None, entries: list[DiagnosticEntry]) -> discord.Embed:
        total_failures = sum(1 for entry in entries if entry.status == "fail")
        total_warnings = sum(1 for entry in entries if entry.status == "warn")

        if total_failures:
            color = self.bot.embeds.error_color
            verdict = "FALHAS CRITICAS DETECTADAS"
        elif total_warnings:
            color = self.bot.embeds.warning_color
            verdict = "OPERACIONAL COM ALERTAS"
        else:
            color = self.bot.embeds.success_color
            verdict = "PRONTO PARA OPERACAO"

        description = [
            "Relatorio operacional do reino de Drakoria.",
            f"Status geral: **{verdict}**",
            f"Falhas: **{total_failures}** | Alertas: **{total_warnings}** | Itens verificados: **{len(entries)}**",
        ]
        if guild is not None:
            description.append(f"Servidor auditado: **{guild.name}** (`{guild.id}`)")

        embed = self.bot.embeds.make(
            title="Healthcheck da Coroa",
            description="\n".join(description),
            color=color,
        )

        for entry in entries:
            label = {
                "ok": "OK",
                "warn": "ALERTA",
                "fail": "FALHA",
            }[entry.status]
            embed.add_field(
                name=f"[{label}] {entry.name}",
                value=entry.detail[:1024],
                inline=False,
            )

        return embed

    def _validate_config_entry(self) -> DiagnosticEntry:
        try:
            validate_config(self.bot.config)
        except ConfigError as exc:
            return DiagnosticEntry("Configuracao", "fail", str(exc))
        return DiagnosticEntry(
            "Configuracao",
            "ok",
            "O arquivo JSON passou na validacao estrutural e contem os blocos obrigatorios para subir com seguranca.",
        )

    async def _database_entry(self) -> DiagnosticEntry:
        missing_tables: list[str] = []
        for table in self.bot.db.REQUIRED_TABLES:
            if not await self.bot.db.table_exists(table):
                missing_tables.append(table)

        integrity = await self.bot.db.integrity_check()
        if integrity.lower() != "ok" or missing_tables:
            parts = []
            if integrity.lower() != "ok":
                parts.append(f"PRAGMA integrity_check retornou: {integrity}")
            if missing_tables:
                parts.append(f"Tabelas ausentes: {', '.join(missing_tables)}")
            return DiagnosticEntry("Banco de Dados", "fail", " | ".join(parts))

        counts = []
        for table in (
            "points",
            "tickets",
            "announcements",
            "voice_point_sessions",
            "registration_records",
            "member_registration_sessions",
            "beta_tester_applications",
        ):
            counts.append(f"{table}: {await self.bot.db.count_rows(table)}")
        return DiagnosticEntry(
            "Banco de Dados",
            "ok",
            "SQLite inicializado com integridade valida. Registros atuais: " + ", ".join(counts),
        )

    async def _views_entry(self) -> DiagnosticEntry:
        registered_registration_panel = self.bot.registered_persistent_views.get("registration_panel", 0)
        registered_member_registration_panel = self.bot.registered_persistent_views.get("member_registration_panel", 0)
        registered_beta_panel = self.bot.registered_persistent_views.get("beta_program_panel", 0)
        registered_beta_continue = self.bot.registered_persistent_views.get("beta_program_continue", 0)
        registered_beta_reviews = self.bot.registered_persistent_views.get("beta_program_reviews", 0)
        registered_ticket_panel = self.bot.registered_persistent_views.get("ticket_panel", 0)
        registered_ticket = self.bot.registered_persistent_views.get("ticket_controls", 0)
        registered_voice_panel = self.bot.registered_persistent_views.get("voice_point_panel", 0)

        issues: list[str] = []
        if registered_registration_panel != 1:
            issues.append("Painel persistente Registrar-se nao foi registrado")
        if registered_member_registration_panel != 1:
            issues.append("Painel persistente de cadastro nao foi registrado")
        if registered_beta_panel != 1:
            issues.append("Painel persistente do programa beta nao foi registrado")
        if registered_beta_continue not in {0, 1}:
            issues.append("Estado invalido da view de continuidade beta")
        pending_beta_ids = await self.bot.db.list_pending_beta_tester_application_ids(self.bot.server_map.guild_id())
        if registered_beta_reviews != len(pending_beta_ids):
            issues.append(
                "Quantidade de views de revisao beta restauradas diverge das candidaturas pendentes "
                f"({registered_beta_reviews}/{len(pending_beta_ids)})"
            )
        if registered_ticket_panel != 1:
            issues.append("Painel Tickets persistente nao foi registrado")
        if registered_ticket != 1:
            issues.append("Controles persistentes de ticket nao foram registrados")
        if registered_voice_panel != 1:
            issues.append("Painel persistente do bate-ponto por voz nao foi registrado")

        if issues:
            return DiagnosticEntry("Views Persistentes", "fail", " | ".join(issues))

        return DiagnosticEntry(
            "Views Persistentes",
            "ok",
            (
                "As views permanentes foram registradas com sucesso. "
                f"Revisoes beta pendentes restauradas: {registered_beta_reviews}."
            ),
        )

    async def _registration_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        if not self.bot.server_map.registration_panel_enabled():
            return DiagnosticEntry(
                "Registro Inicial",
                "warn",
                "registration_panel.enabled esta false. O fluxo Registrar-se esta desabilitado por configuracao.",
            )

        panel_channel_id = self.bot.server_map.registration_panel_channel_id()
        registered_role_id = self.bot.server_map.registration_registered_role_id()
        visitor_role_id = self.bot.server_map.registration_visitor_role_id()
        log_channel_id = self.bot.server_map.registration_log_channel_id()
        rules_channel_ids = self.bot.server_map.registration_rules_channel_ids()

        if guild is None:
            return DiagnosticEntry(
                "Registro Inicial",
                "fail",
                (
                    "Nao foi possivel validar o sistema Registrar-se sem acesso a guild configurada. "
                    f"IDs configurados: panel={panel_channel_id}, registered_role={registered_role_id}, "
                    f"visitor_role={visitor_role_id}, log={log_channel_id}, rules={rules_channel_ids}."
                ),
            )

        status_lines: list[str] = []
        problems: list[str] = []
        panel_channel = guild.get_channel(panel_channel_id or 0) if panel_channel_id else None
        registered_role = guild.get_role(registered_role_id or 0) if registered_role_id else None
        visitor_role = guild.get_role(visitor_role_id or 0) if visitor_role_id else None
        log_channel = guild.get_channel(log_channel_id or 0) if log_channel_id else None
        if not isinstance(panel_channel, discord.TextChannel):
            problems.append(f"Canal do painel ausente (`{panel_channel_id}`)")
            status_lines.append(f"panel_channel_id `{panel_channel_id}` -> ausente")
        else:
            status_lines.append(f"panel_channel_id `{panel_channel_id}` -> {panel_channel.name} [encontrado]")
        if registered_role is None:
            problems.append(f"Cargo de registro ausente (`{registered_role_id}`)")
            status_lines.append(f"registered_role_id `{registered_role_id}` -> ausente")
        else:
            status_lines.append(f"registered_role_id `{registered_role_id}` -> {registered_role.name} [encontrado]")
        if visitor_role is None:
            problems.append(f"Cargo visitante ausente (`{visitor_role_id}`)")
            status_lines.append(f"visitor_role_id `{visitor_role_id}` -> ausente")
        else:
            status_lines.append(f"visitor_role_id `{visitor_role_id}` -> {visitor_role.name} [encontrado]")
        if not isinstance(log_channel, discord.TextChannel):
            problems.append(f"Canal de log ausente (`{log_channel_id}`)")
            status_lines.append(f"log_channel_id `{log_channel_id}` -> ausente")
        else:
            status_lines.append(f"log_channel_id `{log_channel_id}` -> {log_channel.name} [encontrado]")
        for channel_id in rules_channel_ids:
            rule_channel = guild.get_channel(channel_id)
            if rule_channel is None:
                problems.append(f"Canal de regras ausente (`{channel_id}`)")
                status_lines.append(f"rules_channel_id `{channel_id}` -> ausente")
            else:
                status_lines.append(f"rules_channel_id `{channel_id}` -> {rule_channel.name} [encontrado]")

        warnings: list[str] = []
        state = await self.bot.db.get_registration_panel_message(guild.id)
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if not isinstance(saved_channel, discord.TextChannel):
                problems.append(f"Painel persistido aponta para canal ausente (`{state['channel_id']}`)")
                status_lines.append(
                    f"painel_persistido channel `{state['channel_id']}` / message `{state['message_id']}` -> canal ausente"
                )
            else:
                try:
                    await saved_channel.fetch_message(int(state["message_id"]))
                    status_lines.append(
                        f"painel_persistido channel `{state['channel_id']}` / message `{state['message_id']}` -> encontrado"
                    )
                except discord.NotFound:
                    problems.append(f"Mensagem persistida do painel nao encontrada (`{state['message_id']}`)")
                    status_lines.append(
                        f"painel_persistido channel `{state['channel_id']}` / message `{state['message_id']}` -> mensagem ausente"
                    )
        else:
            status_lines.append("painel_persistido -> nao registrado no banco")
            warnings.append("Painel ainda nao publicado ou sem estado persistido.")

        me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is not None:
            if not me.guild_permissions.manage_roles:
                problems.append("Bot sem permissao `manage_roles` para aplicar/remover cargos")
            if registered_role and me.top_role <= registered_role:
                problems.append("Hierarquia impede aplicar o cargo de registro")
            if self.bot.server_map.registration_remove_visitor_role() and visitor_role and me.top_role <= visitor_role:
                problems.append("Hierarquia impede remover o cargo visitante")

        if problems:
            return DiagnosticEntry(
                "Registro Inicial",
                "fail",
                "Problemas: " + " | ".join(problems) + "\n" + "\n".join(status_lines),
            )

        if warnings:
            return DiagnosticEntry(
                "Registro Inicial",
                "warn",
                "Alertas: " + " | ".join(warnings) + "\n" + "\n".join(status_lines),
            )

        return DiagnosticEntry(
            "Registro Inicial",
            "ok",
            (
                "Registrar-se habilitado e recursos essenciais disponiveis.\n"
                + "\n".join(status_lines)
            ),
        )

    async def _announcements_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        if not self.bot.server_map.announcements_enabled():
            return DiagnosticEntry(
                "Anuncios",
                "warn",
                "announcements.enabled esta false. O modulo de comunicados esta desabilitado.",
            )

        log_channel_id = self.bot.server_map.announcements_log_channel_id()
        allowed_roles = self.bot.server_map.announcements_allowed_role_ids()
        logo_url = self.bot.server_map.announcements_logo_url()
        large_logo_url = self.bot.server_map.announcements_large_logo_url()
        footer = self.bot.server_map.announcements_default_footer()
        color = self.bot.server_map.announcements_embed_color()

        if guild is None:
            return DiagnosticEntry(
                "Anuncios",
                "fail",
                (
                    "Nao foi possivel validar o modulo de anuncios sem acesso a guild configurada. "
                    f"log_channel_id={log_channel_id}, allowed_role_ids={allowed_roles}, logo_configurada={'sim' if logo_url else 'nao'}."
                ),
            )

        status_lines: list[str] = []
        problems: list[str] = []
        warnings: list[str] = []

        log_channel = guild.get_channel(log_channel_id or 0) if log_channel_id else None
        if not isinstance(log_channel, discord.TextChannel):
            problems.append(f"Canal de log de anuncios ausente (`{log_channel_id}`)")
            status_lines.append(f"log_channel_id `{log_channel_id}` -> ausente")
        else:
            status_lines.append(f"log_channel_id `{log_channel_id}` -> {log_channel.name} [encontrado]")

        if not allowed_roles:
            warnings.append("announcements.allowed_role_ids esta vazio; somente administradores poderao publicar.")
            status_lines.append("allowed_role_ids -> vazio")
        else:
            for role_id in allowed_roles:
                role = guild.get_role(role_id)
                if role is None:
                    problems.append(f"Cargo autorizado ausente (`{role_id}`)")
                    status_lines.append(f"allowed_role_id `{role_id}` -> ausente")
                else:
                    status_lines.append(f"allowed_role_id `{role_id}` -> {role.name} [encontrado]")

        if not logo_url:
            problems.append("announcements.logo_url ausente")
            status_lines.append("logo_url -> ausente")
        else:
            status_lines.append("logo_url -> configurada")
        status_lines.append(f"large_logo_url -> {'configurada' if large_logo_url else 'fallback para logo_url'}")

        if not footer.strip():
            problems.append("announcements.default_footer vazio")
            status_lines.append("default_footer -> vazio")
        else:
            status_lines.append("default_footer -> configurado")

        if color is None or color <= 0:
            problems.append("announcements.embed_color invalido")
            status_lines.append(f"embed_color -> invalido ({color})")
        else:
            status_lines.append(f"embed_color -> {color}")

        if problems:
            return DiagnosticEntry("Anuncios", "fail", "Problemas: " + " | ".join(problems) + "\n" + "\n".join(status_lines))
        if warnings:
            return DiagnosticEntry("Anuncios", "warn", "Alertas: " + " | ".join(warnings) + "\n" + "\n".join(status_lines))
        return DiagnosticEntry("Anuncios", "ok", "Modulo de anuncios pronto para operacao.\n" + "\n".join(status_lines))

    async def _beta_program_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        if not self.bot.server_map.beta_program_enabled():
            return DiagnosticEntry("Programa Beta", "warn", "beta_program.enabled esta false.")
        panel_id = self.bot.server_map.beta_program_panel_channel_id()
        app_id = self.bot.server_map.beta_program_application_channel_id()
        card_id = self.bot.server_map.beta_program_card_channel_id()
        log_id = self.bot.server_map.beta_program_log_channel_id()
        role_id = self.bot.server_map.beta_program_role_id()
        if guild is None:
            return DiagnosticEntry(
                "Programa Beta",
                "fail",
                f"Guild ausente para validar beta_program. panel={panel_id} app={app_id} card={card_id} role={role_id}",
            )
        issues: list[str] = []
        lines: list[str] = []
        for label, target_id in (
            ("panel_channel_id", panel_id),
            ("application_channel_id", app_id),
            ("card_channel_id", card_id),
            ("log_channel_id", log_id),
        ):
            channel = guild.get_channel(target_id or 0) if target_id else None
            if not isinstance(channel, discord.TextChannel):
                issues.append(f"{label} ausente (`{target_id}`)")
                lines.append(f"{label} `{target_id}` -> ausente")
            else:
                lines.append(f"{label} `{target_id}` -> {channel.name} [ok]")
        role = guild.get_role(role_id or 0) if role_id else None
        if role is None:
            issues.append(f"beta_role_id ausente (`{role_id}`)")
            lines.append(f"beta_role_id `{role_id}` -> ausente")
        else:
            lines.append(f"beta_role_id `{role_id}` -> {role.name} [ok]")
        pending = await self.bot.db.list_beta_tester_applications(guild.id, status="pending", limit=200)
        lines.append(f"pendentes no banco -> {len(pending)}")
        if issues:
            return DiagnosticEntry("Programa Beta", "fail", " | ".join(issues) + "\n" + "\n".join(lines))
        return DiagnosticEntry("Programa Beta", "ok", "\n".join(lines))

    async def _member_registration_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        if not self.bot.server_map.member_registration_enabled():
            return DiagnosticEntry(
                "Cadastro Oficial",
                "warn",
                "member_registration.enabled esta false. O cadastro oficial esta desabilitado.",
            )

        panel_channel_id = self.bot.server_map.member_registration_panel_channel_id()
        member_role_id = self.bot.server_map.member_registration_member_role_id()
        log_channel_id = self.bot.server_map.member_registration_log_channel_id()
        minimum_age = self.bot.server_map.member_registration_minimum_age()

        if guild is None:
            return DiagnosticEntry(
                "Cadastro Oficial",
                "fail",
                (
                    "Nao foi possivel validar o cadastro oficial sem acesso a guild configurada. "
                    f"panel={panel_channel_id}, member_role={member_role_id}, log={log_channel_id}, minimum_age={minimum_age}."
                ),
            )

        problems: list[str] = []
        lines: list[str] = []
        panel_channel = guild.get_channel(panel_channel_id or 0) if panel_channel_id else None
        member_role = guild.get_role(member_role_id or 0) if member_role_id else None
        log_channel = guild.get_channel(log_channel_id or 0) if log_channel_id else None

        if not isinstance(panel_channel, discord.TextChannel):
            problems.append(f"Canal do painel ausente (`{panel_channel_id}`)")
            lines.append(f"panel_channel_id `{panel_channel_id}` -> ausente")
        else:
            lines.append(f"panel_channel_id `{panel_channel_id}` -> {panel_channel.name} [encontrado]")
        if member_role is None:
            problems.append(f"Cargo de membro ausente (`{member_role_id}`)")
            lines.append(f"member_role_id `{member_role_id}` -> ausente")
        else:
            lines.append(f"member_role_id `{member_role_id}` -> {member_role.name} [encontrado]")
        if not isinstance(log_channel, discord.TextChannel):
            problems.append(f"Canal de log ausente (`{log_channel_id}`)")
            lines.append(f"log_channel_id `{log_channel_id}` -> ausente")
        else:
            lines.append(f"log_channel_id `{log_channel_id}` -> {log_channel.name} [encontrado]")
        lines.append(f"minimum_age -> `{minimum_age}`")

        state = await self.bot.db.get_member_registration_panel_message(guild.id)
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if not isinstance(saved_channel, discord.TextChannel):
                problems.append(f"Painel persistido do cadastro aponta para canal ausente (`{state['channel_id']}`)")
            else:
                try:
                    await saved_channel.fetch_message(int(state["message_id"]))
                    lines.append(
                        f"painel_persistido channel `{state['channel_id']}` / message `{state['message_id']}` -> encontrado"
                    )
                except discord.NotFound:
                    problems.append(f"Mensagem persistida do cadastro ausente (`{state['message_id']}`)")
        else:
            lines.append("painel_persistido -> nao publicado")

        me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is not None:
            if not me.guild_permissions.manage_roles:
                problems.append("Bot sem `manage_roles` para aplicar cargo de membro")
            if self.bot.server_map.member_registration_rename_member_on_success() and not me.guild_permissions.manage_nicknames:
                problems.append("Bot sem `manage_nicknames` para alterar nickname automaticamente")
            if member_role is not None and me.top_role <= member_role:
                problems.append("Hierarquia impede aplicar cargo de membro")

        if problems:
            return DiagnosticEntry(
                "Cadastro Oficial",
                "fail",
                "Problemas: " + " | ".join(problems) + "\n" + "\n".join(lines),
            )

        return DiagnosticEntry(
            "Cadastro Oficial",
            "ok",
            "Cadastro oficial pronto para operacao.\n" + "\n".join(lines),
        )

    async def _ticket_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        ticket_types = self.bot.server_map.ticket_types()
        if guild is None:
            return DiagnosticEntry(
                "Tickets",
                "fail",
                (
                    "Nao foi possivel validar o sistema de tickets sem acesso ao servidor configurado. "
                    f"Tipos configurados: {len(ticket_types)}."
                ),
            )

        panel_channel_id = self.bot.server_map.ticket_panel_channel_id()
        category_id = self.bot.server_map.ticket_category_id()
        log_channel_id = self.bot.server_map.ticket_log_channel_id()
        transcript_channel_id = self.bot.server_map.ticket_transcript_channel_id()
        support_role_ids = self.bot.server_map.ticket_support_role_ids()

        problems: list[str] = []
        for label, target_id, resolver in (
            ("Painel Tickets", panel_channel_id, guild.get_channel),
            ("Categoria de tickets", category_id, guild.get_channel),
            ("Canal de logs", log_channel_id, guild.get_channel),
            ("Canal de transcricoes", transcript_channel_id, guild.get_channel),
        ):
            if target_id and resolver(int(target_id)) is None:
                problems.append(f"{label} ausente (`{target_id}`)")
        for role_id in support_role_ids:
            if guild.get_role(int(role_id)) is None:
                problems.append(f"Cargo de suporte ausente (`{role_id}`)")

        open_tickets = await self.bot.ticket_service.list_open_tickets(guild)
        panel_state = await self.bot.db.get_ticket_panel_message(guild.id)
        if panel_state:
            saved_channel = guild.get_channel(int(panel_state["channel_id"]))
            if not isinstance(saved_channel, discord.TextChannel):
                problems.append(f"Painel persistido aponta para canal ausente (`{panel_state['channel_id']}`)")

        if problems:
            return DiagnosticEntry("Tickets", "fail", " | ".join(problems))

        resolved_types = ", ".join(
            f"{ticket_type['emoji']} {ticket_type['label']} (`{ticket_type['key']}`)" for ticket_type in ticket_types
        )
        return DiagnosticEntry(
            "Tickets",
            "ok",
            (
                f"Sistema de tickets pronto com {len(ticket_types)} categorias configuradas, "
                f"{len(open_tickets)} tickets abertos no banco e painel persistente "
                f"{'registrado' if panel_state else 'ainda nao publicado'}.\n"
                f"Tipos: {resolved_types}"
            ),
        )

    async def _voice_point_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        if not self.bot.server_map.voice_points_enabled():
            return DiagnosticEntry("Bate-Ponto por Voz", "warn", "O sistema existe na configuracao, mas foi marcado como desabilitado.")

        active_sessions = await self.bot.db.count_active_voice_point_sessions(self.bot.server_map.guild_id())
        valid_channels = self.bot.server_map.voice_point_valid_channel_ids()
        allowed_roles = self.bot.server_map.voice_point_allowed_role_ids()
        if guild is None:
            return DiagnosticEntry(
                "Bate-Ponto por Voz",
                "fail",
                (
                    f"Sistema habilitado, porem a guild nao foi localizada. "
                    f"Calls configuradas: {len(valid_channels)} | Cargos autorizados: {len(allowed_roles)}."
                ),
            )

        missing_channels = [channel_id for channel_id in valid_channels if guild.get_channel(channel_id) is None]
        missing_roles = [role_id for role_id in allowed_roles if guild.get_role(role_id) is None]
        if missing_channels or missing_roles:
            details = []
            if missing_channels:
                details.append(f"calls ausentes: {missing_channels}")
            if missing_roles:
                details.append(f"cargos ausentes: {missing_roles}")
            return DiagnosticEntry("Bate-Ponto por Voz", "fail", " | ".join(details))

        audits = await self.bot.point_service.audit_active_sessions(guild)
        stale_count = sum(1 for audit in audits if audit.status == "stale")
        warn_count = sum(1 for audit in audits if audit.status == "warn")
        if stale_count:
            return DiagnosticEntry(
                "Bate-Ponto por Voz",
                "fail",
                (
                    f"Sistema habilitado com {len(valid_channels)} calls validas e {len(allowed_roles)} cargos autorizados, "
                    f"mas existem {stale_count} sessoes stale aguardando intervencao."
                ),
            )
        if warn_count:
            return DiagnosticEntry(
                "Bate-Ponto por Voz",
                "warn",
                (
                    f"Sistema habilitado com {len(valid_channels)} calls validas, "
                    f"{len(allowed_roles)} cargos autorizados e {warn_count} sessoes em divergencia leve."
                ),
            )

        return DiagnosticEntry(
            "Bate-Ponto por Voz",
            "ok",
            (
                f"Sistema habilitado com {len(valid_channels)} calls validas, "
                f"{len(allowed_roles)} cargos autorizados e {active_sessions} sessoes ativas no banco."
            ),
        )

    async def _management_dashboard_runtime_entry(self, guild: discord.Guild | None) -> DiagnosticEntry:
        if not self.bot.server_map.management_dashboard_enabled():
            return DiagnosticEntry("Dashboard da Gestao", "warn", "management_dashboard.enabled esta false.")

        channel_id = self.bot.server_map.management_dashboard_channel_id()
        role_ids = self.bot.server_map.management_dashboard_allowed_role_ids()
        if guild is None:
            return DiagnosticEntry(
                "Dashboard da Gestao",
                "fail",
                f"Guild ausente para validar dashboard. channel={channel_id} roles={role_ids}",
            )
        channel = guild.get_channel(channel_id or 0) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return DiagnosticEntry("Dashboard da Gestao", "fail", f"Canal do dashboard ausente (`{channel_id}`).")
        missing_roles = [role_id for role_id in role_ids if guild.get_role(role_id) is None]
        if missing_roles:
            return DiagnosticEntry("Dashboard da Gestao", "fail", f"Cargos autorizados ausentes: {missing_roles}")
        state = await self.bot.db.get_management_dashboard_message(guild.id)
        published = "sim" if state else "nao"
        return DiagnosticEntry(
            "Dashboard da Gestao",
            "ok",
            (
                f"Canal `{channel.id}` ({channel.name}) encontrado | roles autorizados: {len(role_ids)} | "
                f"publicado: {published} | weekly={self.bot.server_map.management_dashboard_show_weekly_metrics()} | "
                f"monthly={self.bot.server_map.management_dashboard_show_monthly_metrics()} | alerts={self.bot.server_map.management_dashboard_show_alerts()}."
            ),
        )

    def _cogs_entry(self) -> DiagnosticEntry:
        expected = {
            "AdministrationCog",
            "BetaProgramCog",
            "MemberRegistrationCog",
            "PointCog",
            "AnnouncementCog",
            "TicketCog",
        }
        loaded = set(self.bot.cogs.keys())
        missing = sorted(expected - loaded)
        if missing:
            return DiagnosticEntry(
                "Cogs",
                "fail",
                "Os seguintes modulos nao foram carregados no startup: " + ", ".join(missing),
            )
        return DiagnosticEntry("Cogs", "ok", "Todos os cogs essenciais foram carregados e registrados na tree.")

    def _guild_entry(self, guild: discord.Guild) -> DiagnosticEntry:
        if guild.id != self.bot.server_map.guild_id():
            return DiagnosticEntry(
                "Servidor",
                "fail",
                (
                    "O bot esta ligado a um servidor diferente do configurado. "
                    f"Config: {self.bot.server_map.guild_id()} | Atual: {guild.id}"
                ),
            )
        return DiagnosticEntry("Servidor", "ok", f"Guild alvo localizada com sucesso: {guild.name} (`{guild.id}`).")

    def _server_map_entry(self, guild: discord.Guild) -> DiagnosticEntry:
        missing_channels = self._missing_targets(
            guild,
            self.bot.config.get("channels", {}),
            resolver=guild.get_channel,
            label="canal",
        )
        missing_categories = self._missing_targets(
            guild,
            self.bot.config.get("categories", {}),
            resolver=guild.get_channel,
            label="categoria",
        )
        missing_roles = self._missing_targets(
            guild,
            self.bot.config.get("roles", {}),
            resolver=guild.get_role,
            label="cargo",
        )
        missing_logs = self._missing_targets(
            guild,
            self.bot.config.get("logs", {}).get("channels", {}),
            resolver=guild.get_channel,
            label="canal de log",
        )

        details = missing_channels + missing_categories + missing_roles + missing_logs
        if details:
            return DiagnosticEntry(
                "Mapa Operacional",
                "fail",
                "IDs configurados mas nao encontrados no servidor: " + " | ".join(details),
            )
        voice_channel_details = []
        for channel_id in self.bot.server_map.voice_point_valid_channel_ids():
            channel = guild.get_channel(channel_id)
            group = self.bot.server_map.voice_point_channel_group(channel_id)
            voice_channel_details.append(f"`{channel_id}` -> {getattr(channel, 'name', 'ausente')} [{group}]")
        ticket_details = [
            f"painel `{self.bot.server_map.ticket_panel_channel_id()}` -> {getattr(guild.get_channel(self.bot.server_map.ticket_panel_channel_id()), 'name', 'ausente')}",
            f"categoria `{self.bot.server_map.ticket_category_id()}` -> {getattr(guild.get_channel(self.bot.server_map.ticket_category_id()), 'name', 'ausente')}",
            f"logs `{self.bot.server_map.ticket_log_channel_id()}` -> {getattr(guild.get_channel(self.bot.server_map.ticket_log_channel_id()), 'name', 'ausente')}",
            f"transcricoes `{self.bot.server_map.ticket_transcript_channel_id()}` -> {getattr(guild.get_channel(self.bot.server_map.ticket_transcript_channel_id()), 'name', 'ausente')}",
        ]
        management_detail = (
            f"dashboard `{self.bot.server_map.management_dashboard_channel_id()}` -> "
            f"{getattr(guild.get_channel(self.bot.server_map.management_dashboard_channel_id()), 'name', 'ausente')}"
        )
        member_registration_detail = (
            f"cadastro painel `{self.bot.server_map.member_registration_panel_channel_id()}` -> "
            f"{getattr(guild.get_channel(self.bot.server_map.member_registration_panel_channel_id()), 'name', 'ausente')} | "
            f"cargo `{self.bot.server_map.member_registration_member_role_id()}` -> "
            f"{getattr(guild.get_role(self.bot.server_map.member_registration_member_role_id()), 'name', 'ausente')}"
        )
        return DiagnosticEntry(
            "Mapa Operacional",
            "ok",
            (
                "Todos os canais, categorias, logs e cargos configurados foram encontrados no servidor. "
                f"Tickets: {' | '.join(ticket_details)}. "
                f"Calls do expediente: {' | '.join(voice_channel_details[:6])}. "
                f"Gestao: {management_detail}. "
                f"Cadastro: {member_registration_detail}. "
                f"Beta: painel `{self.bot.server_map.beta_program_panel_channel_id()}` -> "
                f"{getattr(guild.get_channel(self.bot.server_map.beta_program_panel_channel_id()), 'name', 'ausente')}"
            ) if voice_channel_details else
            "Todos os canais, categorias, logs e cargos configurados foram encontrados no servidor.",
        )

    def _bot_permissions_entry(self, guild: discord.Guild) -> DiagnosticEntry:
        me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is None:
            return DiagnosticEntry(
                "Permissoes do Bot",
                "fail",
                "Nao foi possivel localizar o proprio bot entre os membros da guild.",
            )

        problems: list[str] = []
        channel_specs = {
            "boas-vindas": (self.bot.server_map.channel("welcome"), self.CHANNEL_PERMISSIONS),
            "log de tickets": (self.bot.server_map.log_channel("tickets"), self.FILE_CHANNEL_PERMISSIONS),
            "log de pontos": (self.bot.server_map.log_channel("points"), self.CHANNEL_PERMISSIONS),
            "log de anuncios": (self.bot.server_map.announcements_log_channel_id(), self.CHANNEL_PERMISSIONS),
            "painel do bate-ponto": (self.bot.server_map.voice_point_panel_channel_id(), self.CHANNEL_PERMISSIONS),
            "relatorios da staff": (self.bot.server_map.voice_point_report_channel_id(), self.CHANNEL_PERMISSIONS),
            "log do bate-ponto": (self.bot.server_map.voice_point_log_channel_id(), self.CHANNEL_PERMISSIONS),
            "dashboard da gestao": (self.bot.server_map.management_dashboard_channel_id(), self.CHANNEL_PERMISSIONS),
            "painel de tickets": (self.bot.server_map.ticket_panel_channel_id(), self.CHANNEL_PERMISSIONS),
            "log de transcricoes": (self.bot.server_map.ticket_transcript_channel_id(), self.FILE_CHANNEL_PERMISSIONS),
            "painel Registrar-se": (self.bot.server_map.registration_panel_channel_id(), self.CHANNEL_PERMISSIONS),
            "log de registro": (self.bot.server_map.registration_log_channel_id(), self.CHANNEL_PERMISSIONS),
            "painel de cadastro": (self.bot.server_map.member_registration_panel_channel_id(), self.CHANNEL_PERMISSIONS),
            "log de cadastro": (self.bot.server_map.member_registration_log_channel_id(), self.CHANNEL_PERMISSIONS),
            "painel beta": (self.bot.server_map.beta_program_panel_channel_id(), self.CHANNEL_PERMISSIONS),
            "candidaturas beta": (self.bot.server_map.beta_program_application_channel_id(), self.CHANNEL_PERMISSIONS),
            "carteirinhas beta": (self.bot.server_map.beta_program_card_channel_id(), self.CHANNEL_PERMISSIONS),
            "log beta": (self.bot.server_map.beta_program_log_channel_id(), self.CHANNEL_PERMISSIONS),
        }

        for label, (channel_id, permission_names) in channel_specs.items():
            channel = guild.get_channel(channel_id) if channel_id else None
            if isinstance(channel, discord.abc.GuildChannel):
                missing = self._missing_permissions(channel.permissions_for(me), permission_names)
                if missing:
                    problems.append(f"{label}: faltam {', '.join(missing)}")

        ticket_category_id = self.bot.server_map.ticket_category_id()
        ticket_category = guild.get_channel(ticket_category_id) if ticket_category_id else None
        if isinstance(ticket_category, discord.CategoryChannel):
            missing = self._missing_permissions(ticket_category.permissions_for(me), self.TICKET_CATEGORY_PERMISSIONS)
            if missing:
                problems.append(f"categoria de tickets: faltam {', '.join(missing)}")

        guild_missing = self._missing_permissions(
            guild.me.guild_permissions if guild.me else me.guild_permissions,
            ("manage_roles", "manage_channels"),
        )
        if guild_missing:
            problems.append("escopo da guild: faltam " + ", ".join(guild_missing))

        if problems:
            return DiagnosticEntry(
                "Permissoes do Bot",
                "fail",
                "Permissoes insuficientes para operacao completa: " + " | ".join(problems),
            )

        return DiagnosticEntry(
            "Permissoes do Bot",
            "ok",
            "O bot possui as permissoes essenciais para publicar paineis, logs, tickets e cargos operacionais.",
        )

    @staticmethod
    def _missing_targets(
        guild: discord.Guild,
        mapping: dict[str, Any],
        *,
        resolver: Any,
        label: str,
    ) -> list[str]:
        missing: list[str] = []
        for key, raw_id in mapping.items():
            try:
                target_id = int(raw_id)
            except (TypeError, ValueError):
                missing.append(f"{label} {key} com ID invalido")
                continue
            if resolver(target_id) is None:
                missing.append(f"{label} {key} (`{target_id}`)")
        return missing

    @staticmethod
    def _missing_permissions(permission_set: discord.Permissions, permission_names: tuple[str, ...]) -> list[str]:
        return [name for name in permission_names if not getattr(permission_set, name, False)]


