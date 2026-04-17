from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import discord


TICKET_STATUS_FLOW = ("open", "in_progress", "waiting_user", "closed")


@dataclass(slots=True)
class TicketCloseResult:
    transcript_text: str
    transcript_filename: str
    transcript_channel_id: int | None
    transcript_message_id: int | None
    dm_status: str
    close_behavior: str


class TicketService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    def ticket_types(self) -> list[dict[str, str]]:
        return [
            {
                "key": str(ticket_type["key"]).strip().lower(),
                "label": str(ticket_type["label"]).strip(),
                "description": str(ticket_type["description"]).strip(),
                "emoji": str(ticket_type["emoji"]).strip(),
            }
            for ticket_type in self.bot.server_map.ticket_types()
        ]

    def ticket_type(self, key: str) -> dict[str, str]:
        ticket_type = self.bot.server_map.ticket_type(key)
        if not ticket_type:
            raise RuntimeError("O tipo de suporte solicitado não existe na configuração atual.")
        return {
            "key": str(ticket_type["key"]).strip().lower(),
            "label": str(ticket_type["label"]).strip(),
            "description": str(ticket_type["description"]).strip(),
            "emoji": str(ticket_type["emoji"]).strip(),
        }

    def status_label(self, status: str) -> str:
        return self.bot.server_map.ticket_status_label(status)

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _format_timestamp(self, value: str | None) -> str:
        parsed = self._parse_timestamp(value)
        if parsed is None:
            return "Não registrado"
        return discord.utils.format_dt(parsed, style="f")

    def _format_duration(self, seconds: int) -> str:
        total = max(int(seconds), 0)
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes or hours:
            parts.append(f"{minutes}min")
        parts.append(f"{secs}s")
        return " ".join(parts)

    def _ticket_slug(self, ticket_type_key: str) -> str:
        mapping = {
            "bug_report": "bug",
            "report": "denuncia",
            "general_question": "duvida",
            "account_issue": "conta",
            "general_support": "suporte",
        }
        return mapping.get(ticket_type_key, "suporte")

    def _safe_member_slug(self, member: discord.Member) -> str:
        raw = "".join(char.lower() if char.isalnum() else "-" for char in member.display_name)
        compact = "-".join(part for part in raw.split("-") if part)
        return compact[:32] or str(member.id)

    def _resolve_support_roles(self, guild: discord.Guild) -> list[discord.Role]:
        roles: list[discord.Role] = []
        missing: list[int] = []
        for role_id in self.bot.server_map.ticket_support_role_ids():
            role = guild.get_role(role_id)
            if role is None:
                missing.append(role_id)
                continue
            roles.append(role)
        if missing:
            raise RuntimeError(
                "Há cargos de suporte configurados que não foram encontrados no servidor.\n"
                f"IDs ausentes: {missing}"
            )
        return roles

    def _ticket_channel_name(self, member: discord.Member, ticket_type_key: str) -> str:
        return f"ticket-{self._ticket_slug(ticket_type_key)}-{self._safe_member_slug(member)}"[:90]

    def build_panel_embed(self, guild: discord.Guild | None) -> discord.Embed:
        type_lines = [
            f"{ticket_type['emoji']} **{ticket_type['label']}**\n{ticket_type['description']}"
            for ticket_type in self.ticket_types()
        ]
        description = (
            "Use este painel para abrir solicitações de suporte.\n"
            "Selecione a categoria correta antes de abrir o ticket. Todo atendimento é registrado e auditável.\n"
            "Uso indevido deste canal pode resultar em medidas disciplinares. 🙂"
        )
        embed = self.bot.embeds.make(title="🎫 Painel Tickets", description=description)
        embed.add_field(name="Categorias de Suporte", value="\n\n".join(type_lines), inline=False)
        embed.add_field(
            name="Regras do Atendimento",
            value=(
                "Abra tickets apenas para demandas reais, com descrição objetiva e completa.\n"
                "Quando um staff assumir o ticket, o histórico ficará vinculado ao registro oficial do ticket."
            ),
            inline=False,
        )
        return embed

    def build_ticket_embed(self, ticket: dict[str, Any], guild: discord.Guild) -> discord.Embed:
        member = guild.get_member(int(ticket["user_id"]))
        assigned_staff = guild.get_member(int(ticket["assigned_staff_id"])) if ticket.get("assigned_staff_id") else None
        ticket_type = self.ticket_type(str(ticket["ticket_type"]))
        embed = self.bot.embeds.make(
            title=f"Atendimento Oficial ",
            description=(
                "Este canal foi criado para suporte técnico e administrativo.\n"
                "Mantenham a comunicação objetiva, respeitosa e focada na resolução."
            ),
        )
        embed.add_field(name="Autor", value=member.mention if member else f"indisponível", inline=True)
        embed.add_field(name="Tipo", value=f"{ticket_type['emoji']} {ticket_type['label']}", inline=True)
        embed.add_field(name="Status", value=self.status_label(str(ticket["status"])), inline=True)
        embed.add_field(
            name="Staff Responsável",
            value=assigned_staff.mention if assigned_staff else "Ainda não assumido",
            inline=True,
        )
        embed.add_field(name="Aberto em", value=self._format_timestamp(ticket.get("opened_at")), inline=True)
        embed.add_field(name="Canal", value=f"<#{ticket['channel_id']}>", inline=True)
        embed.add_field(
            name="Instruções",
            value=(
                "O autor deve detalhar o caso com clareza, incluindo contexto e evidências quando possível."
            ),
            inline=False,
        )
        if ticket.get("status_detail"):
            embed.add_field(name="Observação Operacional", value=str(ticket["status_detail"]), inline=False)
        return embed

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        panel_channel_id = self.bot.server_map.ticket_panel_channel_id()
        channel = guild.get_channel(panel_channel_id) if panel_channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError(
                "O canal oficial do Painel Tickets não foi localizado. Corrija `tickets.panel_channel_id` antes de publicar."
            )

        embed = self.build_panel_embed(guild)
        state = await self.bot.db.get_ticket_panel_message(guild.id)
        message: discord.Message | None = None
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=self.bot.view_factory.build_ticket_panel_view())
                except discord.NotFound:
                    message = None
        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_ticket_panel_view())
            await self.bot.db.save_ticket_panel_message(guild.id, channel.id, message.id)

        if actor is not None:
            await self._log(
                "Painel Tickets Atualizado",
                f"{actor.mention} publicou ou sincronizou o Painel Tickets.",
                fields=[("Canal", channel.mention, True), ("Mensagem", f"indisponível", True)],
            )
        return message

    async def send_panel_entrypoint(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Contexto inválido",
                    "Tickets só podem ser abertos dentro do servidor configurado.",
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=self.build_panel_embed(interaction.guild),
            view=self.bot.view_factory.build_ticket_panel_view(),
            ephemeral=True,
        )

    async def open_ticket(self, member: discord.Member, ticket_type_key: str, *, origin: str) -> discord.TextChannel:
        guild = member.guild
        ticket_type = self.ticket_type(ticket_type_key)

        existing = await self.bot.db.get_open_ticket_by_user(guild.id, member.id)
        if existing and self.bot.server_map.ticket_allow_one_open_per_user():
            channel = guild.get_channel(int(existing["channel_id"]))
            if isinstance(channel, discord.TextChannel):
                await self._log(
                    "Bloqueio de Ticket Duplicado",
                    f"{member.mention} tentou abrir um novo ticket sem encerrar o atendimento anterior.",
                    fields=[
                        ("Ticket Atual", channel.mention, True),
                        ("Tipo Solicitado", ticket_type["label"], True),
                    ],
                    level="warn",
                )
                raise RuntimeError(f"Já existe um ticket aberto em {channel.mention}.")
            await self.bot.db.mark_ticket_stale(
                int(existing["channel_id"]),
                self.bot.user.id if self.bot.user else member.id,
                "Ticket marcado como stale porque o canal anterior não existe mais.",
            )
            await self._log(
                "Ticket Stale Saneado",
                f"O ticket anterior de {member.mention} foi encerrado por inconsistência antes da abertura de um novo atendimento.",
                fields=[("Canal ausente", f"indisponível", True)],
                level="warn",
            )

        category_id = self.bot.server_map.ticket_category_id()
        category = guild.get_channel(category_id) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            panel_channel = guild.get_channel(self.bot.server_map.ticket_panel_channel_id() or 0)
            if isinstance(panel_channel, discord.TextChannel) and isinstance(panel_channel.category, discord.CategoryChannel):
                category = panel_channel.category
                await self._log(
                    "Fallback de Categoria de Tickets",
                    "A categoria configurada para tickets não foi encontrada. O sistema usou a categoria do canal do Painel Tickets.",
                    fields=[
                        ("Categoria usada", f"{category.name}", False),
                        ("ID configurado", f"indisponível", True),
                    ],
                    level="warn",
                )

        if not isinstance(category, discord.CategoryChannel):
            me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
            if me and me.guild_permissions.manage_channels:
                category = await guild.create_category_channel(
                    name="tickets-suporte",
                    reason="Autocorreção: categoria de tickets ausente na configuração",
                )
                await self._log(
                    "Categoria de Tickets Criada Automaticamente",
                    "A categoria de tickets não existia no servidor e foi criada automaticamente para manter o atendimento operacional.",
                    fields=[("Categoria criada", f"{category.name}", False)],
                    level="warn",
                )

        if not isinstance(category, discord.CategoryChannel):
            raise RuntimeError(
                "A categoria de tickets configurada não foi localizada e não foi possível aplicar fallback automático. "
                "Revise `tickets.category_id`."
            )

        support_roles = self._resolve_support_roles(guild)
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }
        for role in support_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_messages=True,
            )

        ticket_channel = await guild.create_text_channel(
            name=self._ticket_channel_name(member, ticket_type["key"]),
            category=category,
            overwrites=overwrites,
            topic=(
                f"Ticket oficial de suporte | autor={member.id} | tipo={ticket_type['key']} | "
                f"origem={origin}"
            ),
            reason=f"Abertura de ticket do tipo {ticket_type['key']} por {member}",
        )
        try:
            await ticket_channel.move(category=category, end=True, sync_permissions=False)
        except discord.HTTPException:
            await self._log(
                "Ordenação de Ticket não aplicada",
                "O canal foi criado, mas não foi possível posicioná-lo no final da categoria.",
                fields=[
                    ("Canal", ticket_channel.mention, True),
                    ("Categoria", f"{category.name}", False),
                ],
                level="warn",
            )

        ticket_id = await self.bot.db.create_ticket(guild.id, member.id, ticket_channel.id, ticket_type["key"])
        ticket = await self.bot.db.get_ticket_by_id(ticket_id)
        if not ticket:
            raise RuntimeError("O ticket foi criado no canal, mas o registro não foi localizado no banco.")

        panel_message = await ticket_channel.send(
            content=member.mention,
            embed=self.build_ticket_embed(ticket, guild),
            view=self.bot.view_factory.build_ticket_control_view(),
        )
        await self.bot.db.set_ticket_panel_message(ticket_channel.id, panel_message.id)

        await self._log(
            "Ticket Aberto",
            f"{member.mention} abriu um novo ticket de suporte.",
            fields=[
                ("Ticket", f"`#{ticket_id}`", True),
                ("Tipo", f"{ticket_type['emoji']} {ticket_type['label']}", True),
                ("Canal", ticket_channel.mention, True),
                ("Origem", origin, True),
            ],
        )
        return ticket_channel

    async def refresh_ticket_panel(self, channel: discord.TextChannel) -> discord.Message:
        ticket = await self.bot.db.get_ticket_by_channel(channel.id)
        if not ticket:
            raise RuntimeError("Este canal não está vinculado a nenhum ticket oficial.")

        message: discord.Message | None = None
        panel_message_id = ticket.get("panel_message_id")
        if panel_message_id:
            try:
                message = await channel.fetch_message(int(panel_message_id))
            except discord.NotFound:
                message = None

        embed = self.build_ticket_embed(ticket, channel.guild)
        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_ticket_control_view())
            await self.bot.db.set_ticket_panel_message(channel.id, message.id)
        else:
            await message.edit(embed=embed, view=self.bot.view_factory.build_ticket_control_view())
        return message

    async def claim_ticket(self, interaction: discord.Interaction) -> dict[str, Any]:
        if not isinstance(interaction.channel, discord.TextChannel):
            raise RuntimeError("Os controles de ticket exigem um canal de texto válido.")
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            raise RuntimeError("Este canal não está vinculado a nenhum ticket oficial.")
        if str(ticket["status"]) == "closed":
            raise RuntimeError("Este ticket já foi encerrado e não pode mais ser assumido.")
        assigned_staff_id = ticket.get("assigned_staff_id") or ticket.get("claimed_by")
        if assigned_staff_id and int(assigned_staff_id) != interaction.user.id:
            raise RuntimeError(f"Este ticket já está sob responsabilidade de <@{assigned_staff_id}>.")

        await self.bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        await self.refresh_ticket_panel(interaction.channel)
        await self._log(
            "Ticket Assumido",
            f"{interaction.user.mention} assumiu o atendimento do ticket oficial.",
            fields=[
                ("Ticket", f"``", True),
                ("Canal", interaction.channel.mention, True),
                ("Autor", f"<@{ticket['user_id']}>", True),
            ],
        )
        return ticket

    async def transfer_ticket(
        self,
        interaction: discord.Interaction,
        target_member_id: int,
    ) -> dict[str, Any]:
        if not isinstance(interaction.channel, discord.TextChannel):
            raise RuntimeError("A transferência só pode ser executada dentro do canal do ticket.")
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            raise RuntimeError("Este canal não está vinculado a nenhum ticket oficial.")
        if str(ticket["status"]) == "closed":
            raise RuntimeError("Tickets encerrados não podem mais ser transferidos.")

        target_member = interaction.guild.get_member(target_member_id) if interaction.guild else None
        if target_member is None:
            raise RuntimeError("O membro informado para receber a transferência não foi encontrado no servidor.")
        if not self.bot.permission_service.has(target_member, "manage_tickets"):
            raise RuntimeError("O membro indicado não possui autoridade operacional para assumir tickets.")

        previous_staff_id = int(ticket["assigned_staff_id"]) if ticket.get("assigned_staff_id") else None
        await self.bot.db.transfer_ticket(interaction.channel.id, previous_staff_id, target_member.id)
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        await self.refresh_ticket_panel(interaction.channel)
        await self._log(
            "Ticket Transferido",
            f"{interaction.user.mention} transferiu a conduicao do ticket.",
            fields=[
                ("Ticket", f"``", True),
                ("Anterior", f"<@{previous_staff_id}>" if previous_staff_id else "Sem responsável anterior", True),
                ("Novo Responsável", target_member.mention, True),
            ],
        )
        return ticket

    async def set_status(
        self,
        interaction: discord.Interaction,
        status: str,
        detail: str | None = None,
    ) -> dict[str, Any]:
        if status not in TICKET_STATUS_FLOW:
            raise RuntimeError("O status solicitado não existe no fluxo oficial de tickets.")
        if status == "closed":
            raise RuntimeError("Use o fluxo de encerramento para concluir um ticket.")
        if not isinstance(interaction.channel, discord.TextChannel):
            raise RuntimeError("O status do ticket só pode ser alterado dentro de um canal de texto válido.")

        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            raise RuntimeError("Este canal não está vinculado a nenhum ticket oficial.")
        if str(ticket["status"]) == "closed":
            raise RuntimeError("Não é possível alterar o status de um ticket encerrado.")

        await self.bot.db.set_ticket_status(interaction.channel.id, status, interaction.user.id, detail)
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        await self.refresh_ticket_panel(interaction.channel)
        await self._log(
            "Estado do Ticket Atualizado",
            f"{interaction.user.mention} atualizou o estado operacional do ticket.",
            fields=[
                ("Ticket", f"``", True),
                ("Novo Status", self.status_label(status), True),
                ("Canal", interaction.channel.mention, True),
            ],
            extra_detail=detail,
        )
        return ticket

    async def close_ticket(self, interaction: discord.Interaction, reason: str) -> TicketCloseResult:
        if not isinstance(interaction.channel, discord.TextChannel):
            raise RuntimeError("Esta ação só pode ser executada dentro de um canal de ticket.")

        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            raise RuntimeError("Este canal não está registrado como ticket oficial.")
        if str(ticket["status"]) == "closed":
            raise RuntimeError("Este ticket já foi encerrado anteriormente.")
        if not isinstance(interaction.user, discord.Member):
            raise RuntimeError("Contexto inválido para encerramento do ticket.")
        is_staff = self.bot.permission_service.has(interaction.user, "manage_tickets")
        is_author = int(ticket["user_id"]) == interaction.user.id
        if not is_staff and not is_author:
            raise RuntimeError("Somente a staff responsável ou o autor do ticket pode encerrar este atendimento.")

        transcript_text = await self.transcript(interaction.channel, ticket)
        transcript_filename = f"ticket-{ticket['id']}-transcricao.md"
        transcript_channel_id: int | None = None
        transcript_message_id: int | None = None

        transcript_channel = interaction.guild.get_channel(self.bot.server_map.ticket_transcript_channel_id())
        transcript_file = discord.File(BytesIO(transcript_text.encode("utf-8")), filename=transcript_filename)
        if isinstance(transcript_channel, discord.TextChannel):
            transcript_message = await transcript_channel.send(
                embed=self.bot.embeds.make(
                    title=f"Transcricao do Ticket ",
                    description="Registro administrativo arquivado para auditoria interna.",
                ),
                file=transcript_file,
            )
            transcript_channel_id = transcript_channel.id
            transcript_message_id = transcript_message.id

        await self.bot.db.close_ticket(
            interaction.channel.id,
            interaction.user.id,
            reason,
            transcript_name=transcript_filename,
            transcript_channel_id=transcript_channel_id,
            transcript_message_id=transcript_message_id,
        )
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        dm_status = await self._send_close_dm(interaction.channel.guild, ticket, transcript_text, transcript_filename)
        await self.bot.db.set_ticket_dm_status(interaction.channel.id, dm_status)

        await self._log(
            "Ticket Encerrado",
            f"{interaction.user.mention} encerrou um ticket oficial de suporte.",
            fields=[
                ("Ticket", f"``", True),
                ("Canal", interaction.channel.mention, True),
                ("Tipo", self.ticket_type(str(ticket['ticket_type']))["label"], True),
                ("DM ao usuário", dm_status, True),
            ],
            extra_detail=reason,
        )
        return TicketCloseResult(
            transcript_text=transcript_text,
            transcript_filename=transcript_filename,
            transcript_channel_id=transcript_channel_id,
            transcript_message_id=transcript_message_id,
            dm_status=dm_status,
            close_behavior=self.bot.server_map.ticket_close_behavior(),
        )

    async def transcript(self, channel: discord.TextChannel, ticket: dict[str, Any]) -> str:
        opened_at = self._format_timestamp(ticket.get("opened_at"))
        closed_at = self._format_timestamp(self._utcnow().isoformat())
        assigned_staff_id = ticket.get("assigned_staff_id") or ticket.get("claimed_by")
        header = [
            f"# Transcricao do Ticket ",
            "",
            f"- Canal: #{channel.name}",
            f"- Autor: <@{ticket['user_id']}>",
            f"- Tipo: {self.ticket_type(str(ticket['ticket_type']))['label']}",
            f"- Responsável: <@{assigned_staff_id}>" if assigned_staff_id else "- Responsável: não atribuído",
            f"- Aberto em: {opened_at}",
            f"- Encerrado em: {closed_at}",
            "",
            "## Histórico",
            "",
        ]
        lines = header
        async for message in channel.history(limit=None, oldest_first=True):
            created = discord.utils.format_dt(message.created_at.replace(tzinfo=UTC), style="f")
            author_name = getattr(message.author, "display_name", str(message.author))
            content = message.content.strip() or "[sem texto]"
            attachment_lines = [attachment.url for attachment in message.attachments]
            embed_marker = "[conteúdo incorporado]" if message.embeds else ""
            suffix_parts = []
            if attachment_lines:
                suffix_parts.append("Anexos: " + ", ".join(attachment_lines))
            if embed_marker:
                suffix_parts.append(embed_marker)
            suffix = f" | {' | '.join(suffix_parts)}" if suffix_parts else ""
            lines.append(f"- [{created}] {author_name}: {content}{suffix}")
        return "\n".join(lines)

    async def list_open_tickets(self, guild: discord.Guild) -> list[dict[str, Any]]:
        tickets = await self.bot.db.list_open_tickets(guild.id)
        stale: list[dict[str, Any]] = []
        healthy: list[dict[str, Any]] = []
        for ticket in tickets:
            channel = guild.get_channel(int(ticket["channel_id"]))
            if channel is None:
                stale.append(ticket)
            else:
                healthy.append(ticket)
        for ticket in stale:
            await self.bot.db.mark_ticket_stale(
                int(ticket["channel_id"]),
                self.bot.user.id if self.bot.user else int(ticket["user_id"]),
                "Ticket encerrado durante auditoria porque o canal do atendimento não foi encontrado.",
            )
            await self._log(
                "Ticket Stale Detectado",
                "Um ticket aberto foi encerrado automaticamente por divergência entre banco e servidor.",
                fields=[("Canal ausente", f"indisponível", True), ("Ticket", f"``", True)],
                level="warn",
            )
        return healthy

    async def _send_close_dm(
        self,
        guild: discord.Guild,
        ticket: dict[str, Any],
        transcript_text: str,
        transcript_filename: str,
    ) -> str:
        member = guild.get_member(int(ticket["user_id"]))
        if member is None:
            return "falhou: usuário não encontrado"

        assigned_staff_id = ticket.get("assigned_staff_id") or ticket.get("claimed_by")
        opened_at = self._parse_timestamp(ticket.get("opened_at"))
        closed_at = self._parse_timestamp(ticket.get("closed_at"))
        duration_seconds = int((closed_at - opened_at).total_seconds()) if opened_at and closed_at else 0
        embed = self.bot.embeds.make(
            title=f"Ticket  Encerrado",
            description=(
                "Seu atendimento foi concluído.\n"
                "Segue abaixo o resumo administrativo do encerramento."
            ),
        )
        embed.add_field(name="Tipo", value=self.ticket_type(str(ticket["ticket_type"]))["label"], inline=True)
        embed.add_field(name="Status Final", value=self.status_label("closed"), inline=True)
        embed.add_field(name="Duração", value=self._format_duration(duration_seconds), inline=True)
        embed.add_field(name="Assumido por", value=f"<@{assigned_staff_id}>" if assigned_staff_id else "Não atribuído", inline=True)
        embed.add_field(name="Encerrado por", value=f"<@{ticket['closed_by']}>" if ticket.get("closed_by") else "Não registrado", inline=True)
        embed.add_field(name="Aberto em", value=self._format_timestamp(ticket.get("opened_at")), inline=False)
        embed.add_field(name="Encerrado em", value=self._format_timestamp(ticket.get("closed_at")), inline=False)
        if ticket.get("close_reason"):
            embed.add_field(name="Motivo Administrativo", value=str(ticket["close_reason"]), inline=False)

        transcript_bytes = transcript_text.encode("utf-8")
        try:
            if len(transcript_bytes) <= 7_500_000:
                await member.send(
                    embed=embed,
                    file=discord.File(BytesIO(transcript_bytes), filename=transcript_filename),
                )
            else:
                await member.send(
                    embed=self.bot.embeds.make(
                        title=f"Ticket  Encerrado",
                        description=(
                            f"{embed.description}\n"
                            "A transcrição completa foi arquivada internamente pela equipe, pois o arquivo excedeu o limite de envio direto."
                        ),
                        fields=[(field.name, field.value, field.inline) for field in embed.fields],
                    ),
                )
            return "enviada"
        except discord.HTTPException as exc:
            await self._log(
                "Falha ao Enviar DM do Ticket",
                "O ticket foi encerrado normalmente, mas o envio de mensagem privada ao autor falhou.",
                fields=[
                    ("Ticket", f"``", True),
                    ("Usuário", f"<@{ticket['user_id']}>", True),
                    ("Motivo", str(exc)[:200], False),
                ],
                level="warn",
            )
            return "falhou: dm bloqueada ou indisponível"

    async def _log(
        self,
        title: str,
        description: str,
        *,
        fields: list[tuple[str, str, bool]] | None = None,
        level: str = "info",
        extra_detail: str | None = None,
    ) -> None:
        color = {
            "info": self.bot.embeds.default_color,
            "warn": self.bot.embeds.warning_color,
            "error": self.bot.embeds.error_color,
        }.get(level, self.bot.embeds.default_color)
        dispatch_fields = list(fields or [])
        if extra_detail:
            dispatch_fields.append(("Detalhe", extra_detail[:1024], False))
        await self.bot.central_logger.dispatch(
            "tickets",
            title=title,
            description=description,
            color=color,
            fields=dispatch_fields,
        )




