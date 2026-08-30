from __future__ import annotations

from typing import Any

import discord


class DiscordGuildApplicationReviewView(discord.ui.View):
    def __init__(self, bot: Any, application_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.application_id = application_id
        approve = discord.ui.Button(
            label="Aprovar",
            style=discord.ButtonStyle.success,
            custom_id=f"drakoria:guild:application:approve:{application_id}",
        )
        approve.callback = self.approve_button
        reject = discord.ui.Button(
            label="Recusar",
            style=discord.ButtonStyle.danger,
            custom_id=f"drakoria:guild:application:reject:{application_id}",
        )
        reject.callback = self.reject_button
        self.add_item(approve)
        self.add_item(reject)

    async def approve_button(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(interaction.user, "manage_discord_guilds"):
            await interaction.response.send_message(embed=self.bot.permission_service.denial_embed("manage_discord_guilds"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.discord_guild_service.approve_creation_application(interaction, self.application_id)
            await interaction.followup.send(embed=self.bot.embeds.success("Guilda Aprovada", result), ephemeral=True)
            await interaction.message.edit(view=None)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha na aprovacao", str(exc)[:300]), ephemeral=True)

    async def reject_button(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(interaction.user, "manage_discord_guilds"):
            await interaction.response.send_message(embed=self.bot.permission_service.denial_embed("manage_discord_guilds"), ephemeral=True)
            return
        await interaction.response.send_modal(DiscordGuildRejectModal(self.bot, self.application_id, target="application"))


class DiscordGuildEmblemReviewView(discord.ui.View):
    def __init__(self, bot: Any, review_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.review_id = review_id
        approve = discord.ui.Button(
            label="Aprovar Emblema",
            style=discord.ButtonStyle.success,
            custom_id=f"drakoria:guild:emblem:approve:{review_id}",
        )
        approve.callback = self.approve_button
        reject = discord.ui.Button(
            label="Recusar Emblema",
            style=discord.ButtonStyle.danger,
            custom_id=f"drakoria:guild:emblem:reject:{review_id}",
        )
        reject.callback = self.reject_button
        self.add_item(approve)
        self.add_item(reject)

    async def approve_button(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(interaction.user, "manage_discord_guilds"):
            await interaction.response.send_message(embed=self.bot.permission_service.denial_embed("manage_discord_guilds"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.discord_guild_service.approve_emblem_review(interaction, self.review_id)
            await interaction.followup.send(embed=self.bot.embeds.success("Emblema Aprovado", result), ephemeral=True)
            await interaction.message.edit(view=None)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha no emblema", str(exc)[:300]), ephemeral=True)

    async def reject_button(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.bot.permission_service.has(interaction.user, "manage_discord_guilds"):
            await interaction.response.send_message(embed=self.bot.permission_service.denial_embed("manage_discord_guilds"), ephemeral=True)
            return
        await interaction.response.send_modal(DiscordGuildRejectModal(self.bot, self.review_id, target="emblem"))


class DiscordGuildInviteView(discord.ui.View):
    def __init__(self, bot: Any, invite_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.invite_id = invite_id
        accept = discord.ui.Button(
            label="Aceitar",
            style=discord.ButtonStyle.success,
            custom_id=f"drakoria:guild:invite:accept:{invite_id}",
        )
        accept.callback = self.accept_button
        decline = discord.ui.Button(
            label="Recusar",
            style=discord.ButtonStyle.secondary,
            custom_id=f"drakoria:guild:invite:decline:{invite_id}",
        )
        decline.callback = self.decline_button
        self.add_item(accept)
        self.add_item(decline)

    async def accept_button(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.discord_guild_service.accept_invite(interaction, self.invite_id)
            await interaction.followup.send(embed=self.bot.embeds.success("Convite Aceito", result), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha no convite", str(exc)[:300]), ephemeral=True)

    async def decline_button(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.discord_guild_service.decline_invite(interaction, self.invite_id)
            await interaction.followup.send(embed=self.bot.embeds.warning("Convite Recusado", result), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha no convite", str(exc)[:300]), ephemeral=True)


class DiscordGuildRecruitmentView(discord.ui.View):
    def __init__(self, bot: Any, guild_profile_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_profile_id = guild_profile_id
        request = discord.ui.Button(
            label="Pedir Convite",
            style=discord.ButtonStyle.success,
            custom_id=f"drakoria:guild:recruit:apply:{guild_profile_id}",
        )
        request.callback = self.request_button
        profile = discord.ui.Button(
            label="Ver Perfil",
            style=discord.ButtonStyle.primary,
            custom_id=f"drakoria:guild:recruit:profile:{guild_profile_id}",
        )
        profile.callback = self.profile_button
        self.add_item(request)
        self.add_item(profile)

    async def request_button(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.discord_guild_service.request_invite_from_recruitment(interaction, self.guild_profile_id)
            await interaction.followup.send(embed=self.bot.embeds.success("Pedido Enviado", result), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha no pedido", str(exc)[:300]), ephemeral=True)

    async def profile_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        profile = await self.bot.db.get_discord_guild_profile(self.guild_profile_id)
        if not profile:
            await interaction.response.send_message("Guilda nao encontrada.", ephemeral=True)
            return
        embed = await self.bot.discord_guild_service.build_profile_embed(interaction.guild, profile)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class DiscordGuildMuralSelect(discord.ui.Select):
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        options_data = getattr(bot, "discord_guild_mural_options", [])[:25]
        options = [
            discord.SelectOption(
                label=str(item["label"])[:100],
                value=str(item["value"]),
                description=str(item.get("description") or "")[:100],
            )
            for item in options_data
        ] or [discord.SelectOption(label="Nenhuma guilda disponivel", value="0", description="Sem registros")]
        super().__init__(
            placeholder="Selecione uma guilda",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="drakoria:guild:mural:select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == "0":
            await interaction.response.send_message("Ainda nao ha guildas no mural.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        profile = await self.bot.db.get_discord_guild_profile(int(self.values[0]))
        if not profile:
            await interaction.response.send_message("Guilda nao encontrada.", ephemeral=True)
            return
        embed = await self.bot.discord_guild_service.build_profile_embed(interaction.guild, profile)
        view = DiscordGuildRecruitmentView(self.bot, int(self.values[0])) if int(profile.get("recruitment_open") or 0) else None
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DiscordGuildMuralView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(DiscordGuildMuralSelect(bot))


class DiscordGuildLeaderPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="Editar Descricao", style=discord.ButtonStyle.primary)
    async def description_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(DiscordGuildDescriptionModal(self.bot))

    @discord.ui.button(label="Abrir/Fechar Recrutamento", style=discord.ButtonStyle.success)
    async def recruitment_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        membership = await self.bot.discord_guild_service.get_profile_for_member(interaction.guild.id, interaction.user.id)
        if not membership:
            await interaction.response.send_message("Guilda nao encontrada.", ephemeral=True)
            return
        current = bool(int(membership.get("recruitment_open") or 0))
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.discord_guild_service.set_recruitment_state(interaction.guild, interaction.user, not current)
            await interaction.followup.send(embed=self.bot.embeds.success("Recrutamento", result), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha no recrutamento", str(exc)[:300]), ephemeral=True)

    @discord.ui.button(label="Enviar Emblema", style=discord.ButtonStyle.secondary)
    async def emblem_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(DiscordGuildEmblemModal(self.bot))

    @discord.ui.button(label="Ver Perfil", style=discord.ButtonStyle.secondary)
    async def profile_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        membership = await self.bot.discord_guild_service.get_profile_for_member(interaction.guild.id, interaction.user.id)
        if not membership:
            await interaction.response.send_message("Guilda nao encontrada.", ephemeral=True)
            return
        embed = await self.bot.discord_guild_service.build_profile_embed(interaction.guild, membership)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class DiscordGuildDescriptionModal(discord.ui.Modal, title="Editar Descricao da Guilda"):
    description = discord.ui.TextInput(label="Nova descricao", style=discord.TextStyle.paragraph, max_length=400)

    def __init__(self, bot: Any) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        try:
            result = await self.bot.discord_guild_service.set_description(interaction.guild, interaction.user, self.description.value)
            await interaction.response.send_message(embed=self.bot.embeds.success("Guilda Atualizada", result), ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(embed=self.bot.embeds.error("Falha ao editar", str(exc)[:300]), ephemeral=True)


class DiscordGuildEmblemModal(discord.ui.Modal, title="Enviar Emblema da Guilda"):
    image_url = discord.ui.TextInput(label="URL da imagem", max_length=500)

    def __init__(self, bot: Any) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        try:
            result = await self.bot.discord_guild_service.submit_emblem(interaction.guild, interaction.user, self.image_url.value)
            await interaction.response.send_message(embed=self.bot.embeds.success("Emblema Enviado", result), ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(embed=self.bot.embeds.error("Falha no emblema", str(exc)[:300]), ephemeral=True)


class DiscordGuildRejectModal(discord.ui.Modal, title="Recusar Revisao"):
    reason = discord.ui.TextInput(label="Motivo", style=discord.TextStyle.paragraph, max_length=300)

    def __init__(self, bot: Any, target_id: int, *, target: str) -> None:
        super().__init__()
        self.bot = bot
        self.target_id = target_id
        self.target = target

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if self.target == "application":
                result = await self.bot.discord_guild_service.reject_creation_application(interaction, self.target_id, self.reason.value)
            else:
                result = await self.bot.discord_guild_service.reject_emblem_review(interaction, self.target_id, self.reason.value)
            await interaction.followup.send(embed=self.bot.embeds.warning("Revisao Encerrada", result), ephemeral=True)
            if interaction.message:
                await interaction.message.edit(view=None)
        except Exception as exc:
            await interaction.followup.send(embed=self.bot.embeds.error("Falha na revisao", str(exc)[:300]), ephemeral=True)
