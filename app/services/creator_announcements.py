from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

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
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.log = logging.getLogger("drakoria.creator_announcements")
        self.session: aiohttp.ClientSession | None = None
        self._twitch_token: str | None = None
        self._twitch_token_expires_at = 0.0
        self._youtube_channels: dict[str, tuple[str, str]] = {}
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
        if twitch_creators and not self._has_env("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"):
            self._warn_missing_credentials("Twitch", "TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET")
        for item in twitch_creators if self._has_env("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET") else []:
            try:
                content = await self._poll_twitch(item, keyword)
                if content:
                    found.append(content)
            except Exception:
                self.log.exception("Falha ao consultar Twitch para %s", item.get("login"))
        youtube_creators = self._creators("youtube")
        if youtube_creators and not self._has_env("YOUTUBE_API_KEY"):
            self._warn_missing_credentials("YouTube", "YOUTUBE_API_KEY")
        for item in youtube_creators if self._has_env("YOUTUBE_API_KEY") else []:
            try:
                found.extend(await self._poll_youtube(item, keyword))
            except Exception:
                self.log.exception("Falha ao consultar YouTube para %s", item.get("handle"))
        return found

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

    async def _poll_youtube(self, creator: dict[str, Any], keyword: str) -> list[CreatorContent]:
        api_key = self._required_env("YOUTUBE_API_KEY")
        handle = str(creator.get("handle") or "").strip()
        if not handle:
            return []
        channel_data = self._youtube_channels.get(handle)
        if not channel_data:
            data = await self._request_json(
                "GET",
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "contentDetails", "forHandle": handle.lstrip("@"), "key": api_key},
            )
            items = data.get("items") or []
            if not items:
                self.log.warning("Canal do YouTube não encontrado: %s", handle)
                return []
            channel_id = str(items[0].get("id") or "")
            uploads_playlist_id = str(
                ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or ""
            )
            if not channel_id or not uploads_playlist_id:
                return []
            channel_data = (channel_id, uploads_playlist_id)
            self._youtube_channels[handle] = channel_data
        channel_id, uploads_playlist_id = channel_data

        data = await self._request_json(
            "GET",
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "part": "contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": "5",
                "key": api_key,
            },
        )
        video_ids = [
            str((item.get("contentDetails") or {}).get("videoId") or "")
            for item in data.get("items") or []
        ]
        video_ids = [video_id for video_id in video_ids if video_id]
        if not video_ids:
            return []
        videos = await self._request_json(
            "GET",
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet", "id": ",".join(video_ids), "key": api_key},
        )
        results: list[CreatorContent] = []
        for item in videos.get("items") or []:
            video_id = str(item.get("id") or "")
            snippet = item.get("snippet") or {}
            title = str(snippet.get("title") or "")
            description = str(snippet.get("description") or "")
            if not video_id or keyword not in f"{title}\n{description}".casefold():
                continue
            thumbs = snippet.get("thumbnails") or {}
            thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
            results.append(
                CreatorContent(
                    platform="youtube",
                    content_id=video_id,
                    creator_id=channel_id,
                    creator_name=str(creator.get("display_name") or snippet.get("channelTitle") or handle),
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    thumbnail_url=str(thumb) if thumb else None,
                    description=description,
                )
            )
        return results

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
