from __future__ import annotations

import logging

from discord.ext import commands, tasks


class CreatorAnnouncementsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log = logging.getLogger("drakoria.creator_announcements.cog")
        self.poll_loop.start()

    def cog_unload(self) -> None:
        self.poll_loop.cancel()

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
