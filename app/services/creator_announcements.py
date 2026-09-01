from __future__ import annotations

import logging
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

import aiohttp


@dataclass(frozen=True)
class CreatorContent:
    platform: str
    content_id: str
    creator_id: str
    creator_name: str
    title: str
    url: str
    thumbnail_url: str | None = None
    description: str = ""
    is_ambassador: bool = False


class CreatorAnnouncementService:
    """Monitora conteúdos dos criadores e publica anúncios sem duplicação."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.log = logging.getLogger("drakoria.creator_announcements")
        self.session: aiohttp.ClientSession | None = None
        self._twitch_token: str | None = None
        self._twitch_token_expires_at = 0.0
        self._youtube_channels: dict[str, str] = {}
        self._missing_credentials_warned: set[str] = set()

    @property
    def config(self) -> dict[str, Any]:
        value = self.bot.config.get("creator_announcements", {})
        return value if isinstance(value, dict) else {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    async def poll(self) -> list[CreatorContent]:
        if not self.enabled:
            return []
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self.session = aiohttp.ClientSession(timeout=timeout)

        found: list[CreatorContent] = []
        keyword = str(self.config.get("keyword") or "Drakoria").casefold()
        twitch_creators = self._creators("twitch")
        twitch_with_api = self._has_env("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET")
        if twitch_creators and not twitch_with_api:
            self.log.debug("Twitch em modo de leitura pública temporária.")
        for item in twitch_creators:
            try:
                content = await (self._poll_twitch(item, keyword) if twitch_with_api else self._poll_twitch_public(item, keyword))
                if content:
                    found.append(content)
            except Exception:
                self.log.exception("Falha ao consultar Twitch para %s", item.get("login"))
        youtube_creators = self._creators("youtube")
        for item in youtube_creators:
            try:
                found.extend(await self._poll_youtube_rss(item, keyword))
            except Exception:
                self.log.exception("Falha ao consultar YouTube para %s", item.get("handle"))
        return found

    async def _poll_twitch_public(self, creator: dict[str, Any], keyword: str) -> CreatorContent | None:
        """Best-effort Twitch fallback until official API credentials are available."""
        login = str(creator.get("login") or "").strip().lower()
        if not login:
            return None
        page = await self._request_text(f"https://www.twitch.tv/{login}", headers={"User-Agent": "DrakoriaBot/1.0"})
        decoded = html.unescape(page)
        live = re.search(r'"(?:isLiveBroadcast|isLive)"\s*:\s*true', decoded, re.IGNORECASE)
        if not live:
            return None

        def first(patterns: tuple[str, ...]) -> str:
            for pattern in patterns:
                match = re.search(pattern, decoded, re.IGNORECASE)
                if match:
                    return html.unescape(match.group(1)).strip()
            return ""

        title = first((
            r'"stream_title"\s*:\s*"((?:\\.|[^"\\])*)"',
            r'"title"\s*:\s*"((?:\\.|[^"\\])*)"',
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        ))
        if "\\" in title:
            try:
                title = json.loads(f'"{title}"')
            except json.JSONDecodeError:
                pass
        if keyword not in title.casefold():
            return None
        stream_id = first((r'"stream_id"\s*:\s*"?(\d+)', r'"broadcast_id"\s*:\s*"?(\d+)'))
        started_at = first((r'"started_at"\s*:\s*"([^"]+)', r'"created_at"\s*:\s*"([^"]+)'))
        identity = f"{login}:{stream_id or started_at or title}"
        content_id = stream_id or hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        thumbnail = first((r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',))
        return CreatorContent(
            platform="twitch",
            content_id=content_id,
            creator_id=login,
            creator_name=str(creator.get("display_name") or login),
            title=title or "Live na Twitch",
            url=f"https://twitch.tv/{login}",
            thumbnail_url=thumbnail or None,
            description="Live na Twitch",
            is_ambassador=bool(creator.get("ambassador", False)),
        )

    async def _poll_twitch(self, creator: dict[str, Any], keyword: str) -> CreatorContent | None:
        login = str(creator.get("login") or "").strip().lower()
        if not login:
            return None
        client_id = self._required_env("TWITCH_CLIENT_ID")
        client_secret = self._required_env("TWITCH_CLIENT_SECRET")
        token = await self._get_twitch_token(client_id, client_secret)
        data = await self._request_json(
            "GET",
            "https://api.twitch.tv/helix/streams",
            headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
            params={"user_login": login},
        )
        streams = data.get("data") or []
        if not streams:
            return None
        stream = streams[0]
        title = str(stream.get("title") or "")
        if keyword not in title.casefold():
            return None
        stream_id = str(stream.get("id") or "").strip()
        if not stream_id:
            return None
        thumbnail = str(stream.get("thumbnail_url") or "").replace("{width}", "1280").replace("{height}", "720")
        return CreatorContent(
            platform="twitch",
            content_id=stream_id,
            creator_id=login,
            creator_name=str(creator.get("display_name") or stream.get("user_name") or login),
            title=title,
            url=f"https://twitch.tv/{login}",
            thumbnail_url=thumbnail or None,
            description=str(stream.get("game_name") or "Live na Twitch"),
            is_ambassador=bool(creator.get("ambassador", False)),
        )

    async def _poll_youtube_rss(self, creator: dict[str, Any], keyword: str) -> list[CreatorContent]:
        handle = str(creator.get("handle") or "").strip()
        channel_id = str(creator.get("channel_id") or "").strip() or await self._resolve_youtube_channel_id(handle)
        if not channel_id:
            self.log.warning("Canal do YouTube não encontrado publicamente: %s", handle)
            return []
        feed = await self._request_text(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
            headers={"User-Agent": "DrakoriaBot/1.0"},
        )
        root = ElementTree.fromstring(feed)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
        results: list[CreatorContent] = []
        for entry in root.findall("atom:entry", ns):
            video_id = (entry.findtext("yt:videoId", default="", namespaces=ns) or "").strip()
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            description = (entry.findtext("media:group/media:description", default="", namespaces=ns) or "").strip()
            if not video_id or keyword not in f"{title}\n{description}".casefold():
                continue
            thumbnail = None
            media_thumbnail = entry.find("media:group/media:thumbnail", ns)
            if media_thumbnail is not None:
                thumbnail = media_thumbnail.attrib.get("url")
            results.append(CreatorContent(
                platform="youtube",
                content_id=video_id,
                creator_id=channel_id,
                creator_name=str(creator.get("display_name") or root.findtext("atom:author/atom:name", default=handle, namespaces=ns)),
                title=title,
                url=f"https://www.youtube.com/watch?v={video_id}",
                thumbnail_url=thumbnail,
                description=description,
            ))
        return results

    async def _resolve_youtube_channel_id(self, handle: str) -> str:
        if not handle:
            return ""
        if handle in self._youtube_channels:
            return self._youtube_channels[handle]
        page = await self._request_text(f"https://www.youtube.com/{handle.lstrip('@')}", headers={"User-Agent": "DrakoriaBot/1.0"})
        patterns = (
            r'"channelId"\s*:\s*"(UC[\w-]+)"',
            r'<meta[^>]+itemprop=["\']channelId["\'][^>]+content=["\'](UC[\w-]+)',
        )
        channel_id = next((match.group(1) for pattern in patterns if (match := re.search(pattern, page, re.IGNORECASE))), "")
        if channel_id:
            self._youtube_channels[handle] = channel_id
        return channel_id

    async def announce(self, content: CreatorContent) -> bool:
        if await self.bot.db.creator_announcement_exists(content.platform, content.content_id):
            return False
        channel_id = int(self.config.get("channel_id") or 0)
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                self.log.exception("Canal de divulgação não encontrado: %s", channel_id)
                return False
        embed = self._build_embed(content)
        mention = "@everyone " if bool(self.config.get("mention_everyone", True)) else ""
        message = await channel.send(content=mention, embed=embed)
        await self.bot.db.save_creator_announcement(
            content.platform, content.content_id, content.creator_id, message.id
        )
        self.log.info("Conteúdo divulgado: %s/%s", content.platform, content.content_id)
        return True

    def manual_content(self, *, platform: str, creator: str, title: str, url: str, description: str = "") -> CreatorContent:
        platform = platform.strip().lower()
        creator = creator.strip()
        normalized_url = url.strip()
        if platform not in {"twitch", "youtube"}:
            raise ValueError("A plataforma deve ser Twitch ou YouTube.")
        if not creator or not title.strip() or not normalized_url:
            raise ValueError("Informe criador, título e link.")
        if not normalized_url.startswith(("https://", "http://")):
            raise ValueError("O link deve começar com http:// ou https://.")
        creator_key = creator.casefold().lstrip("@").rstrip("/")
        ambassador = any(
            str(item.get("login") or item.get("handle") or "").casefold().lstrip("@").rstrip("/") == creator_key
            and bool(item.get("ambassador", False))
            for item in self._creators(platform)
        )
        content_id = hashlib.sha256(f"manual:{platform}:{normalized_url}".encode("utf-8")).hexdigest()[:24]
        return CreatorContent(
            platform=platform,
            content_id=f"manual-{content_id}",
            creator_id=creator,
            creator_name=creator,
            title=title.strip()[:200],
            url=normalized_url,
            description=description.strip()[:1000],
            is_ambassador=ambassador,
        )

    def _build_embed(self, content: CreatorContent):
        if content.platform == "twitch":
            title = f"🔴 Live de {content.creator_name}"
            description = f"**{content.title}**\n\n[Assistir agora]({content.url})"
            if content.description:
                description += f"\n🎮 {content.description}"
        else:
            title = f"🎬 Novo vídeo de {content.creator_name}"
            description = f"**{content.title}**\n\n[Assistir vídeo]({content.url})"
        if content.is_ambassador:
            title = f"👑 {title} • Embaixador Drakoria"
        return self.bot.embeds.make(
            title=title,
            description=description,
            color=0xF1C40F if content.is_ambassador else 0x5865F2,
            thumbnail_url=content.thumbnail_url,
            fields=[("Criador", content.creator_name, True), ("Plataforma", content.platform.title(), True)],
            timestamp=True,
        )

    async def _get_twitch_token(self, client_id: str, client_secret: str) -> str:
        if self._twitch_token and time.monotonic() < self._twitch_token_expires_at - 60:
            return self._twitch_token
        data = await self._request_json(
            "POST",
            "https://id.twitch.tv/oauth2/token",
            params={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        )
        self._twitch_token = str(data.get("access_token") or "")
        if not self._twitch_token:
            raise RuntimeError("Twitch não retornou access_token")
        self._twitch_token_expires_at = time.monotonic() + float(data.get("expires_in") or 0)
        return self._twitch_token

    async def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        assert self.session is not None
        async with self.session.request(method, url, **kwargs) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"API {response.status}: {payload}")
            if not isinstance(payload, dict):
                raise RuntimeError("Resposta de API inválida")
            return payload

    async def _request_text(self, url: str, **kwargs: Any) -> str:
        assert self.session is not None
        async with self.session.get(url, **kwargs) as response:
            payload = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Página {response.status}: {url}")
            return payload

    @staticmethod
    def _required_env(name: str) -> str:
        import os

        value = os.getenv(name, "").strip()
        if not value:
            raise RuntimeError(f"Variável {name} não configurada")
        return value

    def _has_env(self, *names: str) -> bool:
        import os

        return all(os.getenv(name, "").strip() for name in names)

    def _warn_missing_credentials(self, platform: str, names: str) -> None:
        if platform in self._missing_credentials_warned:
            return
        self._missing_credentials_warned.add(platform)
        self.log.warning("Divulgação de %s aguardando credencial: %s", platform, names)

    def _creators(self, platform: str) -> list[dict[str, Any]]:
        creators = self.config.get(platform, [])
        return [item for item in creators if isinstance(item, dict)] if isinstance(creators, list) else []
