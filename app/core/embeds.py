from __future__ import annotations

import discord


class EmbedFactory:
    def __init__(self, style: dict) -> None:
        self.style = style
        self.default_color = int(str(style.get("primary_color", "0xf1c40f")), 16)
        self.success_color = int(str(style.get("success_color", "0xf1c40f")), 16)
        self.error_color = int(str(style.get("error_color", "0xf1c40f")), 16)
        self.warning_color = int(str(style.get("warning_color", "0xf1c40f")), 16)
        self.footer_text = style.get("footer_text", "Reino de Drakoria")
        self.footer_icon: str | None = style.get("footer_icon_url") or None
        _raw_logo = (
            style.get("thumbnail_url")
            or style.get("logo_url")
            or style.get("brand_logo_url")
            or None
        )
        # Only use logo as thumbnail if it's a remote URL; local paths are resolved at startup
        self.default_thumbnail: str | None = (
            _raw_logo if isinstance(_raw_logo, str) and _raw_logo.startswith("http") else None
        )
        self.guild_icon_url: str | None = None

    def make(
        self,
        *,
        title: str,
        description: str,
        color: int | None = None,
        fields: list[tuple[str, str, bool]] | None = None,
        thumbnail_url: str | None = None,
        image_url: str | None = None,
        author_name: str | None = None,
        author_icon_url: str | None = None,
        footer_text: str | None = None,
        footer_icon_url: str | None = None,
        timestamp: bool = False,
    ) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color or self.default_color)
        for name, value, inline in fields or []:
            embed.add_field(name=name, value=value, inline=inline)
        resolved_thumbnail = thumbnail_url or self.default_thumbnail or self.footer_icon or self.guild_icon_url
        if resolved_thumbnail:
            embed.set_thumbnail(url=resolved_thumbnail)
        if image_url:
            embed.set_image(url=image_url)
        if author_name:
            if author_icon_url:
                embed.set_author(name=author_name, icon_url=author_icon_url)
            else:
                embed.set_author(name=author_name)
        resolved_footer = footer_text or self.footer_text
        resolved_footer_icon = (
            footer_icon_url
            if footer_icon_url is not None
            else (self.footer_icon or self.guild_icon_url)
        )
        if resolved_footer_icon:
            embed.set_footer(text=resolved_footer, icon_url=resolved_footer_icon)
        else:
            embed.set_footer(text=resolved_footer)
        if timestamp:
            embed.timestamp = discord.utils.utcnow()
        return embed

    def success(self, title: str, description: str) -> discord.Embed:
        return self.make(title=title, description=description, color=self.success_color)

    def error(self, title: str, description: str) -> discord.Embed:
        return self.make(title=title, description=description, color=self.error_color)

    def warning(self, title: str, description: str) -> discord.Embed:
        return self.make(title=title, description=description, color=self.warning_color)


