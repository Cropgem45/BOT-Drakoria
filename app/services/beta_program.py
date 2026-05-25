from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass(slots=True)
class BetaStartResult:
    status: str
    application_id: int | None
    detail: str


@dataclass(slots=True)
class TesterCardData:
    holder_name: str
    discord_user: str
    discord_id: int
    protocol: str
    issued_label: str
    joined_label: str
    auth_code: str
    status: str = "APROVADO COMO BETA TESTER"


class BetaProgramService:
    INFLUENCER_INVITE_LIMIT = 5
    QUOTA_CHANNEL_ID = 1508552344923799803

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._application_locks: dict[int, asyncio.Lock] = {}
        self._influencer_code_locks: dict[tuple[int, str], asyncio.Lock] = {}
        self._brand_logo_cache: dict[str, Image.Image] = {}

    def panel_enabled(self) -> bool:
        return self.bot.server_map.beta_program_enabled()

    def build_panel_embed(self, guild: discord.Guild | None) -> discord.Embed:
        description = (
            "🧪 O Programa Oficial de Beta Testers do Drakoria está em fase fechada por convite.\n\n"
            "🎟️ Nesta etapa, novas candidaturas só são abertas para pessoas que chegaram por uma campanha "
            "de influencer parceiro e possuem um código válido de ingresso.\n\n"
            "📌 Cada influencer possui **5 convites individuais**. Cada código libera **1 vaga** "
            "e só pode ser usado **uma única vez**.\n\n"
            "✅ Se você recebeu um código, use o botão abaixo para vinculá-lo à sua candidatura."
        )
        embed = self.bot.embeds.make(
            title="🧪 Programa Beta Tester | Acesso por Convite",
            description=description,
            fields=[
                ("🎟️ Ingresso", "Somente com código individual de influencer ativo.", False),
                ("📊 Vagas", "Cada código vale **1 vaga**. O influencer pode gerar até **5 convites**.", False),
                ("📝 Como funciona", "Informe o código, preencha a candidatura e aguarde avaliação da equipe.", False),
                ("🎁 Recompensas", "Cargo especial, carteirinha digital e benefícios exclusivos do programa.", False),
                ("📨 Candidaturas", f"<#{self.bot.server_map.beta_program_application_channel_id()}>", True),
                ("🪪 Carteirinhas", f"<#{self.bot.server_map.beta_program_card_channel_id()}>", True),
                ("🏷️ Cargo", f"<@&{self.bot.server_map.beta_program_role_id()}>", True),
            ],
        )
        footer_icon = self.bot.embeds.footer_icon or self.bot.embeds.guild_icon_url
        if footer_icon:
            embed.set_footer(text="Drakoria | Beta fechado por convite 🎟️", icon_url=footer_icon)
        else:
            embed.set_footer(text="Drakoria | Beta fechado por convite 🎟️")
        return embed

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        if not self.panel_enabled():
            raise RuntimeError("O módulo beta_program está desabilitado na configuração.")
        channel_id = self.bot.server_map.beta_program_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do painel beta não encontrado. Revise beta_program.panel_channel_id.")

        state = await self.bot.db.get_beta_program_panel_message(guild.id)
        message: discord.Message | None = None
        embed = self.build_panel_embed(guild)
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=self.bot.view_factory.build_beta_program_panel_view())
                except discord.NotFound:
                    message = None

        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_beta_program_panel_view())
        await self.bot.db.save_beta_program_panel_message(guild.id, channel.id, message.id)

        if actor is not None:
            await self._dispatch_log(
                title="Painel Beta Publicado",
                description=f"{actor.mention} publicou/sincronizou o painel do Programa Beta.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Canal", channel.mention, True),
                    ("Mensagem", f"indisponível", True),
                    ("Horário", self._now_human(), True),
                ],
            )
        return message

    async def refresh_quota_panel_for_guild_id(self, guild_id: int) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        await self.publish_quota_panel(guild)

    async def publish_quota_panel(self, guild: discord.Guild) -> discord.Message | None:
        channel = guild.get_channel(self.QUOTA_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            self.bot.log.warning("Canal vagas-beta nao encontrado: %s", self.QUOTA_CHANNEL_ID)
            return None

        embed = await self.build_quota_panel_embed(guild)
        state = await self.bot.db.get_beta_quota_panel_message(guild.id)
        message: discord.Message | None = None
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=self.bot.view_factory.build_beta_quota_panel_view())
                except discord.NotFound:
                    message = None

        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_beta_quota_panel_view())
        await self.bot.db.save_beta_quota_panel_message(guild.id, channel.id, message.id)
        return message

    async def build_quota_panel_embed(self, guild: discord.Guild) -> discord.Embed:
        rows = await self.bot.db.list_beta_influencer_owner_quotas(guild.id)
        if not rows:
            description = "Nenhum convite beta de influencer foi gerado ainda."
        else:
            lines: list[str] = []
            for row in rows[:25]:
                owner_id = row.get("owner_user_id")
                name = str(row.get("influencer_name") or "Influencer")
                used = int(row.get("used_codes") or 0)
                pending = int(row.get("pending_codes") or 0)
                remaining = max(self.INFLUENCER_INVITE_LIMIT - used - pending, 0)
                owner_label = f"<@{owner_id}>" if owner_id else name
                status = "esgotado" if used >= self.INFLUENCER_INVITE_LIMIT else "ativo"
                lines.append(
                    f"**{owner_label}** | {status}\n"
                    f"Usadas: **{used}/{self.INFLUENCER_INVITE_LIMIT}** | "
                    f"Pendentes: **{pending}** | Restantes para gerar: **{remaining}**"
                )
            description = "\n\n".join(lines)
            if len(rows) > 25:
                description += f"\n\n... e mais {len(rows) - 25} influencer(s)."

        embed = discord.Embed(
            title="📊 Vagas Beta por Influencer",
            description=description,
            color=self.bot.embeds.default_color,
        )
        embed.set_footer(text="Drakoria | Atualiza automaticamente ao gerar ou usar códigos")
        embed.timestamp = datetime.now(UTC)
        return embed

    async def start_or_resume_application(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        influencer_code: str | None = None,
    ) -> BetaStartResult:
        if interaction.guild is None or interaction.guild.id != self.bot.server_map.guild_id():
            raise RuntimeError("Este fluxo só pode ser usado no servidor oficial.")
        if member.bot:
            raise RuntimeError("Bots não podem enviar candidatura para o Programa Beta.")
        if not self.panel_enabled():
            raise RuntimeError("Programa Beta desabilitado no momento.")

        async with self._member_lock(member.id):
            influencer = None
            normalized_code = self.normalize_influencer_code(influencer_code)
            if normalized_code:
                influencer = await self.bot.db.get_beta_influencer_code(interaction.guild.id, normalized_code)
                if not influencer:
                    raise RuntimeError("❌ Código de influencer não encontrado. Confira o código e tente novamente.")
                if not int(influencer.get("active", 0)):
                    raise RuntimeError("🚫 Este código de influencer está desativado no momento.")

            latest = await self.bot.db.get_latest_beta_tester_application(interaction.guild.id, member.id)
            if latest:
                status = str(latest.get("status", ""))
                if status == "approved":
                    return BetaStartResult(
                        status="already_approved",
                        application_id=int(latest["id"]),
                        detail="Você já foi aprovado no Programa de Beta Testers.",
                    )
                if status in {"in_progress", "pending"}:
                    if status == "pending":
                        return BetaStartResult(
                            status="already_pending",
                            application_id=int(latest["id"]),
                            detail="Sua candidatura já foi enviada e aguarda avaliação da equipe.",
                        )
                    if influencer and str(latest.get("referral_type") or "direct") != "influencer":
                        async with self._influencer_code_lock(interaction.guild.id, normalized_code):
                            await self._consume_influencer_slot(interaction.guild.id, normalized_code, influencer)
                            await self.bot.db.update_beta_tester_application(
                                int(latest["id"]),
                                {
                                    "referral_type": "influencer",
                                    "influencer_code": normalized_code,
                                    "influencer_name": str(influencer["influencer_name"]),
                                    "influencer_owner_id": int(influencer["owner_user_id"])
                                    if influencer.get("owner_user_id")
                                    else None,
                                },
                            )
                            await self.publish_quota_panel(interaction.guild)
                    return BetaStartResult(
                        status="resume",
                        application_id=int(latest["id"]),
                        detail="Há uma candidatura em andamento para continuar.",
                    )
                if status == "rejected" and not self.bot.server_map.beta_program_allow_reapply_after_rejection():
                    return BetaStartResult(
                        status="blocked_reapply",
                        application_id=int(latest["id"]),
                        detail="No momento, não está habilitado novo envio após reprovação.",
                    )

            if normalized_code and await self.bot.db.has_user_used_beta_influencer_code(
                interaction.guild.id,
                member.id,
                normalized_code,
                ignored_statuses=("in_progress", "pending"),
            ):
                raise RuntimeError(
                    "🚫 Você já usou este código de influencer. Cada código só pode ser usado 1 vez por pessoa."
                )

            if not influencer:
                raise RuntimeError(
                    "🎟️ O Programa Beta está fechado para entrada direta. Use um código válido de influencer para iniciar."
                )

            async with self._influencer_code_lock(interaction.guild.id, normalized_code):
                await self._consume_influencer_slot(interaction.guild.id, normalized_code, influencer)
                application_id = await self.bot.db.create_beta_tester_application(
                    interaction.guild.id,
                    member.id,
                    panel_channel_id=interaction.channel_id,
                    panel_message_id=interaction.message.id if interaction.message else None,
                    referral_type="influencer" if influencer else "direct",
                    influencer_code=normalized_code if influencer else None,
                    influencer_name=str(influencer["influencer_name"]) if influencer else None,
                    influencer_owner_id=int(influencer["owner_user_id"]) if influencer and influencer.get("owner_user_id") else None,
                    status="in_progress",
                )
            await self.publish_quota_panel(interaction.guild)
            await self._dispatch_log(
                title="🧪 Candidatura Beta Iniciada",
                description=f"{member.mention} iniciou candidatura do Programa Beta.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Origem", self._referral_label_from_parts(influencer), False),
                    ("Candidatura", f"indisponível", True),
                    ("Horário", self._now_human(), True),
                ],
            )
            return BetaStartResult(
                status="started",
                application_id=application_id,
                detail="✅ Candidatura iniciada com sucesso.",
            )

    async def register_influencer_code(
        self,
        guild_id: int,
        *,
        code: str | None = None,
        influencer_name: str,
        owner_user_id: int | None,
        created_by_id: int | None,
        slot_limit: int | None = None,
    ) -> str:
        normalized = self.normalize_influencer_code(code) or await self.generate_unique_influencer_code(guild_id)
        if not normalized:
            raise RuntimeError("❌ Informe um código de influencer válido.")
        if len(normalized) < 3:
            raise RuntimeError("❌ O código precisa ter pelo menos 3 caracteres.")
        clean_name = influencer_name.strip()[:80]
        if not clean_name:
            raise RuntimeError("❌ Informe o nome do influencer.")
        resolved_slot_limit = slot_limit if slot_limit is not None else 5
        if resolved_slot_limit < 1 or resolved_slot_limit > 100:
            raise RuntimeError("📊 A quantidade de vagas precisa ficar entre 1 e 100.")
        await self.bot.db.upsert_beta_influencer_code(
            guild_id,
            normalized,
            clean_name,
            owner_user_id=owner_user_id,
            created_by_id=created_by_id,
            slot_limit=resolved_slot_limit,
            active=True,
        )
        return normalized

    async def generate_single_use_influencer_code(
        self,
        guild_id: int,
        *,
        influencer_name: str,
        owner_user_id: int | None,
        created_by_id: int | None,
    ) -> dict[str, Any]:
        clean_name = influencer_name.strip()[:80]
        if not clean_name:
            raise RuntimeError("❌ Informe o nome do influencer.")
        quota = await self.bot.db.get_beta_influencer_owner_quota(
            guild_id,
            owner_user_id=owner_user_id,
            influencer_name=clean_name,
        )
        reserved = int(quota["used_codes"]) + int(quota["pending_codes"])
        if reserved >= self.INFLUENCER_INVITE_LIMIT:
            raise RuntimeError(
                "🚫 Este influencer já possui 5 convites beta gerados/ocupados. "
                "Use ou desative um código pendente antes de gerar outro."
            )
        code = await self.register_influencer_code(
            guild_id,
            code=None,
            influencer_name=clean_name,
            owner_user_id=owner_user_id,
            created_by_id=created_by_id,
            slot_limit=1,
        )
        remaining = max(self.INFLUENCER_INVITE_LIMIT - reserved - 1, 0)
        return {
            "code": code,
            "slot_limit": 1,
            "remaining": remaining,
            "used_codes": int(quota["used_codes"]),
            "pending_codes": int(quota["pending_codes"]) + 1,
            "limit": self.INFLUENCER_INVITE_LIMIT,
        }

    async def generate_unique_influencer_code(self, guild_id: int) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for _ in range(20):
            left = "".join(secrets.choice(alphabet) for _ in range(4))
            right = "".join(secrets.choice(alphabet) for _ in range(4))
            candidate = f"DRK-{left}-{right}"
            if not await self.bot.db.get_beta_influencer_code(guild_id, candidate):
                return candidate
        raise RuntimeError("❌ Não foi possível gerar um código único agora. Tente novamente.")

    async def set_influencer_code_active(self, guild_id: int, code: str, active: bool) -> str:
        normalized = self.normalize_influencer_code(code)
        if not normalized:
            raise RuntimeError("❌ Informe um código de influencer válido.")
        changed = await self.bot.db.set_beta_influencer_code_active(guild_id, normalized, active)
        if not changed:
            raise RuntimeError("❌ Código de influencer não encontrado.")
        return normalized

    async def list_influencer_codes(self, guild_id: int, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await self.bot.db.list_beta_influencer_codes(guild_id, include_inactive=include_inactive)

    async def influencer_code_stats(self, guild_id: int, code: str) -> tuple[dict[str, Any], dict[str, int]]:
        normalized = self.normalize_influencer_code(code)
        if not normalized:
            raise RuntimeError("❌ Informe um código de influencer válido.")
        influencer = await self.bot.db.get_beta_influencer_code(guild_id, normalized)
        if not influencer:
            raise RuntimeError("❌ Código de influencer não encontrado.")
        stats = await self.bot.db.get_beta_influencer_code_stats(guild_id, normalized)
        return influencer, stats

    async def reset_influencer_slots(self, guild_id: int, code: str | None = None) -> tuple[str | None, int]:
        normalized = self.normalize_influencer_code(code)
        if code and not normalized:
            raise RuntimeError("❌ Informe um código de influencer válido.")
        changed = await self.bot.db.reset_beta_influencer_slots(guild_id, normalized or None)
        if code and changed == 0:
            raise RuntimeError("❌ Código de influencer não encontrado.")
        return normalized or None, changed

    async def _consume_influencer_slot(
        self,
        guild_id: int,
        normalized_code: str,
        influencer: dict[str, Any],
    ) -> None:
        consumed = await self.bot.db.try_consume_beta_influencer_slot(
            guild_id,
            normalized_code,
            owner_limit=self.INFLUENCER_INVITE_LIMIT,
        )
        if consumed:
            return
        refreshed = await self.bot.db.get_beta_influencer_code(guild_id, normalized_code) or influencer
        used_slots = int(refreshed.get("slot_used") or 0)
        if not int(refreshed.get("active", 0)):
            raise RuntimeError("🚫 Este código de influencer está desativado no momento.")
        name = str(refreshed.get("influencer_name") or "este influencer")
        quota = await self.bot.db.get_beta_influencer_owner_quota(
            guild_id,
            owner_user_id=int(refreshed["owner_user_id"]) if refreshed.get("owner_user_id") else None,
            influencer_name=name,
        )
        if int(quota.get("used_codes") or 0) >= self.INFLUENCER_INVITE_LIMIT:
            raise RuntimeError(
                f"🚫 As 5 vagas de **{name}** já foram consumidas. "
                "Nenhum código deste influencer pode liberar novas entradas."
            )
        if used_slots > 0:
            raise RuntimeError(
                f"🚫 O código `{normalized_code}` de **{name}** já foi usado. "
                "Peça ao influencer um novo código individual para participar do beta."
            )
        raise RuntimeError(
            f"🚫 O código `{normalized_code}` de **{name}** não possui vaga disponível. "
            "Peça outro código ativo para participar do beta."
        )

    async def save_step_answers(self, application_id: int, step: str, answers: dict[str, str]) -> None:
        application = await self.bot.db.get_beta_tester_application(application_id)
        if not application:
            raise RuntimeError("Candidatura não encontrada.")
        if str(application.get("status")) != "in_progress":
            raise RuntimeError("A candidatura não está mais em edição.")
        current_answers = json.loads(application.get("answers_json") or "{}")
        current_answers.update({key: value.strip()[:1500] for key, value in answers.items()})
        await self.bot.db.set_beta_tester_application_answers(application_id, answers=current_answers, last_step=step)

    async def submit_application(self, guild: discord.Guild, member: discord.Member, application_id: int) -> None:
        application = await self.bot.db.get_beta_tester_application(application_id)
        if not application:
            raise RuntimeError("Candidatura não localizada para envio.")
        if str(application.get("status")) != "in_progress":
            raise RuntimeError("Esta candidatura não está disponível para envio.")
        answers = json.loads(application.get("answers_json") or "{}")
        missing = [key for key in self.question_keys() if not str(answers.get(key, "")).strip()]
        if missing:
            raise RuntimeError("Ainda existem respostas obrigatórias não preenchidas.")

        channel_id = self.bot.server_map.beta_program_application_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal de candidaturas beta não encontrado.")

        await self.bot.db.update_beta_tester_application(
            application_id,
            {
                "status": "pending",
                "submitted_at": datetime.now(UTC).isoformat(),
                "application_channel_id": channel.id,
                "last_step": "submitted",
                "last_error": None,
            },
        )
        refreshed = await self.bot.db.get_beta_tester_application(application_id)
        embed = self.build_application_embed(member, refreshed, answers)
        message = await channel.send(embed=embed, view=self.bot.view_factory.build_beta_application_review_view(application_id))
        await self.bot.db.update_beta_tester_application(application_id, {"application_message_id": message.id})

        await self._dispatch_log(
            title="📨 Candidatura Beta Enviada",
            description=f"{member.mention} enviou candidatura para avaliação da equipe.",
            color=self.bot.embeds.default_color,
            fields=[
                ("🎟️ Origem", self._referral_label(refreshed), False),
                ("🧾 Candidatura", f"indisponível", True),
                ("📌 Canal", channel.mention, True),
                ("💬 Mensagem", f"indisponível", True),
            ],
        )

    async def approve_application(self, interaction: discord.Interaction, application_id: int) -> str:
        async with self._application_lock(application_id):
            application = await self.bot.db.get_beta_tester_application(application_id)
            if not application:
                raise RuntimeError("Candidatura não encontrada.")
            if str(application.get("status")) != "pending":
                raise RuntimeError("Esta candidatura já foi processada.")
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                raise RuntimeError("Contexto inválido para aprovação.")

            member = interaction.guild.get_member(int(application["user_id"]))
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(int(application["user_id"]))
                except discord.HTTPException:
                    raise RuntimeError("Membro da candidatura não foi encontrado no servidor.")

            beta_role = interaction.guild.get_role(self.bot.server_map.beta_program_role_id() or 0)
            if beta_role is None:
                raise RuntimeError("Cargo beta tester não foi encontrado.")

            role_applied = beta_role in member.roles
            if not role_applied:
                await member.add_roles(beta_role, reason=f"Aprovado no Programa Beta por {interaction.user}")
                role_applied = True

            card_generated = False
            card_data = self._build_tester_card_data(member, application_id)
            card_embed = self.build_tester_card_embed(member, card_data)
            card_generated = True

            card_sent_dm = False
            dm_status = "não_tentado"
            if self.bot.server_map.beta_program_send_dm_on_approval():
                try:
                    await member.send(embed=card_embed)
                    card_sent_dm = True
                    dm_status = "enviado"
                except discord.HTTPException:
                    dm_status = "falhou"

            card_sent_channel = False
            card_channel_id = self.bot.server_map.beta_program_card_channel_id()
            card_channel = interaction.guild.get_channel(card_channel_id) if card_channel_id else None
            if isinstance(card_channel, discord.TextChannel):
                channel_embed = self.build_tester_card_embed(
                    member,
                    card_data,
                    title="Carta Oficial de Beta Tester",
                    description=f"{member.mention} foi aprovado no Programa de Beta Testers.",
                    actor_label=interaction.user.mention,
                )
                await card_channel.send(embed=channel_embed)
                card_sent_channel = True

            await self.bot.db.update_beta_tester_application(
                application_id,
                {
                    "status": "approved",
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewed_by_id": interaction.user.id,
                    "review_result": "approved",
                    "rejection_reason": None,
                    "role_applied": int(role_applied),
                    "card_generated": int(card_generated),
                    "card_sent_dm": int(card_sent_dm),
                    "card_sent_channel": int(card_sent_channel),
                    "last_step": "reviewed",
                    "last_error": None,
                },
            )
            await self.refresh_application_message(interaction.guild, application_id)
            await self._dispatch_log(
                title="✅ Candidatura Beta Aprovada",
                description=f"{member.mention} foi aprovado no Programa Beta por {interaction.user.mention}.",
                color=self.bot.embeds.success_color,
                fields=[
                    ("🧾 Candidatura", f"indisponível", True),
                    ("🎟️ Origem", self._referral_label(application), False),
                    ("🏷️ Cargo aplicado", f"{beta_role.mention}", False),
                    ("📩 DM", dm_status, True),
                    ("🪪 Carteirinha canal", "enviada" if card_sent_channel else "não enviada", True),
                ],
            )
            return "Aprovação registrada com sucesso."

    async def reject_application(
        self,
        interaction: discord.Interaction,
        application_id: int,
        reason: str,
    ) -> str:
        async with self._application_lock(application_id):
            application = await self.bot.db.get_beta_tester_application(application_id)
            if not application:
                raise RuntimeError("Candidatura não encontrada.")
            if str(application.get("status")) != "pending":
                raise RuntimeError("Esta candidatura já foi processada.")
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                raise RuntimeError("Contexto inválido para reprovação.")

            await self.bot.db.update_beta_tester_application(
                application_id,
                {
                    "status": "rejected",
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewed_by_id": interaction.user.id,
                    "review_result": "rejected",
                    "rejection_reason": reason[:500],
                    "last_step": "reviewed",
                    "last_error": None,
                },
            )
            member = interaction.guild.get_member(int(application["user_id"]))
            if member and self.bot.server_map.beta_program_send_dm_on_rejection():
                rejection_embed = self.bot.embeds.make(
                    title="Atualização sobre sua candidatura",
                    description=(
                        "Agradecemos pelo interesse em participar do Programa de Beta Testers do Drakoria.\n\n"
                        "Neste momento, sua candidatura não foi aprovada. Valorizamos seu interesse em contribuir "
                        "e novas oportunidades podem surgir nas próximas fases do projeto."
                    ),
                    fields=[("Motivo informado", reason[:1000], False)],
                )
                try:
                    await member.send(embed=rejection_embed)
                except discord.HTTPException:
                    pass

            await self.refresh_application_message(interaction.guild, application_id)
            await self._dispatch_log(
                title="⚠️ Candidatura Beta Reprovada",
                description=f"Candidatura indisponível foi reprovada por {interaction.user.mention}.",
                color=self.bot.embeds.warning_color,
                fields=[
                    ("Motivo", reason[:1000], False),
                    ("Horário", self._now_human(), True),
                ],
            )
            return "Reprovação registrada com sucesso."

    async def refresh_application_message(self, guild: discord.Guild, application_id: int) -> None:
        application = await self.bot.db.get_beta_tester_application(application_id)
        if not application:
            return
        channel_id = application.get("application_channel_id")
        message_id = application.get("application_message_id")
        if not channel_id or not message_id:
            return
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(message_id))
        except discord.HTTPException:
            return
        member = guild.get_member(int(application["user_id"]))
        answers = json.loads(application.get("answers_json") or "{}")
        embed = self.build_application_embed(member, application, answers)
        view = self.bot.view_factory.build_beta_application_review_view(application_id) if application.get("status") == "pending" else None
        await message.edit(embed=embed, view=view)

    async def generate_tester_card(
        self,
        member: discord.Member,
        application_id: int,
        *,
        issued_label: str | None = None,
        joined_label: str | None = None,
        auth_code: str | None = None,
    ) -> tuple[bytes, str]:
        protocol = f"BT-{application_id:06d}"
        data = TesterCardData(
            holder_name=member.display_name,
            discord_user=str(member),
            discord_id=member.id,
            protocol=protocol,
            issued_label=issued_label or datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC"),
            joined_label=joined_label
            or (
                member.joined_at.astimezone(UTC).strftime("%d/%m/%Y")
                if member.joined_at is not None
                else "-"
            ),
            auth_code=auth_code or self._card_auth_code(member.id, application_id),
        )
        card_payload = await self.render_tester_card(data, avatar_asset=member.display_avatar.replace(format="png", size=512))
        return card_payload, f"drakoria-beta-card-{member.id}.png"

    async def render_tester_card(
        self,
        data: TesterCardData,
        *,
        avatar_asset: discord.Asset | None = None,
        avatar_bytes: bytes | None = None,
    ) -> bytes:
        width, height = 960, 1180

        card = Image.new("RGBA", (width, height), (7, 6, 14, 255))
        draw = ImageDraw.Draw(card)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(6 + (24 - 6) * ratio)
            g = int(6 + (10 - 6) * ratio)
            b = int(14 + (46 - 14) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((width - 640, -220, width + 260, 640), fill=(132, 70, 188, 95))
        glow_draw.ellipse((-360, 430, 560, 1160), fill=(244, 198, 77, 42))
        card = Image.alpha_composite(card, glow)
        draw = ImageDraw.Draw(card)

        for x in range(-height, width, 44):
            draw.line((x, 0, x + height, height), fill=(236, 194, 74, 14), width=1)

        outer = (24, 24, width - 24, height - 24)
        inner = (42, 42, width - 42, height - 42)
        header = (64, 58, width - 64, 224)
        avatar_panel = (92, 258, width - 92, 600)
        info_panel = (92, 634, width - 92, 914)
        status_box = (92, 944, width - 92, 1056)
        footer_box = (92, 1080, width - 92, 1134)

        draw.rounded_rectangle(outer, radius=36, fill=(10, 8, 18, 228), outline=(236, 194, 74, 255), width=4)
        draw.rounded_rectangle(inner, radius=30, outline=(131, 77, 192, 185), width=2)
        draw.rounded_rectangle(header, radius=22, fill=(25, 14, 44, 240), outline=(228, 188, 75, 190), width=2)
        draw.rounded_rectangle(avatar_panel, radius=30, fill=(19, 11, 36, 244), outline=(236, 194, 74, 220), width=3)
        draw.rounded_rectangle(info_panel, radius=30, fill=(15, 10, 30, 238), outline=(131, 77, 192, 210), width=2)
        draw.rounded_rectangle(status_box, radius=24, fill=(67, 30, 112, 246), outline=(236, 194, 74, 255), width=3)
        draw.rounded_rectangle(footer_box, radius=18, fill=(10, 7, 20, 246), outline=(131, 77, 192, 220), width=2)

        eyebrow_font = self._load_font(22, bold=True)
        label_font = self._load_font(28, bold=True)
        footer_font = self._load_font(18, bold=False)

        logo = await self._load_brand_logo_image()
        emblem_frame: tuple[int, int, int, int] | None = None
        if logo is not None:
            emblem_size = 86
            emblem = ImageOps.fit(logo, (emblem_size, emblem_size), method=Image.Resampling.LANCZOS)
            emblem_frame_size = emblem_size + 18
            emblem_margin_right = 18
            emblem_margin_top = 14
            frame_x2 = inner[2] - emblem_margin_right
            frame_y1 = inner[1] + emblem_margin_top
            emblem_frame = (
                frame_x2 - emblem_frame_size,
                frame_y1,
                frame_x2,
                frame_y1 + emblem_frame_size,
            )
            emblem_x = emblem_frame[0] + 12
            emblem_y = emblem_frame[1] + 12
            draw.rounded_rectangle(
                emblem_frame,
                radius=22,
                fill=(20, 11, 36, 244),
                outline=(236, 194, 74, 230),
                width=3,
            )
            card.paste(emblem, (emblem_x, emblem_y), emblem)

        title = "CARTEIRINHA OFICIAL BETA TESTER"
        subtitle = "Drakoria | Nexar | Programa de Validação Técnica"
        title_left = header[0] + 24
        title_right = (emblem_frame[0] - 18) if emblem_frame else (header[2] - 24)
        title_max_width = max(220, title_right - title_left)
        title_font = self._fit_text_font(draw, title, max_width=title_max_width, preferred_size=54, min_size=42, bold=True)
        subtitle_font = self._fit_text_font(draw, subtitle, max_width=title_max_width, preferred_size=28, min_size=22, bold=False)
        title_h = self._text_dimensions(draw, title, title_font)[1]
        subtitle_h = self._text_dimensions(draw, subtitle, subtitle_font)[1]
        title_y = header[1] + 24
        subtitle_y = title_y + title_h + 10
        draw.text((title_left, title_y), title, fill=(250, 224, 145, 255), font=title_font)
        draw.text((title_left, subtitle_y), subtitle, fill=(194, 154, 245, 255), font=subtitle_font)
        line_y = subtitle_y + subtitle_h + 18
        draw.line((title_left, line_y, title_right, line_y), fill=(232, 191, 82, 205), width=2)

        panel_title = "TESTER"
        panel_title_font = self._load_font(28, bold=True)
        panel_title_w, panel_title_h = self._text_dimensions(draw, panel_title, panel_title_font)
        panel_title_x = avatar_panel[0] + ((avatar_panel[2] - avatar_panel[0]) - panel_title_w) // 2
        panel_title_y = avatar_panel[1] + 22
        draw.text((panel_title_x, panel_title_y), panel_title, fill=(228, 194, 108, 255), font=panel_title_font)

        avatar_size = 228
        avatar_x = avatar_panel[0] + 48
        protocol_box = (avatar_panel[0] + 320, avatar_panel[1] + 92, avatar_panel[2] - 28, avatar_panel[3] - 42)
        avatar_area_top = panel_title_y + panel_title_h + 26
        avatar_area_bottom = protocol_box[1] - 16
        avatar_y = avatar_area_top + max(0, (avatar_area_bottom - avatar_area_top - avatar_size) // 2)
        draw.ellipse((avatar_x - 12, avatar_y - 12, avatar_x + avatar_size + 12, avatar_y + avatar_size + 12), fill=(11, 8, 22, 236))
        draw.ellipse((avatar_x - 14, avatar_y - 14, avatar_x + avatar_size + 14, avatar_y + avatar_size + 14), outline=(236, 194, 74, 245), width=4)

        avatar = Image.new("RGBA", (avatar_size, avatar_size), (48, 66, 104, 255))
        try:
            if avatar_bytes is None and avatar_asset is not None:
                avatar_bytes = await avatar_asset.read()
            if avatar_bytes is not None:
                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar = ImageOps.fit(avatar, (avatar_size, avatar_size), method=Image.Resampling.LANCZOS)
        except Exception:
            pass

        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)
        avatar_circle = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
        avatar_circle.paste(avatar, (0, 0), mask)
        card.paste(avatar_circle, (avatar_x, avatar_y), avatar_circle)

        draw.rounded_rectangle(protocol_box, radius=22, fill=(12, 8, 24, 232), outline=(131, 77, 192, 205), width=2)
        px = protocol_box[0] + 24
        box_width = protocol_box[2] - protocol_box[0] - 48
        draw.text((px, protocol_box[1] + 26), "PROTOCOLO", fill=(226, 190, 100, 255), font=eyebrow_font)
        protocol_font = self._fit_text_font(draw, data.protocol, max_width=box_width, preferred_size=46, min_size=38, bold=True)
        draw.text((px, protocol_box[1] + 58), data.protocol, fill=(250, 224, 145, 255), font=protocol_font)
        draw.text((px, protocol_box[1] + 128), "CÓDIGO DE AUTENTICAÇÃO", fill=(226, 190, 100, 255), font=eyebrow_font)
        code_font = self._fit_text_font(draw, data.auth_code, max_width=box_width, preferred_size=24, min_size=20, bold=True)
        draw.text((px, protocol_box[1] + 166), data.auth_code, fill=(212, 180, 248, 255), font=code_font)

        content_pad = 34
        name_label_y = info_panel[1] + 24
        draw.text((info_panel[0] + content_pad, name_label_y), "PORTADOR", fill=(226, 190, 100, 255), font=label_font)
        name_text = self._truncate_text(data.holder_name, 34)
        name_max_width = info_panel[2] - info_panel[0] - (content_pad * 2)
        name_font = self._fit_text_font(draw, name_text, max_width=name_max_width, preferred_size=60, min_size=48, bold=True)
        _, name_h = self._text_dimensions(draw, name_text, name_font)
        name_y = name_label_y + 26
        draw.text((info_panel[0] + content_pad, name_y), name_text, fill=(252, 241, 214, 255), font=name_font)

        grid_top = name_y + name_h + 18
        field_gap = 18
        column_gap = 22
        field_width = (info_panel[2] - info_panel[0] - (content_pad * 2) - column_gap) // 2

        def draw_field(x: int, y: int, label: str, value: str, *, max_width: int) -> None:
            draw.text((x, y), label, fill=(218, 183, 96, 255), font=eyebrow_font)
            value_font_fit = self._fit_text_font(
                draw,
                value,
                max_width=max_width,
                preferred_size=34,
                min_size=28,
                bold=True,
            )
            draw.text((x, y + 28), value, fill=(230, 208, 255, 255), font=value_font_fit)

        left_x = info_panel[0] + content_pad
        right_x = left_x + field_width + column_gap
        draw_field(left_x, grid_top, "USUÁRIO", self._truncate_text(data.discord_user, 24), max_width=field_width)
        draw_field(left_x, grid_top + 78, "EMISSÃO", data.issued_label, max_width=field_width)
        draw_field(right_x, grid_top + 78, "INGRESSO", data.joined_label, max_width=field_width)

        status_label = "STATUS"
        status_text = data.status
        draw.text((status_box[0] + 24, status_box[1] + 12), status_label, fill=(250, 224, 145, 255), font=eyebrow_font)
        status_font_fit = self._fit_text_font(
            draw,
            status_text,
            max_width=status_box[2] - status_box[0] - 48,
            preferred_size=46,
            min_size=34,
            bold=True,
        )
        status_w, status_h = self._text_dimensions(draw, status_text, status_font_fit)
        status_x = status_box[0] + ((status_box[2] - status_box[0]) - status_w) // 2
        status_y = status_box[1] + 42
        draw.text((status_x, status_y), status_text, fill=(250, 224, 145, 255), font=status_font_fit)

        footer_line = f"ID {data.discord_id}   |   AUTENTICAÇÃO {data.auth_code}"
        footer_font_fit = self._fit_text_font(
            draw,
            footer_line,
            max_width=footer_box[2] - footer_box[0] - 40,
            preferred_size=20,
            min_size=18,
            bold=True,
        )
        draw.text((footer_box[0] + 20, footer_box[1] + 8), footer_line, fill=(250, 224, 145, 255), font=footer_font_fit)
        draw.text((footer_box[0] + 20, footer_box[1] + 30), "Documento oficial do Programa Beta Drakoria.", fill=(204, 170, 244, 255), font=footer_font)

        out = io.BytesIO()
        card.convert("RGB").save(out, format="PNG", optimize=True)
        out.seek(0)
        return out.getvalue()

    async def reissue_tester_card(
        self,
        guild: discord.Guild,
        member: discord.Member,
        *,
        actor: discord.Member | discord.User | None = None,
        application_id: int | None = None,
        issued_label: str | None = None,
        joined_label: str | None = None,
        auth_code: str | None = None,
    ) -> dict[str, Any]:
        application = (
            await self.bot.db.get_beta_tester_application(application_id)
            if application_id is not None
            else await self.bot.db.get_latest_beta_tester_application(guild.id, member.id)
        )
        if application and (int(application["guild_id"]) != guild.id or int(application["user_id"]) != member.id):
            fallback_application = await self.bot.db.get_latest_beta_tester_application(guild.id, member.id)
            if fallback_application and str(fallback_application.get("status")) == "approved":
                application = fallback_application
            else:
                raise RuntimeError(
                    "O candidatura_id informado não pertence ao usuário selecionado neste servidor."
                )
        if not application:
            beta_role_id = self.bot.server_map.beta_program_role_id()
            beta_role = guild.get_role(beta_role_id or 0)
            if beta_role is None or beta_role not in member.roles:
                raise RuntimeError(
                    "Nenhuma candidatura beta foi encontrada para esse usuário, e ele não possui o cargo Beta Tester."
                )
            application_id = await self.bot.db.create_beta_tester_application(
                guild.id,
                member.id,
                panel_channel_id=None,
                panel_message_id=None,
                status="approved",
            )
            await self.bot.db.update_beta_tester_application(
                application_id,
                {
                    "submitted_at": datetime.now(UTC).isoformat(),
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewed_by_id": actor.id if actor else None,
                    "review_result": "approved",
                    "role_applied": 1,
                    "last_step": "manual_reissue_bootstrap",
                    "last_error": None,
                },
            )
            application = await self.bot.db.get_beta_tester_application(application_id)
            if not application:
                raise RuntimeError("Não foi possível criar o registro histórico da candidatura beta.")
        if str(application.get("status")) != "approved":
            raise RuntimeError("A carteirinha só pode ser reemitida para candidaturas já aprovadas.")

        resolved_application_id = int(application["id"])
        card_data = self._build_tester_card_data(
            member,
            resolved_application_id,
            issued_label=issued_label,
            joined_label=joined_label,
            auth_code=auth_code,
        )
        card_embed = self.build_tester_card_embed(member, card_data)

        dm_sent = False
        try:
            await member.send(embed=card_embed)
            dm_sent = True
        except discord.HTTPException:
            dm_sent = False

        channel_sent = False
        card_channel_id = self.bot.server_map.beta_program_card_channel_id()
        card_channel = guild.get_channel(card_channel_id) if card_channel_id else None
        if isinstance(card_channel, discord.TextChannel):
            channel_embed = self.build_tester_card_embed(
                member,
                card_data,
                title="Carta Oficial de Beta Tester",
                description=f"{member.mention} recebeu a carteirinha Beta Tester atualizada.",
                actor_label=actor.mention if actor else "sistema",
            )
            await card_channel.send(embed=channel_embed)
            channel_sent = True

        await self.bot.db.update_beta_tester_application(
            resolved_application_id,
            {
                "card_generated": 1,
                "card_sent_dm": int(dm_sent),
                "card_sent_channel": int(channel_sent),
                "last_error": None if dm_sent and channel_sent else "Falha parcial ao reemitir carteirinha.",
            },
        )
        return {
            "application_id": resolved_application_id,
            "dm_sent": dm_sent,
            "channel_sent": channel_sent,
            "channel_id": card_channel_id,
        }

    def _build_tester_card_data(
        self,
        member: discord.Member,
        application_id: int,
        *,
        issued_label: str | None = None,
        joined_label: str | None = None,
        auth_code: str | None = None,
    ) -> TesterCardData:
        return TesterCardData(
            holder_name=member.display_name,
            discord_user=str(member),
            discord_id=member.id,
            protocol=f"BT-{application_id:06d}",
            issued_label=issued_label or datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC"),
            joined_label=joined_label
            or (
                member.joined_at.astimezone(UTC).strftime("%d/%m/%Y")
                if member.joined_at is not None
                else "-"
            ),
            auth_code=auth_code or self._card_auth_code(member.id, application_id),
        )

    def build_tester_card_embed(
        self,
        member: discord.Member,
        data: TesterCardData,
        *,
        title: str | None = None,
        description: str | None = None,
        actor_label: str | None = None,
    ) -> discord.Embed:
        lines = [
            "Registro oficial de identidade do Programa Beta de Drakoria.",
            "",
            f"**Portador:** {member.mention}",
            f"**Usuario Discord:** `{data.discord_user}`",
            f"**Status:** **{data.status}**",
        ]
        embed = self.bot.embeds.make(
            title=title or "Carta Oficial de Beta Tester",
            description=description or "\n".join(lines),
            color=self.bot.embeds.success_color,
            fields=[
                ("Protocolo", f"`{data.protocol}`", True),
                ("Emissao", f"`{data.issued_label}`", True),
                ("Ingresso", f"`{data.joined_label}`", True),
                ("Codigo de Autenticacao", f"`{data.auth_code}`", False),
                ("Identificacao", f"`{data.discord_id}`", True),
                ("Perfil", member.mention, True),
                ("Condicao Operacional", "Aprovado como Beta Tester", False),
            ],
            thumbnail_url=member.display_avatar.url,
            author_name="Drakoria | Programa Beta",
            author_icon_url=self.bot.embeds.footer_icon or self.bot.embeds.guild_icon_url,
            footer_text="Documento oficial do Programa Beta Drakoria",
            footer_icon_url=self.bot.embeds.footer_icon or self.bot.embeds.guild_icon_url,
            timestamp=True,
        )
        if actor_label:
            embed.add_field(name="Lavrado por", value=actor_label, inline=True)
        return embed

    async def reissue_all_tester_cards(
        self,
        guild: discord.Guild,
        *,
        actor: discord.Member | discord.User | None = None,
    ) -> dict[str, Any]:
        approved = await self.bot.db.list_beta_tester_applications(guild.id, status="approved", limit=500)
        latest_by_user: dict[int, dict[str, Any]] = {}
        for application in approved:
            user_id = int(application["user_id"])
            if user_id not in latest_by_user:
                latest_by_user[user_id] = application

        target_user_ids: set[int] = set(latest_by_user)
        beta_role = guild.get_role(self.bot.server_map.beta_program_role_id() or 0)
        if beta_role is not None:
            target_user_ids.update(member.id for member in beta_role.members if not member.bot)

        results: list[dict[str, Any]] = []
        for user_id in sorted(target_user_ids):
            application = latest_by_user.get(user_id)
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.HTTPException:
                    results.append(
                        {
                            "user_id": user_id,
                            "application_id": int(application["id"]) if application else None,
                            "status": "member_not_found",
                        }
                    )
                    continue

            try:
                result = await self.reissue_tester_card(
                    guild,
                    member,
                    actor=actor,
                    application_id=int(application["id"]) if application else None,
                )
                results.append(
                    {
                        "user_id": user_id,
                        "application_id": result["application_id"],
                        "status": "ok",
                        "dm_sent": result["dm_sent"],
                        "channel_sent": result["channel_sent"],
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "user_id": user_id,
                        "application_id": int(application["id"]) if application else None,
                        "status": "error",
                        "error": str(exc)[:300],
                    }
                )

        success_count = sum(1 for item in results if item["status"] == "ok")
        fail_count = len(results) - success_count
        return {
            "total": len(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
        }

    @staticmethod
    def _card_auth_code(member_id: int, application_id: int) -> str:
        payload = f"{member_id}:{application_id}".encode("utf-8")
        digest = hashlib.sha1(payload).hexdigest()[:10].upper()
        return f"DRK-{application_id:06d}-{digest}"

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        value = text.strip()
        if len(value) <= max_chars:
            return value
        if max_chars <= 3:
            return value[:max_chars]
        return value[: max_chars - 3].rstrip() + "..."

    def _fit_text_font(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        max_width: int,
        preferred_size: int,
        min_size: int,
        bold: bool,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        size = preferred_size
        while size >= min_size:
            font = self._load_font(size, bold=bold)
            width, _ = self._text_dimensions(draw, text, font)
            if width <= max_width:
                return font
            size -= 1
        return self._load_font(min_size, bold=bold)

    @staticmethod
    def _text_dimensions(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> tuple[int, int]:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top

    async def _load_brand_logo_image(self) -> Image.Image | None:
        logo_url = self._brand_logo_url()
        if not logo_url:
            return None
        cached = self._brand_logo_cache.get(logo_url)
        if cached is not None:
            return cached.copy()
        logo_bytes = await asyncio.to_thread(self._download_logo_bytes, logo_url)
        if not logo_bytes:
            return None
        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        except OSError:
            return None
        self._brand_logo_cache[logo_url] = logo
        return logo.copy()

    def _brand_logo_url(self) -> str | None:
        style = self.bot.server_map.style()
        for key in ("logo_url", "thumbnail_url", "brand_logo_url", "footer_icon_url"):
            value = style.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return self.bot.server_map.announcements_logo_url()

    def _download_logo_bytes(self, logo_url: str) -> bytes | None:
        if logo_url.startswith(("http://", "https://")):
            request = Request(
                logo_url,
                headers={"User-Agent": "DrakoriaBot/1.0"},
            )
            try:
                with urlopen(request, timeout=8) as response:
                    return response.read()
            except Exception:
                return None

        local_path = self._resolve_local_logo_path(logo_url)
        if local_path is None:
            return None
        try:
            return local_path.read_bytes()
        except OSError:
            return None

    def _resolve_local_logo_path(self, logo_url: str) -> Path | None:
        candidate = Path(logo_url.strip())
        if candidate.is_absolute():
            return candidate if candidate.exists() else None

        base_dirs: list[Path] = [Path.cwd()]
        runtime_config = getattr(getattr(self.bot, "runtime", None), "config_path", None)
        if isinstance(runtime_config, Path):
            base_dirs.extend([runtime_config.parent, runtime_config.parent.parent])

        for base in base_dirs:
            try:
                resolved = (base / candidate).resolve()
            except OSError:
                continue
            if resolved.exists():
                return resolved
        return None

    @staticmethod
    def _load_font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = []
        if bold:
            candidates.extend(
                [
                    str((Path.cwd() / "data" / "fonts" / "arialbd.ttf").resolve()),
                    "C:/Windows/Fonts/segoeuib.ttf",
                    "C:/Windows/Fonts/arialbd.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                ]
            )
        else:
            candidates.extend(
                [
                    str((Path.cwd() / "data" / "fonts" / "arial.ttf").resolve()),
                    "C:/Windows/Fonts/segoeui.ttf",
                    "C:/Windows/Fonts/arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                    "/usr/share/fonts/TTF/DejaVuSans.ttf",
                ]
            )
        for font_path in candidates:
            try:
                return ImageFont.truetype(font_path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def build_application_embed(
        self,
        member: discord.Member | None,
        application: dict[str, Any],
        answers: dict[str, str],
    ) -> discord.Embed:
        status = str(application.get("status", "unknown"))
        reviewer = application.get("reviewed_by_id")
        description = (
            f"Candidatura oficial do Programa Beta.\n"
            f"Status atual: **{status.upper()}**\n"
            f"Origem: **{self._referral_label(application)}**"
        )
        embed = self.bot.embeds.make(
            title="🧪 Candidatura Beta Tester",
            description=description,
            fields=[
                ("👤 Usuário", f"{member.mention if member else f'<@{application['user_id']}>'}", False),
                ("🕒 Criada em", f"`{application.get('created_at')}`", True),
                ("📨 Enviada em", f"`{application.get('submitted_at') or '-'}`", True),
                ("🛡️ Revisada por", f"<@{reviewer}>" if reviewer else "-", True),
            ],
        )
        for key, label in self.questions():
            value = str(answers.get(key, "-")).strip() or "-"
            embed.add_field(name=label[:256], value=value[:1024], inline=False)
        if application.get("rejection_reason"):
            embed.add_field(name="Motivo da Reprovação", value=str(application["rejection_reason"])[:1024], inline=False)
        return embed

    async def _dispatch_log(
        self,
        *,
        title: str,
        description: str,
        color: int,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        channel_id = self.bot.server_map.beta_program_log_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            self.bot.log.warning("Canal de log beta não encontrado: %s", channel_id)
            return
        embed = self.bot.embeds.make(title=title, description=description, color=color, fields=fields or [])
        embed.timestamp = datetime.now(UTC)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            self.bot.log.warning("Falha ao enviar log beta: %s", exc)

    def _member_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    def _application_lock(self, application_id: int) -> asyncio.Lock:
        if application_id not in self._application_locks:
            self._application_locks[application_id] = asyncio.Lock()
        return self._application_locks[application_id]

    def _influencer_code_lock(self, guild_id: int, normalized_code: str) -> asyncio.Lock:
        key = (guild_id, normalized_code)
        if key not in self._influencer_code_locks:
            self._influencer_code_locks[key] = asyncio.Lock()
        return self._influencer_code_locks[key]

    @staticmethod
    def _now_human() -> str:
        now = datetime.now(UTC)
        return f"{discord.utils.format_dt(now, style='F')} | `{now.isoformat()}`"

    @staticmethod
    def questions() -> list[tuple[str, str]]:
        return [
            ("age", "1) Sua idade"),
            ("availability", "2) Disponibilidade para testes"),
            ("bug_reaction", "3) Como você reporta bugs?"),
            ("detailist_example", "4) Experiência com testes ou feedback"),
            ("good_tester", "5) Por que foi indicado ao beta fechado?"),
            ("critical_failure_report", "6) Como reportaria uma falha crítica?"),
            ("best_test_type", "7) O que mais quer testar no Drakoria?"),
            ("consistency_commitment", "8) Frequência de participação"),
            ("why_join", "9) Por que quer testar Drakoria nesta fase?"),
            ("expected_contribution", "10) Que feedback pode entregar à equipe?"),
        ]

    @classmethod
    def question_keys(cls) -> list[str]:
        return [key for key, _ in cls.questions()]

    @staticmethod
    def normalize_influencer_code(code: str | None) -> str:
        if not code:
            return ""
        allowed = []
        for char in code.strip().upper():
            if char.isalnum():
                allowed.append(char)
            elif char in {"-", "_"}:
                allowed.append("-")
        return "".join(allowed)[:32]

    @staticmethod
    def _referral_label(application: dict[str, Any] | None) -> str:
        if not application or str(application.get("referral_type") or "direct") != "influencer":
            return "Direta / sem influencer"
        code = str(application.get("influencer_code") or "-")
        name = str(application.get("influencer_name") or "Influencer")
        owner = application.get("influencer_owner_id")
        owner_label = f" | <@{owner}>" if owner else ""
        return f"{name} (`{code}`){owner_label}"

    @staticmethod
    def _referral_label_from_parts(influencer: dict[str, Any] | None) -> str:
        if not influencer:
            return "Direta / sem influencer"
        owner = influencer.get("owner_user_id")
        owner_label = f" | <@{owner}>" if owner else ""
        return f"{influencer['influencer_name']} (`{influencer['code']}`){owner_label}"




