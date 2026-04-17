from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import discord


@dataclass(slots=True)
class RegistrationResult:
    status: str
    registered_role: discord.Role | None
    removed_role: discord.Role | None
    detail: str


class RegistrationService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    def panel_enabled(self) -> bool:
        return self.bot.server_map.registration_panel_enabled()

    def build_panel_embed(self, guild: discord.Guild | None) -> discord.Embed:
        rules = self._rules_line()
        description = (
            "Este é o registro inicial oficial de Drakoria.\n"
            "Ao confirmar, você declara que leu, compreendeu e aceita integralmente as regras do servidor."
        )
        embed = self.bot.embeds.make(title="✅ Registrar-se", description=description)
        embed.add_field(name="Regras Oficiais", value=rules, inline=False)
        return embed

    def build_confirmation_embed(self) -> discord.Embed:
        rules = self._rules_line()
        return self.bot.embeds.make(
            title="Confirmação de Registro",
            description=(
                "Antes de concluir, confirme que leu e concorda com as regras do servidor.\n"
                "Ao prosseguir, o bot registrará teu consentimento e aplicará o cargo oficial da comunidade."
            ),
            fields=[
                ("Declaração Obrigatória", "Eu li, compreendi e concordo com as regras do servidor.", False),
                ("Canais de Regras", rules, False),
            ],
        )

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        if not self.panel_enabled():
            raise RuntimeError("O painel de registro está desabilitado em `registration_panel.enabled`.")

        channel_id = self.bot.server_map.registration_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError(
                "O canal do painel de registro não foi localizado. Revise `registration_panel.panel_channel_id`."
            )

        me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is None:
            raise RuntimeError("Não foi possível localizar o bot na guild para validar permissões.")
        missing_permissions = [
            label
            for attr, label in (
                ("view_channel", "View Channel"),
                ("send_messages", "Send Messages"),
                ("embed_links", "Embed Links"),
            )
            if not getattr(channel.permissions_for(me), attr, False)
        ]
        if missing_permissions:
            raise RuntimeError(
                "O bot não possui permissões suficientes para publicar o painel no canal configurado.\n"
                f"Canal: {channel.mention}\nPermissões ausentes: {', '.join(missing_permissions)}"
            )

        state = await self.bot.db.get_registration_panel_message(guild.id)
        message: discord.Message | None = None
        embed = self.build_panel_embed(guild)
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=self.bot.view_factory.build_registration_panel_view())
                except discord.NotFound:
                    message = None

        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_registration_panel_view())
        await self.bot.db.save_registration_panel_message(guild.id, channel.id, message.id)

        if actor is not None:
            await self._dispatch_log(
                title="Painel Registrar-se Publicado",
                description=f"{actor.mention} publicou ou sincronizou o painel de registro inicial.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Canal", channel.mention, True),
                    ("Mensagem", f"indisponível", True),
                    ("Registrado em", self._now_human(), True),
                ],
            )
        return message

    async def register_member(self, interaction: discord.Interaction, member: discord.Member) -> RegistrationResult:
        guild = interaction.guild
        if guild is None:
            raise RuntimeError("Este fluxo só pode ser executado dentro do servidor oficial.")
        if guild.id != self.bot.server_map.guild_id():
            raise RuntimeError("Este painel pertence a outra guild. Use o painel oficial de Drakoria.")
        if member.guild.id != guild.id:
            raise RuntimeError("Membro inválido para este contexto de registro.")
        if member.bot:
            raise RuntimeError("Contas de bot não podem concluir o registro inicial.")
        if not self.panel_enabled():
            raise RuntimeError("O painel de registro está desabilitado no momento.")

        source_channel_id = interaction.channel.id if interaction.channel else None
        source_message_id = interaction.message.id if interaction.message else None
        source_interaction_id = interaction.id

        async with self._member_lock(member.id):
            registered_role = guild.get_role(self.bot.server_map.registration_registered_role_id() or 0)
            if registered_role is None:
                await self._persist_failure(
                    guild.id,
                    member.id,
                    source_channel_id,
                    source_message_id,
                    source_interaction_id,
                    "Cargo de registro configurado não encontrado.",
                )
                raise RuntimeError(
                    "O cargo configurado para registro não foi encontrado no servidor. "
                    "Revise `registration_panel.registered_role_id`."
                )

            visitor_role = guild.get_role(self.bot.server_map.registration_visitor_role_id() or 0)
            if visitor_role is None:
                await self._persist_failure(
                    guild.id,
                    member.id,
                    source_channel_id,
                    source_message_id,
                    source_interaction_id,
                    "Cargo visitante configurado não encontrado.",
                )
                raise RuntimeError(
                    "O cargo de visitante configurado não foi encontrado no servidor. "
                    "Revise `registration_panel.visitor_role_id`."
                )

            already_has_role = registered_role in member.roles
            if already_has_role:
                await self.bot.db.upsert_registration_record(
                    guild.id,
                    member.id,
                    status="already_registered",
                    registered_role_id=registered_role.id,
                    removed_role_id=visitor_role.id if visitor_role not in member.roles else None,
                    source_channel_id=source_channel_id,
                    source_message_id=source_message_id,
                    source_interaction_id=source_interaction_id,
                    notes="Tentativa ignorada: membro já registrado.",
                    mark_registered=True,
                )
                return RegistrationResult(
                    status="already_registered",
                    registered_role=registered_role,
                    removed_role=None,
                    detail="Teu registro inicial já consta como concluído. Nenhuma alteração adicional foi necessária.",
                )

            self._validate_bot_role_capability(guild, registered_role, visitor_role)

            removed_role: discord.Role | None = None
            try:
                if registered_role not in member.roles:
                    await member.add_roles(registered_role, reason="Registro inicial confirmado no painel Registrar-se")
                if self.bot.server_map.registration_remove_visitor_role() and visitor_role in member.roles:
                    await member.remove_roles(visitor_role, reason="Registro inicial concluído no painel Registrar-se")
                    removed_role = visitor_role
            except discord.Forbidden as exc:
                await self._persist_failure(
                    guild.id,
                    member.id,
                    source_channel_id,
                    source_message_id,
                    source_interaction_id,
                    "Discord recusou a alteração de cargos por permissão.",
                )
                raise RuntimeError(
                    "Não foi possível concluir o registro porque o bot não tem permissão efetiva para gerenciar cargos."
                ) from exc
            except discord.HTTPException as exc:
                await self._persist_failure(
                    guild.id,
                    member.id,
                    source_channel_id,
                    source_message_id,
                    source_interaction_id,
                    f"Erro HTTP ao aplicar cargos: {exc}",
                )
                raise RuntimeError(
                    "O Discord retornou erro técnico ao aplicar os cargos. Tente novamente em instantes."
                ) from exc

            await self.bot.db.upsert_registration_record(
                guild.id,
                member.id,
                status="success",
                registered_role_id=registered_role.id,
                removed_role_id=removed_role.id if removed_role else None,
                source_channel_id=source_channel_id,
                source_message_id=source_message_id,
                source_interaction_id=source_interaction_id,
                notes="Registro concluído com sucesso.",
                mark_registered=True,
            )
            await self._dispatch_log(
                title="Registro Inicial Concluído",
                description=f"{member.mention} concluiu o registro inicial no painel Registrar-se.",
                color=self.bot.embeds.success_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Cargo aplicado", f"{registered_role.mention}", False),
                    (
                        "Cargo removido",
                        f"{removed_role.mention}" if removed_role else "Não removido",
                        False,
                    ),
                    ("Origem", self._origin_text(source_channel_id, source_message_id), False),
                    ("Resultado", "success", True),
                    ("Horário", self._now_human(), True),
                ],
            )
            return RegistrationResult(
                status="success",
                registered_role=registered_role,
                removed_role=removed_role,
                detail="Registro confirmado e cargos atualizados com sucesso.",
            )

    def _validate_bot_role_capability(
        self,
        guild: discord.Guild,
        registered_role: discord.Role,
        visitor_role: discord.Role,
    ) -> None:
        me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is None:
            raise RuntimeError("Não foi possível localizar o bot na guild para validar hierarquia de cargos.")
        if not me.guild_permissions.manage_roles:
            raise RuntimeError("O bot precisa da permissão `Manage Roles` para concluir o registro inicial.")
        if me.top_role <= registered_role:
            raise RuntimeError(
                "O cargo de registro está acima (ou no mesmo nível) do bot na hierarquia. "
                "Ajuste a posição do cargo do bot para permitir a concessão."
            )
        if self.bot.server_map.registration_remove_visitor_role() and me.top_role <= visitor_role:
            raise RuntimeError(
                "O cargo de visitante está acima (ou no mesmo nível) do bot na hierarquia. "
                "Ajuste a hierarquia para permitir a remoção automática."
            )

    async def _persist_failure(
        self,
        guild_id: int,
        user_id: int,
        source_channel_id: int | None,
        source_message_id: int | None,
        source_interaction_id: int,
        notes: str,
    ) -> None:
        await self.bot.db.upsert_registration_record(
            guild_id,
            user_id,
            status="failed",
            registered_role_id=self.bot.server_map.registration_registered_role_id(),
            removed_role_id=None,
            source_channel_id=source_channel_id,
            source_message_id=source_message_id,
            source_interaction_id=source_interaction_id,
            notes=notes[:500],
            mark_registered=False,
        )
        await self._dispatch_log(
            title="Falha no Registro Inicial",
            description="Uma tentativa de registro inicial falhou e foi registrada para auditoria.",
            color=self.bot.embeds.error_color,
            fields=[
                ("Guild", f"indisponível", True),
                ("Usuário", f"<@{user_id}>", False),
                ("Origem", self._origin_text(source_channel_id, source_message_id), False),
                ("Resultado", "failed", True),
                ("Motivo", notes[:1024], False),
                ("Horário", self._now_human(), True),
            ],
        )

    async def _dispatch_log(
        self,
        *,
        title: str,
        description: str,
        color: int,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        channel_id = self.bot.server_map.registration_log_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            self.bot.log.warning("Canal de log do registro não encontrado: %s", channel_id)
            return
        embed = self.bot.embeds.make(title=title, description=description, color=color, fields=fields or [])
        embed.timestamp = datetime.now(UTC)
        await channel.send(embed=embed)

    def _rules_line(self) -> str:
        channel_ids = self.bot.server_map.registration_rules_channel_ids()
        if not channel_ids:
            return "Nenhum canal de regras configurado."
        return " | ".join(f"📜<#{channel_id}>" for channel_id in channel_ids)

    def _member_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    @staticmethod
    def _origin_text(source_channel_id: int | None, source_message_id: int | None) -> str:
        channel_text = f"<#{source_channel_id}>" if source_channel_id else "`desconhecido`"
        message_text = f"indisponível" if source_message_id else "`desconhecida`"
        return f"{channel_text} | msg {message_text}"

    @staticmethod
    def _now_human() -> str:
        now = datetime.now(UTC)
        return f"{discord.utils.format_dt(now, style='F')} | `{now.isoformat()}`"




