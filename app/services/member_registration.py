from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

import discord


try:
    BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    BRASILIA_TZ = timezone(timedelta(hours=-3))
GAME_NICK_PATTERN = re.compile(r"^[A-Za-z0-9 _\-.]{3,32}$")


@dataclass(slots=True)
class SessionStartResult:
    status: str
    session_id: int | None
    detail: str


@dataclass(slots=True)
class FinalizeResult:
    status: str
    detail: str
    role_applied: bool
    nickname_status: str


class MemberRegistrationService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    def panel_enabled(self) -> bool:
        return self.bot.server_map.member_registration_enabled()

    def build_panel_embed(self, guild: discord.Guild | None) -> discord.Embed:
        description = (
            "Este é o Cadastro Oficial Drakoria para entrada de players no servidor. 🛡️\n"
            "O preenchimento completo é obrigatório para concluir teu acesso como membro. ✅"
        )
        embed = self.bot.embeds.make(
            title="📜 Cadastro Oficial Drakoria",
            description=description,
        )
        embed.add_field(
            name="Diretrizes do Cadastro",
            value=(
                "O processo é individual e pessoal.\n"
                "As respostas ficam registradas para auditoria administrativa.\n"
                "Idade mínima obrigatória: 16 anos."
            ),
            inline=False,
        )
        footer_icon = self.bot.embeds.footer_icon or self.bot.embeds.guild_icon_url
        if footer_icon:
            embed.set_footer(text="Drakoria | Cadastro Oficial", icon_url=footer_icon)
        else:
            embed.set_footer(text="Drakoria | Cadastro Oficial")
        return embed

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        if not self.panel_enabled():
            raise RuntimeError("O cadastro oficial está desabilitado em `member_registration.enabled`.")

        channel_id = self.bot.server_map.member_registration_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError(
                "Canal do cadastro oficial não encontrado. Revise `member_registration.panel_channel_id`."
            )

        me = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is None:
            raise RuntimeError("Não foi possível validar as permissões do bot nesta guild.")
        missing = [
            label
            for attr, label in (
                ("view_channel", "View Channel"),
                ("send_messages", "Send Messages"),
                ("embed_links", "Embed Links"),
            )
            if not getattr(channel.permissions_for(me), attr, False)
        ]
        if missing:
            raise RuntimeError(
                "Permissões insuficientes para publicar painel de cadastro.\n"
                f"Canal: {channel.mention}\nPermissões ausentes: {', '.join(missing)}"
            )

        state = await self.bot.db.get_member_registration_panel_message(guild.id)
        message: discord.Message | None = None
        embed = self.build_panel_embed(guild)
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=self.bot.view_factory.build_member_registration_panel_view())
                except discord.NotFound:
                    message = None
        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_member_registration_panel_view())
        await self.bot.db.save_member_registration_panel_message(guild.id, channel.id, message.id)

        if actor is not None:
            await self._dispatch_log(
                title="Painel de Cadastro Publicado",
                description=f"{actor.mention} publicou ou sincronizou o painel oficial de cadastro.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Canal", channel.mention, True),
                    ("Mensagem", f"indisponível", True),
                    ("Horário", self._now_human(), True),
                ],
            )
        return message

    async def start_session(self, interaction: discord.Interaction, member: discord.Member) -> SessionStartResult:
        if interaction.guild is None:
            raise RuntimeError("Cadastro disponivel apenas dentro do servidor oficial.")
        if interaction.guild.id != self.bot.server_map.guild_id():
            raise RuntimeError("Este painel não pertence ao servidor oficial configurado.")
        if member.bot:
            raise RuntimeError("Contas de bot não podem usar o cadastro oficial.")
        if not self.panel_enabled():
            raise RuntimeError("Cadastro oficial desabilitado no momento.")

        async with self._member_lock(member.id):
            latest = await self.bot.db.get_latest_member_registration_session(interaction.guild.id, member.id)
            member_role = interaction.guild.get_role(self.bot.server_map.member_registration_member_role_id() or 0)
            has_member_role = bool(member_role and member_role in member.roles)
            if latest and str(latest.get("status")) == "completed" and has_member_role:
                await self._dispatch_log(
                    title="Tentativa Duplicada de Cadastro",
                    description=f"{member.mention} tentou iniciar cadastro já concluído.",
                    color=self.bot.embeds.warning_color,
                    fields=[
                        ("Usuário", f"{member}", False),
                        ("Sessão", f"indisponível", True),
                        ("Horário", self._now_human(), True),
                    ],
                )
                return SessionStartResult(
                    status="already_completed",
                    session_id=int(latest["id"]),
                    detail="Teu cadastro oficial já consta como concluído. Não e necessário repetir.",
                )
            if latest and str(latest.get("status")) == "in_progress":
                await self._dispatch_log(
                    title="Cadastro Retomado",
                    description=f"{member.mention} retomou uma sessão de cadastro em andamento.",
                    color=self.bot.embeds.default_color,
                    fields=[
                        ("Usuário", f"{member}", False),
                        ("Sessão", f"indisponível", True),
                        ("Etapa", f"`{latest.get('last_step')}`", True),
                        ("Horário", self._now_human(), True),
                    ],
                )
                return SessionStartResult(
                    status="already_in_progress",
                    session_id=int(latest["id"]),
                    detail="Existe um cadastro em andamento. Vamos retomar da etapa atual.",
                )

            panel_message_id = interaction.message.id if interaction.message else None
            session_id = await self.bot.db.start_member_registration_session(
                interaction.guild.id,
                member.id,
                source_channel_id=interaction.channel_id,
                source_message_id=interaction.message.id if interaction.message else None,
                panel_message_id=panel_message_id,
            )
            await self._dispatch_log(
                title="Cadastro Iniciado",
                description=f"{member.mention} iniciou o cadastro oficial.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Sessão", f"indisponível", True),
                    ("Origem", self._origin_text(interaction.channel_id, panel_message_id), False),
                    ("Horário", self._now_human(), True),
                ],
            )
            return SessionStartResult(
                status="started",
                session_id=session_id,
                detail="Cadastro iniciado. Preencha as etapas para concluir tua entrada oficial.",
            )

    async def save_step_one(
        self,
        session_id: int,
        *,
        age: int,
        game_nick: str,
        how_found_drakoria: str,
        prior_rpg_experience: str,
    ) -> None:
        nick = game_nick.strip()
        if not GAME_NICK_PATTERN.match(nick):
            raise RuntimeError(
                "Nick inválido. Use entre 3 e 32 caracteres com letras, numeros, espaco, ponto, traco ou underscore."
            )
        if age <= 0 or age > 99:
            raise RuntimeError("Idade inválida. Informe um numero inteiro entre 1 e 99.")
        await self.bot.db.update_member_registration_session(
            session_id,
            {
                "age": int(age),
                "game_nick": nick,
                "how_found_drakoria": how_found_drakoria.strip()[:300],
                "prior_rp_experience": prior_rpg_experience.strip()[:300],
                "last_step": "step_1",
                "last_error": None,
            },
        )

    async def save_step_two(
        self,
        session_id: int,
        *,
        weekly_availability: str,
        interest_area: str,
        what_called_attention: str,
        rules_confirmation: str,
    ) -> None:
        await self.bot.db.update_member_registration_session(
            session_id,
            {
                "weekly_availability": weekly_availability.strip()[:300],
                "interest_area": interest_area.strip()[:300],
                "what_called_attention": what_called_attention.strip()[:500],
                "rules_confirmation": rules_confirmation.strip()[:120],
                "last_step": "step_2",
                "last_error": None,
            },
        )

    async def finalize(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        session_id: int,
        *,
        truth_confirmation: str,
        final_notes: str,
    ) -> FinalizeResult:
        session = await self.bot.db.get_member_registration_session(session_id)
        if not session:
            raise RuntimeError("Sessão de cadastro não encontrada. Inicie novamente pelo painel oficial.")
        if str(session.get("status")) != "in_progress":
            raise RuntimeError("Esta sessão já foi encerrada. Inicie novo fluxo apenas se autorizado.")
        if int(session.get("user_id", 0)) != member.id:
            raise RuntimeError("Sessão inválida para este usuário.")

        await self.bot.db.update_member_registration_session(
            session_id,
            {
                "truth_confirmation": truth_confirmation.strip()[:120],
                "final_notes": final_notes.strip()[:500] if final_notes.strip() else None,
                "last_step": "step_3",
                "last_error": None,
            },
        )

        age = int(session.get("age") or 0)
        minimum_age = self.bot.server_map.member_registration_minimum_age()
        if self.bot.server_map.member_registration_auto_reject_under_minimum_age() and age < minimum_age:
            await self.bot.db.update_member_registration_session(
                session_id,
                {
                    "status": "rejected_underage",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "rejection_reason": f"Idade informada ({age}) abaixo do mínimo ({minimum_age}).",
                    "last_step": "finished",
                },
            )
            await self._dispatch_log(
                title="Cadastro Reprovado Automaticamente",
                description=f"{member.mention} teve o cadastro encerrado por idade abaixo do mínimo.",
                color=self.bot.embeds.warning_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Sessão", f"indisponível", True),
                    ("Idade", f"`{age}`", True),
                    ("Regra", f"Mínimo de `{minimum_age}` anos", True),
                    ("Horário", self._now_human(), True),
                ],
            )
            return FinalizeResult(
                status="rejected_underage",
                detail=(
                    "Teu cadastro foi encerrado automaticamente, pois a idade informada não atende a idade mínima "
                    f"de {minimum_age} anos para ingresso no servidor."
                ),
                role_applied=False,
                nickname_status="not_applied_underage",
            )

        game_nick = str(session.get("game_nick") or "").strip()
        nickname_status = "disabled"
        nickname_applied = None
        if self.bot.server_map.member_registration_rename_member_on_success():
            try:
                if game_nick:
                    await member.edit(nick=game_nick, reason="Cadastro oficial de membro concluído")
                    nickname_status = "success"
                    nickname_applied = game_nick
                else:
                    nickname_status = "skipped_empty_nick"
            except discord.Forbidden:
                nickname_status = "failed_forbidden"
            except discord.HTTPException as exc:
                nickname_status = f"failed_http:{exc.status}"
        if nickname_status.startswith("failed"):
            await self._dispatch_log(
                title="Falha ao Alterar Nickname",
                description=f"{member.mention} concluiu cadastro, mas houve falha ao alterar nickname.",
                color=self.bot.embeds.warning_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Sessão", f"indisponível", True),
                    ("Nickname desejádo", f"`{game_nick or '-'}`", True),
                    ("Status", nickname_status, True),
                    ("Horário", self._now_human(), True),
                ],
            )

        role_id = self.bot.server_map.member_registration_member_role_id()
        role = interaction.guild.get_role(role_id or 0) if role_id else None
        if role is None:
            await self.bot.db.update_member_registration_session(
                session_id,
                {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "last_error": "Cargo de membro configurado não encontrado.",
                    "nickname_applied": nickname_applied,
                    "nickname_apply_status": nickname_status,
                    "last_step": "finished",
                },
            )
            await self._dispatch_log(
                title="Falha no Cadastro",
                description="Cadastro finalizado com erro por configuracao de cargo ausente.",
                color=self.bot.embeds.error_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Sessão", f"indisponível", True),
                    ("Erro", "Cargo de membro não encontrado.", False),
                    ("Horário", self._now_human(), True),
                ],
            )
            raise RuntimeError("Falha ao concluir cadastro: cargo de membro não encontrado na guild.")

        role_applied = role in member.roles
        if not role_applied:
            try:
                await member.add_roles(role, reason="Cadastro oficial de membro concluído")
                role_applied = True
            except discord.Forbidden:
                await self.bot.db.update_member_registration_session(
                    session_id,
                    {
                        "status": "failed",
                        "completed_at": datetime.now(UTC).isoformat(),
                        "last_error": "Sem permissão efetiva para aplicar cargo.",
                        "nickname_applied": nickname_applied,
                        "nickname_apply_status": nickname_status,
                        "last_step": "finished",
                    },
                )
                await self._dispatch_log(
                    title="Falha no Cadastro",
                    description=f"{member.mention} não recebeu cargo por falta de permissão/hierarquia.",
                    color=self.bot.embeds.error_color,
                    fields=[
                        ("Usuário", f"{member}", False),
                        ("Sessão", f"indisponível", True),
                        ("Cargo", f"{role.mention}", False),
                        ("Horário", self._now_human(), True),
                    ],
                )
                raise RuntimeError("Não foi possível aplicar o cargo de membro. Verifique permissões e hierarquia.")
            except discord.HTTPException as exc:
                await self.bot.db.update_member_registration_session(
                    session_id,
                    {
                        "status": "failed",
                        "completed_at": datetime.now(UTC).isoformat(),
                        "last_error": f"Erro HTTP ao aplicar cargo: {exc}",
                        "nickname_applied": nickname_applied,
                        "nickname_apply_status": nickname_status,
                        "last_step": "finished",
                    },
                )
                raise RuntimeError("Discord retornou erro técnico ao aplicar cargo. Tente novamente.") from exc

        await self.bot.db.update_member_registration_session(
            session_id,
            {
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
                "applied_role_id": role.id,
                "nickname_applied": nickname_applied,
                "nickname_apply_status": nickname_status,
                "last_step": "finished",
                "last_error": None,
            },
        )

        await self._dispatch_log(
            title="Cadastro Concluído",
            description=f"{member.mention} concluiu o cadastro oficial com sucesso.",
            color=self.bot.embeds.success_color,
            fields=[
                ("Usuário", f"{member}", False),
                ("Sessão", f"indisponível", True),
                ("Cargo aplicado", f"{role.mention}", False),
                ("Nickname", nickname_status, True),
                ("Horário", self._now_human(), True),
            ],
        )
        await self._dispatch_completed_notice(
            member=member,
            session_id=session_id,
            role=role,
            nickname_status=nickname_status,
            game_nick=game_nick,
            session_data=await self.bot.db.get_member_registration_session(session_id),
        )
        detail = "Cadastro concluído com sucesso. Bem-vindo oficialmente ao reino de Drakoria."
        if nickname_status.startswith("failed"):
            detail += "\nObservacao: não consegui alterar teu nickname automaticamente; a administração foi notificada."
        return FinalizeResult(
            status="completed",
            detail=detail,
            role_applied=True,
            nickname_status=nickname_status,
        )

    async def describe_status(self, guild_id: int, user_id: int) -> tuple[str, dict[str, Any] | None]:
        latest = await self.bot.db.get_latest_member_registration_session(guild_id, user_id)
        if latest is None:
            return "no_session", None
        return str(latest.get("status", "unknown")), latest

    def format_session_for_embed(self, session: dict[str, Any]) -> str:
        started_at = str(session.get("started_at") or "-")
        completed_at = str(session.get("completed_at") or "-")
        return (
            f"Sessão: indisponível\n"
            f"Status: **{session.get('status')}**\n"
            f"Idade: `{session.get('age')}`\n"
            f"Nick de jogo: `{session.get('game_nick') or '-'}`\n"
            f"Etapa atual: `{session.get('last_step')}`\n"
            f"Iniciado em: `{started_at}`\n"
            f"Concluído em: `{completed_at}`\n"
            f"Motivo de rejeição: `{session.get('rejection_reason') or '-'}`\n"
            f"Nickname status: `{session.get('nickname_apply_status') or '-'}`"
        )

    async def _dispatch_log(
        self,
        *,
        title: str,
        description: str,
        color: int,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        channel_id = self.bot.server_map.member_registration_log_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            self.bot.log.warning("Canal de log do cadastro não encontrado: %s", channel_id)
            return
        embed = self.bot.embeds.make(title=title, description=description, color=color, fields=fields or [])
        embed.timestamp = datetime.now(UTC)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            self.bot.log.warning("Sem permissão para enviar log de cadastro no canal %s", channel_id)
        except discord.HTTPException as exc:
            self.bot.log.warning("Falha HTTP ao enviar log de cadastro: %s", exc)

    async def _dispatch_completed_notice(
        self,
        *,
        member: discord.Member,
        session_id: int,
        role: discord.Role,
        nickname_status: str,
        game_nick: str,
        session_data: dict[str, Any] | None,
    ) -> None:
        channel_id = self.bot.server_map.member_registration_completed_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            self.bot.log.warning("Canal de cadastro concluídos não encontrado: %s", channel_id)
            return
        session_data = session_data or {}
        notes = str(session_data.get("final_notes") or "-").strip()
        notes = notes[:600] if notes and notes != "-" else "-"
        overview = (
            f"Idade: `{session_data.get('age') or '-'}`\n"
            f"Conheceu o Drakoria por: {self._fit(session_data.get('how_found_drakoria'), 200)}\n"
            f"Experiencia em RPG: {self._fit(session_data.get('prior_rp_experience'), 200)}\n"
            f"Disponibilidade semanal: {self._fit(session_data.get('weekly_availability'), 200)}\n"
            f"Area de interesse: {self._fit(session_data.get('interest_area'), 200)}"
        )
        confirmations = (
            f"Leitura das regras: `{self._fit(session_data.get('rules_confirmation'), 60)}`\n"
            f"Veracidade dos dados: `{self._fit(session_data.get('truth_confirmation'), 60)}`"
        )
        metadata = (
            f"Iniciado em: `{session_data.get('started_at') or '-'}`\n"
            f"Concluído em: `{session_data.get('completed_at') or '-'}`\n"
            f"Sessão: indisponível\n"
            f"Status final: `{session_data.get('status') or 'completed'}`"
        )
        embed = self.bot.embeds.make(
            title="Cadastro Concluído",
            description=f"{member.mention} concluiu o cadastro oficial de entrada no servidor.",
            color=self.bot.embeds.success_color,
            fields=[
                ("Usuário", f"{member}", False),
                ("Cargo aplicado", f"{role.mention}", False),
                ("Nick informado", f"`{game_nick or '-'}`", True),
                ("Nickname status", nickname_status, True),
                ("Resumo do Cadastro", overview, False),
                ("O que chamou atencao", self._fit(session_data.get("what_called_attention"), 800), False),
                ("Confirmacoes", confirmations, False),
                ("Observacao Final", notes, False),
                ("Metadados da Sessão", metadata, False),
                ("Registro", self._now_human(), False),
            ],
        )
        embed.timestamp = datetime.now(UTC)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            self.bot.log.warning("Sem permissão para enviar em cadastro-concluídos: %s", channel_id)
        except discord.HTTPException as exc:
            self.bot.log.warning("Falha HTTP ao enviar aviso de cadastro concluído: %s", exc)

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
        now_local = datetime.now(BRASILIA_TZ)
        now_utc = datetime.now(UTC)
        return f"{now_local.strftime('%d/%m/%Y %H:%M:%S')} (Brasilia) | `{now_utc.isoformat()}`"

    @staticmethod
    def _fit(value: Any, max_len: int) -> str:
        text = str(value or "-").strip()
        if not text:
            return "-"
        return text[:max_len]





