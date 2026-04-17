from __future__ import annotations

from typing import Any

import discord


class OnboardingService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def is_open(self, guild_id: int) -> bool:
        settings = await self.bot.db.get_guild_settings(guild_id)
        if not settings:
            return self.bot.server_map.onboarding_open()
        return bool(settings.get("onboarding_open", 1))

    async def submit_application(self, interaction: discord.Interaction, answers: dict[str, str]) -> int:
        existing_application = await self.bot.db.get_application(interaction.guild_id, interaction.user.id)
        if existing_application and existing_application["status"] == "pending":
            raise RuntimeError(
                "Teu pergaminho anterior ainda aguarda julgamento da corte. Aguarda o veredito antes de reenviar."
            )

        whitelist_status = await self.bot.db.get_whitelist_status(interaction.guild_id, interaction.user.id)
        if whitelist_status and whitelist_status["status"] == "approved":
            raise RuntimeError("Tua entrada ja foi aprovada. Nao ha necessidade de enviar novo pergaminho.")

        application_id = await self.bot.db.upsert_application(interaction.guild_id, interaction.user.id, answers)
        review_channel_id = self.bot.server_map.channel("onboarding_review")
        review_channel = self.bot.get_channel(review_channel_id) if review_channel_id else None
        if not isinstance(review_channel, discord.TextChannel):
            raise RuntimeError(
                "O canal de revisao do onboarding nao foi localizado. Corrige a configuracao antes de abrir novos ingressos."
            )

        embed = self.bot.embeds.make(
            title="Pergaminho de Ingresso Recebido",
            description=(
                f"O aventureiro {interaction.user.mention} apresentou seu pedido de entrada.\n"
                f"Identificador do pergaminho: **indisponível**"
            ),
        )
        for question, answer in answers.items():
            embed.add_field(name=question, value=answer, inline=False)
        embed.add_field(name="Estado", value="Pendente de julgamento", inline=False)
        await review_channel.send(
            embed=embed,
            view=self.bot.view_factory.build_review_view(target_user_id=interaction.user.id),
        )

        await self.bot.central_logger.dispatch(
            "onboarding",
            title="Novo Pedido de Onboarding",
            description=f"{interaction.user.mention} enviou um pergaminho de ingresso.",
            color=self.bot.embeds.default_color,
            fields=[("Usuario", f"{interaction.user}", False)],
        )
        return application_id

    async def approve(self, interaction: discord.Interaction, member: discord.Member, reason: str | None) -> None:
        application = await self.bot.db.get_application(interaction.guild_id, member.id)
        if application and application["status"] != "pending":
            raise RuntimeError("Este pergaminho ja recebeu veredito anteriormente e nao pode ser julgado outra vez.")
        await self.bot.db.review_application(interaction.guild_id, member.id, "approved", interaction.user.id, reason)
        approved_role_id = self.bot.server_map.role("approved")
        pending_role_id = self.bot.server_map.role("visitor")
        if approved_role_id:
            role = member.guild.get_role(approved_role_id)
            if role:
                await member.add_roles(role, reason="Whitelist aprovada em Drakoria")
            else:
                raise RuntimeError("O cargo configurado para aprovados nao foi encontrado no servidor.")
        if pending_role_id:
            pending = member.guild.get_role(pending_role_id)
            if pending and pending in member.roles:
                await member.remove_roles(pending, reason="Whitelist aprovada em Drakoria")

        await self.bot.central_logger.dispatch(
            "moderation",
            title="Whitelist Aprovada",
            description=f"{member.mention} foi aceito no reino.",
            color=self.bot.embeds.success_color,
            fields=[("Avaliador", interaction.user.mention, True), ("Motivo", reason or "Nao informado", False)],
        )

    async def reject(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        application = await self.bot.db.get_application(interaction.guild_id, member.id)
        if application and application["status"] != "pending":
            raise RuntimeError("Este pergaminho ja recebeu veredito anteriormente e nao pode ser julgado outra vez.")
        await self.bot.db.review_application(interaction.guild_id, member.id, "rejected", interaction.user.id, reason)
        await self.bot.central_logger.dispatch(
            "moderation",
            title="Whitelist Reprovada",
            description=f"{member.mention} teve o pedido recusado.",
            color=self.bot.embeds.error_color,
            fields=[("Avaliador", interaction.user.mention, True), ("Motivo", reason, False)],
        )



