from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks


class CreatorAnnouncementsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log = logging.getLogger("drakoria.creator_announcements.cog")
        self.poll_loop.start()

    def cog_unload(self) -> None:
        self.poll_loop.cancel()

    @app_commands.command(name="divulgar", description="Publica manualmente uma live ou vídeo de criador")
    @app_commands.guild_only()
    @app_commands.describe(
        plataforma="Plataforma do conteúdo",
        criador="Nome do criador conforme a configuração",
        titulo="Título da live ou vídeo",
        link="Link direto para o conteúdo",
        descricao="Descrição opcional",
    )
    @app_commands.choices(
        plataforma=[
            app_commands.Choice(name="Twitch", value="twitch"),
            app_commands.Choice(name="YouTube", value="youtube"),
        ]
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def divulgar(
        self,
        interaction: discord.Interaction,
        plataforma: app_commands.Choice[str],
        criador: str,
        titulo: str,
        link: str,
        descricao: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            content = self.bot.creator_announcement_service.manual_content(
                platform=plataforma.value,
                creator=criador,
                title=titulo,
                url=link,
                description=descricao or "",
            )
            published = await self.bot.creator_announcement_service.announce(content)
        except (ValueError, RuntimeError, discord.HTTPException) as exc:
            await interaction.followup.send(f"Não foi possível divulgar: {exc}", ephemeral=True)
            return
        if published:
            await interaction.followup.send("Conteúdo divulgado com sucesso.", ephemeral=True)
        else:
            await interaction.followup.send("Esse link já foi divulgado anteriormente.", ephemeral=True)

    @tasks.loop(seconds=60)
    async def poll_loop(self) -> None:
        service = self.bot.creator_announcement_service
        for content in await service.poll():
            try:
                await service.announce(content)
            except Exception:
                self.log.exception("Falha ao publicar conteúdo de %s", content.url)

    @poll_loop.before_loop
    async def before_poll_loop(self) -> None:
        await self.bot.wait_until_ready()
        interval = int(self.bot.config.get("creator_announcements", {}).get("interval_seconds", 60))
        self.poll_loop.change_interval(seconds=max(30, min(interval, 3600)))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CreatorAnnouncementsCog(bot))
