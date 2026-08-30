from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import discord


HIERARCHY_ORDER = {
    "leader": 4,
    "subleader": 3,
    "officer": 2,
    "member": 1,
}


@dataclass(slots=True)
class GuildCreateResult:
    status: str
    detail: str
    guild_profile_id: int | None = None
    application_id: int | None = None


class DiscordGuildService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    def enabled(self) -> bool:
        return self.bot.server_map.discord_guilds_enabled()

    async def bootstrap(self, guild: discord.Guild) -> None:
        if not self.enabled():
            return
        await self.publish_mural(guild)

    async def create_guild(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        name: str,
        emoji: str,
        description: str,
    ) -> GuildCreateResult:
        self._ensure_enabled()
        await self._ensure_member_without_guild(member)
        clean_name = self._normalize_name(name)
        clean_description = self._normalize_description(description)
        normalized_emoji = self._validate_emoji(interaction.guild, emoji)
        slug = self._slugify(clean_name)
        await self._ensure_name_available(interaction.guild.id, clean_name, slug)
        pending = await self.bot.db.get_pending_discord_guild_application_by_user(interaction.guild.id, member.id)
        if pending:
            raise RuntimeError("Voce ja possui uma criacao de guilda pendente de revisao.")

        if self.bot.server_map.discord_guilds_auto_approve_creation():
            profile_id = await self._approve_profile_creation(
                interaction.guild,
                member,
                name=clean_name,
                slug=slug,
                emoji=normalized_emoji,
                description=clean_description,
                approved_by_id=self.bot.user.id if self.bot.user else None,
            )
            await self.refresh_mural(interaction.guild)
            return GuildCreateResult(
                status="approved",
                detail="Sua guilda foi criada e oficializada no Discord.",
                guild_profile_id=profile_id,
            )

        application_id = await self.bot.db.create_discord_guild_application(
            interaction.guild.id,
            member.id,
            clean_name,
            slug,
            normalized_emoji,
            clean_description,
        )
        await self._publish_creation_review(interaction.guild, application_id)
        return GuildCreateResult(
            status="pending_review",
            detail="Sua guilda foi enviada para aprovacao da staff.",
            application_id=application_id,
        )

    async def approve_creation_application(self, interaction: discord.Interaction, application_id: int) -> str:
        application = await self.bot.db.get_discord_guild_application(application_id)
        if not application or str(application.get("status")) != "pending":
            raise RuntimeError("Solicitacao de guilda nao encontrada ou ja processada.")
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise RuntimeError("Contexto invalido para aprovacao.")
        requester = interaction.guild.get_member(int(application["requester_user_id"]))
        if requester is None:
            try:
                requester = await interaction.guild.fetch_member(int(application["requester_user_id"]))
            except discord.HTTPException:
                raise RuntimeError("Solicitante nao encontrado no servidor.")
        await self._ensure_member_without_guild(requester)
        await self._ensure_name_available(
            interaction.guild.id,
            str(application["name"]),
            str(application["slug"]),
        )
        profile_id = await self._approve_profile_creation(
            interaction.guild,
            requester,
            name=str(application["name"]),
            slug=str(application["slug"]),
            emoji=str(application["emoji"]),
            description=str(application["description"]),
            approved_by_id=interaction.user.id,
        )
        await self.bot.db.update_discord_guild_application(
            application_id,
            {
                "status": "approved",
                "reviewed_by_id": interaction.user.id,
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
        )
        await self.refresh_mural(interaction.guild)
        return f"Guilda aprovada com sucesso. Registro oficial: `{profile_id}`."

    async def reject_creation_application(self, interaction: discord.Interaction, application_id: int, reason: str) -> str:
        application = await self.bot.db.get_discord_guild_application(application_id)
        if not application or str(application.get("status")) != "pending":
            raise RuntimeError("Solicitacao de guilda nao encontrada ou ja processada.")
        await self.bot.db.update_discord_guild_application(
            application_id,
            {
                "status": "rejected",
                "reviewed_by_id": interaction.user.id if isinstance(interaction.user, discord.Member) else None,
                "review_reason": reason.strip()[:300],
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
        )
        return "Solicitacao de guilda recusada."

    async def get_profile_for_member(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        return await self.bot.db.get_discord_guild_membership(user_id, guild_id)

    async def get_profile_by_name(self, guild_id: int, name: str) -> dict[str, Any] | None:
        return await self.bot.db.get_discord_guild_profile_by_name(guild_id, name)

    async def build_profile_embed(self, guild: discord.Guild, profile: dict[str, Any]) -> discord.Embed:
        members = await self.bot.db.list_discord_guild_members(int(profile["guild_profile_id"] if "guild_profile_id" in profile else profile["id"]))
        leader_id = int(profile["leader_user_id"])
        leader = guild.get_member(leader_id)
        member_count = len(members)
        ranking = await self.guild_rankings(guild)
        ranking_position = next((idx for idx, item in enumerate(ranking, start=1) if int(item["id"]) == int(profile.get("id") or profile.get("guild_profile_id"))), None)
        role_id = profile.get("role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        voice_channel_id = profile.get("linked_voice_channel_id")
        voice_label = f"<#{voice_channel_id}>" if voice_channel_id else "Nao definida"
        embed = self.bot.embeds.make(
            title=f"{profile.get('emoji', '')}「{profile.get('name', 'Guilda')}」",
            description=str(profile.get("description") or "Sem descricao oficial."),
            fields=[
                ("Lider", leader.mention if leader else f"<@{leader_id}>", True),
                ("Membros", str(member_count), True),
                ("Recrutamento", "Aberto" if int(profile.get("recruitment_open") or 0) else "Fechado", True),
                ("Criada em", f"`{profile.get('guild_created_at') or profile.get('created_at')}`", False),
                ("Ranking", f"#{ranking_position}" if ranking_position else "Sem ranking", True),
                ("Cargo", role.mention if role else "Nao criado", True),
                ("Call", voice_label, True),
            ],
            color=self.bot.embeds.success_color if int(profile.get("recruitment_open") or 0) else self.bot.embeds.default_color,
        )
        emblem = str(profile.get("emblem_url") or "").strip()
        if emblem:
            embed.set_thumbnail(url=emblem)
        achievements = self._load_json_list(profile.get("achievements_json"))
        if achievements:
            embed.add_field(name="Conquistas", value="\n".join(f"- {item}" for item in achievements[:6]), inline=False)
        member_lines = []
        for row in members[:12]:
            member_lines.append(f"<@{row['user_id']}> | `{self._hierarchy_label(str(row['hierarchy']))}`")
        embed.add_field(name="Quadro de Membros", value="\n".join(member_lines) if member_lines else "Sem membros listados.", inline=False)
        return embed

    async def guild_rankings(self, guild: discord.Guild) -> list[dict[str, Any]]:
        profiles = await self.bot.db.list_discord_guild_profiles(guild.id)
        results: list[dict[str, Any]] = []
        for profile in profiles:
            count = await self.bot.db.count_discord_guild_members(int(profile["id"]))
            results.append({**profile, "member_count": count})
        results.sort(key=lambda item: (-int(item["member_count"]), str(item["created_at"])))
        return results

    async def build_ranking_embed(self, guild: discord.Guild) -> discord.Embed:
        ranking = await self.guild_rankings(guild)
        if not ranking:
            return self.bot.embeds.make(title="Ranking das Guildas", description="Nenhuma guilda oficializada ainda.")
        lines = []
        for index, item in enumerate(ranking[:10], start=1):
            status = "Recrutando" if int(item.get("recruitment_open") or 0) else "Fechada"
            lines.append(f"**{index}.** {item['emoji']}「{item['name']}」 | `{item['member_count']} membros` | {status}")
        return self.bot.embeds.make(title="Ranking das Guildas", description="\n".join(lines))

    async def invite_member(self, interaction: discord.Interaction, actor: discord.Member, target: discord.Member) -> int:
        profile = await self._require_actor_guild_with_rank(interaction.guild.id, actor.id, minimum="officer")
        if target.bot:
            raise RuntimeError("Bots nao podem entrar em guildas sociais.")
        await self._ensure_member_without_guild(target)
        existing = await self.bot.db.get_pending_discord_guild_invite(int(profile["guild_profile_id"]), target.id)
        if existing:
            raise RuntimeError("Ja existe um convite pendente para este usuario.")
        invite_id = await self.bot.db.create_discord_guild_invite(int(profile["guild_profile_id"]), target.id, actor.id)
        embed = self.bot.embeds.make(
            title="Convite de Guilda",
            description=f"{actor.mention} convidou voce para entrar em {profile['emoji']}「{profile['name']}」.",
        )
        view = self.bot.view_factory.build_discord_guild_invite_view(invite_id)
        try:
            await target.send(embed=embed, view=view)
        except discord.HTTPException:
            pass
        return invite_id

    async def accept_invite(self, interaction: discord.Interaction, invite_id: int) -> str:
        invite = await self.bot.db.get_discord_guild_invite(invite_id)
        if not invite or str(invite.get("status")) != "pending":
            raise RuntimeError("Convite nao encontrado ou ja processado.")
        guild = interaction.guild or self.bot.get_guild(self.bot.server_map.guild_id())
        if guild is None:
            raise RuntimeError("Servidor oficial nao encontrado para concluir o convite.")
        member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                raise RuntimeError("Nao foi possivel localizar voce no servidor oficial.")
        if int(invite["invited_user_id"]) != interaction.user.id:
            raise RuntimeError("Este convite nao pertence a voce.")
        await self._ensure_member_without_guild(member)
        profile = await self.bot.db.get_discord_guild_profile(int(invite["guild_profile_id"]))
        if not profile or str(profile.get("status")) != "approved":
            raise RuntimeError("A guilda deste convite nao esta mais disponivel.")
        await self._add_member_to_guild(
            guild,
            profile,
            member,
            hierarchy="member",
            invited_by_id=int(invite["invited_by_id"]),
        )
        await self.bot.db.update_discord_guild_invite(
            invite_id,
            {"status": "accepted", "responded_at": datetime.now(UTC).isoformat()},
        )
        await self.refresh_mural(guild)
        return f"Voce entrou em {profile['emoji']}「{profile['name']}」."

    async def decline_invite(self, interaction: discord.Interaction, invite_id: int) -> str:
        invite = await self.bot.db.get_discord_guild_invite(invite_id)
        if not invite or str(invite.get("status")) != "pending":
            raise RuntimeError("Convite nao encontrado ou ja processado.")
        if int(invite["invited_user_id"]) != interaction.user.id:
            raise RuntimeError("Este convite nao pertence a voce.")
        await self.bot.db.update_discord_guild_invite(
            invite_id,
            {"status": "declined", "responded_at": datetime.now(UTC).isoformat()},
        )
        return "Convite recusado."

    async def leave_guild(self, guild: discord.Guild, member: discord.Member) -> str:
        membership = await self.bot.db.get_discord_guild_membership(member.id, guild.id)
        if not membership:
            raise RuntimeError("Voce nao participa de nenhuma guilda.")
        if str(membership["hierarchy"]) == "leader":
            raise RuntimeError("O lider nao pode sair sem transferir a lideranca ou encerrar a guilda.")
        await self._remove_member_from_guild(guild, membership, member)
        await self.refresh_mural(guild)
        return "Saida da guilda concluida com sucesso."

    async def remove_member(self, guild: discord.Guild, actor: discord.Member, target: discord.Member) -> str:
        actor_membership = await self._require_actor_guild_with_rank(guild.id, actor.id, minimum="officer")
        target_membership = await self.bot.db.get_discord_guild_membership(target.id, guild.id)
        if not target_membership or int(target_membership["guild_profile_id"]) != int(actor_membership["guild_profile_id"]):
            raise RuntimeError("Este usuario nao pertence a sua guilda.")
        if self._hierarchy_power(str(target_membership["hierarchy"])) >= self._hierarchy_power(str(actor_membership["hierarchy"])):
            raise RuntimeError("Voce nao pode remover alguem com cargo igual ou superior ao seu.")
        await self._remove_member_from_guild(guild, target_membership, target)
        await self.refresh_mural(guild)
        return "Membro removido da guilda."

    async def update_member_hierarchy(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        hierarchy: str,
    ) -> str:
        hierarchy = hierarchy.strip().lower()
        if hierarchy not in {"subleader", "officer", "member"}:
            raise RuntimeError("Hierarquia invalida.")
        actor_membership = await self._require_actor_guild_with_rank(guild.id, actor.id, minimum="leader")
        target_membership = await self.bot.db.get_discord_guild_membership(target.id, guild.id)
        if not target_membership or int(target_membership["guild_profile_id"]) != int(actor_membership["guild_profile_id"]):
            raise RuntimeError("Este usuario nao pertence a sua guilda.")
        if str(target_membership["hierarchy"]) == "leader":
            raise RuntimeError("Nao e possivel alterar a hierarquia do lider por aqui.")
        await self.bot.db.upsert_discord_guild_member(
            int(target_membership["guild_profile_id"]),
            target.id,
            hierarchy,
            invited_by_id=target_membership.get("invited_by_id"),
            original_nickname=target_membership.get("original_nickname"),
        )
        return f"Hierarquia atualizada para `{self._hierarchy_label(hierarchy)}`."

    async def transfer_leadership(self, guild: discord.Guild, actor: discord.Member, target: discord.Member) -> str:
        actor_membership = await self._require_actor_guild_with_rank(guild.id, actor.id, minimum="leader")
        target_membership = await self.bot.db.get_discord_guild_membership(target.id, guild.id)
        if not target_membership or int(target_membership["guild_profile_id"]) != int(actor_membership["guild_profile_id"]):
            raise RuntimeError("O novo lider precisa estar na sua guilda.")
        guild_profile_id = int(actor_membership["guild_profile_id"])
        await self.bot.db.update_discord_guild_profile(guild_profile_id, {"leader_user_id": target.id})
        await self.bot.db.upsert_discord_guild_member(guild_profile_id, actor.id, "subleader", original_nickname=actor_membership.get("original_nickname"))
        await self.bot.db.upsert_discord_guild_member(guild_profile_id, target.id, "leader", original_nickname=target_membership.get("original_nickname"))
        return f"Lideranca transferida para {target.mention}."

    async def set_description(self, guild: discord.Guild, actor: discord.Member, description: str) -> str:
        membership = await self._require_actor_guild_with_rank(guild.id, actor.id, minimum="leader")
        await self.bot.db.update_discord_guild_profile(
            int(membership["guild_profile_id"]),
            {"description": self._normalize_description(description)},
        )
        await self.refresh_mural(guild)
        return "Descricao atualizada."

    async def set_recruitment_state(self, guild: discord.Guild, actor: discord.Member, is_open: bool) -> str:
        membership = await self._require_actor_guild_with_rank(guild.id, actor.id, minimum="leader")
        guild_profile_id = int(membership["guild_profile_id"])
        await self.bot.db.update_discord_guild_profile(guild_profile_id, {"recruitment_open": int(is_open)})
        profile = await self.bot.db.get_discord_guild_profile(guild_profile_id)
        if is_open and profile:
            await self.publish_recruitment_post(guild, profile)
        await self.refresh_mural(guild)
        return "Recrutamento aberto." if is_open else "Recrutamento fechado."

    async def submit_emblem(self, guild: discord.Guild, actor: discord.Member, image_url: str) -> str:
        membership = await self._require_actor_guild_with_rank(guild.id, actor.id, minimum="leader")
        profile = await self.bot.db.get_discord_guild_profile(int(membership["guild_profile_id"]))
        if not profile:
            raise RuntimeError("Guilda nao encontrada.")
        metadata = self._load_metadata(profile.get("metadata_json"))
        cooldown_hours = self.bot.server_map.discord_guilds_emblem_cooldown_hours()
        last_sent = self._parse_dt(metadata.get("last_emblem_submission_at"))
        if cooldown_hours > 0 and last_sent and datetime.now(UTC) - last_sent < timedelta(hours=cooldown_hours):
            raise RuntimeError("Ainda existe cooldown para enviar um novo emblema.")
        review_id = await self.bot.db.create_discord_guild_emblem_review(int(profile["id"]), actor.id, image_url.strip())
        metadata["last_emblem_submission_at"] = datetime.now(UTC).isoformat()
        await self.bot.db.update_discord_guild_profile(int(profile["id"]), {"metadata_json": json.dumps(metadata, ensure_ascii=False)})
        await self._publish_emblem_review(guild, profile, review_id, image_url.strip(), actor)
        return "Emblema enviado para revisao da staff."

    async def approve_emblem_review(self, interaction: discord.Interaction, review_id: int) -> str:
        review = await self.bot.db.get_discord_guild_emblem_review(review_id)
        if not review or str(review.get("status")) != "pending":
            raise RuntimeError("Revisao de emblema nao encontrada ou ja processada.")
        profile = await self.bot.db.get_discord_guild_profile(int(review["guild_profile_id"]))
        if not profile:
            raise RuntimeError("Guilda vinculada ao emblema nao encontrada.")
        await self.bot.db.update_discord_guild_profile(int(profile["id"]), {"emblem_url": review["image_url"]})
        await self.bot.db.update_discord_guild_emblem_review(
            review_id,
            {
                "status": "approved",
                "reviewed_by_id": interaction.user.id if isinstance(interaction.user, discord.Member) else None,
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
        )
        return "Emblema aprovado e aplicado ao perfil da guilda."

    async def reject_emblem_review(self, interaction: discord.Interaction, review_id: int, reason: str) -> str:
        review = await self.bot.db.get_discord_guild_emblem_review(review_id)
        if not review or str(review.get("status")) != "pending":
            raise RuntimeError("Revisao de emblema nao encontrada ou ja processada.")
        await self.bot.db.update_discord_guild_emblem_review(
            review_id,
            {
                "status": "rejected",
                "reviewed_by_id": interaction.user.id if isinstance(interaction.user, discord.Member) else None,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "rejection_reason": reason.strip()[:300],
            },
        )
        return "Emblema recusado."

    async def publish_recruitment_post(self, guild: discord.Guild, profile: dict[str, Any]) -> discord.Message | None:
        channel_id = self.bot.server_map.discord_guilds_recruitment_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return None
        members = await self.bot.db.list_discord_guild_members(int(profile["id"]))
        leader = guild.get_member(int(profile["leader_user_id"]))
        embed = self.bot.embeds.make(
            title=f"{profile['emoji']} Guilda {profile['name']} abriu recrutamento!",
            description=str(profile.get("description") or "Sem descricao."),
            fields=[
                ("Lider", leader.mention if leader else f"<@{profile['leader_user_id']}>", True),
                ("Membros", str(len(members)), True),
                ("Status", "Recrutando", True),
            ],
            color=self.bot.embeds.success_color,
        )
        view = self.bot.view_factory.build_discord_guild_recruitment_view(int(profile["id"]))
        message = await channel.send(embed=embed, view=view)
        metadata = self._load_metadata(profile.get("metadata_json"))
        metadata["last_recruitment_message_id"] = message.id
        metadata["last_recruitment_channel_id"] = channel.id
        await self.bot.db.update_discord_guild_profile(int(profile["id"]), {"metadata_json": json.dumps(metadata, ensure_ascii=False)})
        return message

    async def publish_mural(self, guild: discord.Guild) -> discord.Message:
        channel_id = self.bot.server_map.discord_guilds_mural_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do mural das guildas nao encontrado.")
        embed = await self.build_mural_embed(guild)
        state = await self.bot.db.get_discord_guild_mural_message(guild.id)
        view = self.bot.view_factory.build_discord_guild_mural_view()
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=view)
                    await self.bot.db.save_discord_guild_mural_message(guild.id, saved_channel.id, message.id)
                    return message
                except discord.NotFound:
                    pass
        message = await channel.send(embed=embed, view=view)
        await self.bot.db.save_discord_guild_mural_message(guild.id, channel.id, message.id)
        return message

    async def refresh_mural(self, guild: discord.Guild) -> None:
        state = await self.bot.db.get_discord_guild_mural_message(guild.id)
        if not state:
            await self.publish_mural(guild)
            return
        channel = guild.get_channel(int(state["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(state["message_id"]))
        except discord.NotFound:
            await self.publish_mural(guild)
            return
        await message.edit(embed=await self.build_mural_embed(guild), view=self.bot.view_factory.build_discord_guild_mural_view())

    async def build_mural_embed(self, guild: discord.Guild) -> discord.Embed:
        profiles = await self.bot.db.list_discord_guild_profiles(guild.id)
        if not profiles:
            return self.bot.embeds.make(
                title="Mural das Guildas",
                description="Nenhuma guilda oficializada ainda.",
            )
        lines: list[str] = []
        options: list[dict[str, str]] = []
        for profile in profiles[:25]:
            count = await self.bot.db.count_discord_guild_members(int(profile["id"]))
            status = "Recrutando" if int(profile.get("recruitment_open") or 0) else "Fechado"
            lines.append(f"{profile['emoji']}「{profile['name']}」 — {count} membros — {status}")
            options.append({"label": str(profile["name"]), "value": str(profile["id"]), "description": f"{count} membros | {status}"})
        self.bot.discord_guild_mural_options = options
        return self.bot.embeds.make(
            title="Mural das Guildas",
            description="\n".join(lines),
            footer_text="Selecione uma guilda no menu abaixo para ver o perfil ou pedir convite.",
        )

    async def request_invite_from_recruitment(self, interaction: discord.Interaction, guild_profile_id: int) -> str:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise RuntimeError("Use esta acao dentro do servidor oficial.")
        await self._ensure_member_without_guild(interaction.user)
        profile = await self.bot.db.get_discord_guild_profile(guild_profile_id)
        if not profile or str(profile.get("status")) != "approved":
            raise RuntimeError("Guilda nao encontrada.")
        if not int(profile.get("recruitment_open") or 0):
            raise RuntimeError("Esta guilda esta com recrutamento fechado.")
        leader = interaction.guild.get_member(int(profile["leader_user_id"]))
        if leader:
            try:
                await leader.send(
                    embed=self.bot.embeds.make(
                        title="Novo Pedido de Convite",
                        description=f"{interaction.user.mention} demonstrou interesse em entrar em {profile['emoji']}「{profile['name']}」.\nUse `/guilda convidar` para enviar o convite oficial.",
                    )
                )
            except discord.HTTPException:
                pass
        return "Seu interesse foi enviado para a lideranca da guilda."

    async def _publish_creation_review(self, guild: discord.Guild, application_id: int) -> None:
        application = await self.bot.db.get_discord_guild_application(application_id)
        if not application:
            return
        channel_id = self.bot.server_map.discord_guilds_staff_review_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        requester = guild.get_member(int(application["requester_user_id"]))
        embed = self.bot.embeds.make(
            title="Nova Guilda para Revisao",
            description=f"{application['emoji']}「{application['name']}」 foi enviada para aprovacao.",
            fields=[
                ("Solicitante", requester.mention if requester else f"<@{application['requester_user_id']}>", True),
                ("Descricao", str(application["description"]), False),
                ("Slug", f"`{application['slug']}`", True),
            ],
            color=self.bot.embeds.warning_color,
        )
        message = await channel.send(embed=embed, view=self.bot.view_factory.build_discord_guild_application_review_view(application_id))
        await self.bot.db.update_discord_guild_application(application_id, {"review_message_id": message.id})

    async def _publish_emblem_review(
        self,
        guild: discord.Guild,
        profile: dict[str, Any],
        review_id: int,
        image_url: str,
        actor: discord.Member,
    ) -> None:
        channel_id = self.bot.server_map.discord_guilds_staff_review_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.bot.embeds.make(
            title="Emblema para Revisao",
            description=f"{profile['emoji']}「{profile['name']}」 enviou um novo emblema.",
            fields=[
                ("Lider", actor.mention, True),
                ("Guilda", f"{profile['emoji']}「{profile['name']}」", True),
            ],
            image_url=image_url,
            color=self.bot.embeds.warning_color,
        )
        message = await channel.send(embed=embed, view=self.bot.view_factory.build_discord_guild_emblem_review_view(review_id))
        await self.bot.db.update_discord_guild_emblem_review(review_id, {"review_message_id": message.id})

    async def _approve_profile_creation(
        self,
        guild: discord.Guild,
        leader: discord.Member,
        *,
        name: str,
        slug: str,
        emoji: str,
        description: str,
        approved_by_id: int | None,
    ) -> int:
        role = await guild.create_role(name=self._role_name(emoji, name), reason=f"Nova guilda social oficial: {name}")
        profile_id = await self.bot.db.create_discord_guild_profile(
            guild.id,
            name,
            slug,
            emoji,
            description,
            leader.id,
            role_id=role.id,
            status="approved",
            approved_by_id=approved_by_id,
            approved_at=datetime.now(UTC).isoformat(),
        )
        await self._add_member_to_guild(guild, {"id": profile_id, "name": name, "emoji": emoji, "role_id": role.id}, leader, hierarchy="leader")
        return profile_id

    async def _add_member_to_guild(
        self,
        guild: discord.Guild,
        profile: dict[str, Any],
        member: discord.Member,
        *,
        hierarchy: str,
        invited_by_id: int | None = None,
    ) -> None:
        original_nickname = member.nick
        await self.bot.db.upsert_discord_guild_member(
            int(profile["id"]),
            member.id,
            hierarchy,
            invited_by_id=invited_by_id,
            original_nickname=original_nickname,
        )
        role_id = profile.get("role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        if role and role not in member.roles:
            await member.add_roles(role, reason=f"Entrada na guilda social {profile['name']}")
        await self._apply_guild_nickname(member, profile)

    async def _remove_member_from_guild(self, guild: discord.Guild, membership: dict[str, Any], member: discord.Member) -> None:
        profile = await self.bot.db.get_discord_guild_profile(int(membership["guild_profile_id"]))
        if profile:
            role = guild.get_role(int(profile["role_id"])) if profile.get("role_id") else None
            if role and role in member.roles:
                await member.remove_roles(role, reason=f"Saida da guilda social {profile['name']}")
        await self._restore_member_nickname(member, membership.get("original_nickname"))
        await self.bot.db.remove_discord_guild_member(int(membership["guild_profile_id"]), member.id)

    async def _apply_guild_nickname(self, member: discord.Member, profile: dict[str, Any]) -> None:
        if self.bot.permission_service.has_any_role_id(member, self.bot.server_map.discord_guilds_staff_exempt_role_ids()):
            return
        if not member.guild.me or not member.guild.me.guild_permissions.manage_nicknames:
            return
        style = self.bot.server_map.discord_guilds_nickname_style()
        base = member.display_name
        if style == "tag":
            nickname = f"[{str(profile['slug']).upper()[:4]}] {base}"
        else:
            nickname = f"{profile['name']} • {base}"
        try:
            await member.edit(nick=nickname[:32], reason=f"Entrada na guilda social {profile['name']}")
        except discord.HTTPException:
            pass

    async def _restore_member_nickname(self, member: discord.Member, original_nickname: str | None) -> None:
        if self.bot.permission_service.has_any_role_id(member, self.bot.server_map.discord_guilds_staff_exempt_role_ids()):
            return
        if not member.guild.me or not member.guild.me.guild_permissions.manage_nicknames:
            return
        try:
            await member.edit(nick=original_nickname or None, reason="Saida da guilda social")
        except discord.HTTPException:
            pass

    async def _require_actor_guild_with_rank(self, guild_id: int, user_id: int, *, minimum: str) -> dict[str, Any]:
        membership = await self.bot.db.get_discord_guild_membership(user_id, guild_id)
        if not membership:
            raise RuntimeError("Voce nao participa de nenhuma guilda.")
        if self._hierarchy_power(str(membership["hierarchy"])) < self._hierarchy_power(minimum):
            raise RuntimeError("Sua hierarquia atual nao permite esta acao.")
        return membership

    async def _ensure_member_without_guild(self, member: discord.Member) -> None:
        existing = await self.bot.db.get_discord_guild_membership(member.id, member.guild.id)
        if existing:
            raise RuntimeError("Cada usuario pode participar de apenas uma guilda.")

    async def _ensure_name_available(self, guild_id: int, name: str, slug: str) -> None:
        if await self.bot.db.get_discord_guild_profile_by_name(guild_id, name):
            raise RuntimeError("Ja existe uma guilda com esse nome.")
        if await self.bot.db.get_discord_guild_profile_by_slug(guild_id, slug):
            raise RuntimeError("Ja existe uma guilda com essa tag.")

    def _ensure_enabled(self) -> None:
        if not self.enabled():
            raise RuntimeError("Sistema de guildas sociais desabilitado na configuracao.")

    def _validate_emoji(self, guild: discord.Guild | None, emoji: str) -> str:
        text = emoji.strip()
        if text in self.bot.server_map.discord_guilds_allowed_emojis():
            return text
        if guild:
            for custom in guild.emojis:
                rendered = str(custom)
                if text == rendered or text == custom.name:
                    return rendered
        raise RuntimeError("Emoji nao permitido para criacao de guilda.")

    def _normalize_name(self, name: str) -> str:
        clean = re.sub(r"\s+", " ", name.strip())
        if len(clean) < self.bot.server_map.discord_guilds_min_name_length():
            raise RuntimeError("Nome de guilda muito curto.")
        if len(clean) > self.bot.server_map.discord_guilds_max_name_length():
            raise RuntimeError("Nome de guilda muito longo.")
        if not re.fullmatch(r"[A-Za-zÀ-ÿ0-9 ]+", clean):
            raise RuntimeError("Use apenas letras, numeros e espacos no nome da guilda.")
        return clean

    @staticmethod
    def _normalize_description(description: str) -> str:
        clean = description.strip()
        if len(clean) < 10:
            raise RuntimeError("A descricao precisa ter pelo menos 10 caracteres.")
        return clean[:400]

    @staticmethod
    def _slugify(name: str) -> str:
        alnum = re.sub(r"[^A-Za-z0-9]+", "", name).upper()
        return alnum[:4] or "GUILD"

    @staticmethod
    def _role_name(emoji: str, name: str) -> str:
        return f"{emoji}「{name}」"

    @staticmethod
    def _hierarchy_label(hierarchy: str) -> str:
        return {
            "leader": "Lider",
            "subleader": "Sub-Lider",
            "officer": "Oficial",
            "member": "Membro",
        }.get(hierarchy, hierarchy)

    @staticmethod
    def _hierarchy_power(hierarchy: str) -> int:
        return HIERARCHY_ORDER.get(hierarchy, 0)

    @staticmethod
    def _load_json_list(raw: Any) -> list[str]:
        if not raw:
            return []
        try:
            data = json.loads(str(raw))
        except json.JSONDecodeError:
            return []
        return [str(item) for item in data if str(item).strip()]

    @staticmethod
    def _load_metadata(raw: Any) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            data = json.loads(str(raw))
        except json.JSONDecodeError:
            return {}
        return dict(data) if isinstance(data, dict) else {}

    @staticmethod
    def _parse_dt(raw: Any) -> datetime | None:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw))
        except ValueError:
            return None
