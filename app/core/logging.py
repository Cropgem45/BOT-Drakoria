from __future__ import annotations

import logging
from typing import Any

import discord


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


class CentralLogger:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.log = logging.getLogger("drakoria.central_logger")

    async def dispatch(
        self,
        channel_key: str,
        *,
        title: str,
        description: str,
        color: int,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        channel_id = self.bot.server_map.log_channel(channel_key)
        if not channel_id:
            self.log.warning("Canal de log nao configurado para %s", channel_key)
            return

        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            self.log.warning("Canal de log invalido para %s", channel_key)
            return

        embed = self.bot.embeds.make(title=title, description=description, color=color)
        for name, value, inline in fields or []:
            embed.add_field(name=name, value=value, inline=inline)
        await channel.send(embed=embed)


