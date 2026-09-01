from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from app.repositories.database import Database
from app.services.creator_announcements import CreatorAnnouncementService, CreatorContent


class CreatorAnnouncementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "creator-announcements.sqlite3")
        await self.db.initialize()

    async def asyncTearDown(self) -> None:
        self.tempdir.cleanup()

    async def test_database_deduplicates_content_by_platform_and_id(self) -> None:
        self.assertFalse(await self.db.creator_announcement_exists("twitch", "stream-1"))
        await self.db.save_creator_announcement("twitch", "stream-1", "diogompw", 123)
        self.assertTrue(await self.db.creator_announcement_exists("twitch", "stream-1"))
        self.assertFalse(await self.db.creator_announcement_exists("youtube", "stream-1"))

    def test_embed_case_insensitive_content_and_ambassador_style(self) -> None:
        bot = SimpleNamespace(
            config={"creator_announcements": {}},
            embeds=SimpleNamespace(
                make=lambda **kwargs: discord.Embed(
                    title=kwargs["title"], description=kwargs["description"], color=kwargs["color"]
                )
            ),
        )
        service = CreatorAnnouncementService(bot)
        content = CreatorContent(
            platform="twitch",
            content_id="stream-1",
            creator_id="diogompw",
            creator_name="Diogo MPW",
            title="DraKoRiA ao vivo",
            url="https://twitch.tv/diogompw",
            is_ambassador=True,
        )
        embed = service._build_embed(content)
        self.assertIn("Embaixador Drakoria", embed.title or "")
        self.assertEqual(embed.color.value, 0xF1C40F)
        self.assertIn("twitch.tv/diogompw", embed.description or "")

    async def test_youtube_rss_filters_title_and_description_without_api_key(self) -> None:
        bot = SimpleNamespace(config={"creator_announcements": {"youtube_max_age_hours": 10000}}, db=self.db)
        service = CreatorAnnouncementService(bot)
        service._request_text = AsyncMock(return_value="""<?xml version='1.0'?>
        <feed xmlns='http://www.w3.org/2005/Atom' xmlns:yt='http://www.youtube.com/xml/schemas/2015' xmlns:media='http://search.yahoo.com/mrss/'>
          <author><name>Sir Lopes</name></author>
          <entry><yt:videoId>video-1</yt:videoId><published>2026-09-01T00:00:00+00:00</published><title>Gameplay DraKoRiA</title>
            <media:group><media:description>Vídeo oficial</media:description><media:thumbnail url='https://img/1.jpg'/></media:group>
          </entry>
          <entry><yt:videoId>video-2</yt:videoId><published>2026-08-01T00:00:00+00:00</published><title>Outro jogo</title><media:group><media:description>sem palavra</media:description></media:group></entry>
        </feed>""")
        service._resolve_youtube_channel_id = AsyncMock(return_value="UC123")

        results = await service._poll_youtube_rss({"handle": "@sirlopes_br", "display_name": "Sir Lopes"}, "drakoria")

        self.assertEqual([item.content_id for item in results], ["video-1"])
        self.assertEqual(results[0].thumbnail_url, "https://img/1.jpg")

    async def test_youtube_rss_does_not_announce_old_matching_video(self) -> None:
        bot = SimpleNamespace(config={"creator_announcements": {"youtube_max_age_hours": 48}})
        service = CreatorAnnouncementService(bot)
        service._request_text = AsyncMock(return_value="""<feed xmlns='http://www.w3.org/2005/Atom' xmlns:yt='http://www.youtube.com/xml/schemas/2015'>
          <entry><yt:videoId>old-video</yt:videoId><published>2026-06-01T00:00:00+00:00</published><title>Drakoria antigo</title></entry>
        </feed>""")
        service._resolve_youtube_channel_id = AsyncMock(return_value="UC123")

        results = await service._poll_youtube_rss({"handle": "@sirlopes_br"}, "drakoria")

        self.assertEqual(results, [])

    async def test_youtube_handle_resolution_keeps_at_prefix(self) -> None:
        bot = SimpleNamespace(config={"creator_announcements": {}})
        service = CreatorAnnouncementService(bot)
        service._request_text = AsyncMock(return_value='"externalId":"UC123"')

        result = await service._resolve_youtube_channel_id("@sirlopes_br")

        self.assertEqual(result, "UC123")
        self.assertIn("https://www.youtube.com/@sirlopes_br", service._request_text.await_args.args[0])

    async def test_twitch_public_reader_filters_live_title(self) -> None:
        bot = SimpleNamespace(config={"creator_announcements": {}})
        service = CreatorAnnouncementService(bot)
        service._request_text = AsyncMock(return_value='''<meta property="og:image" content="https://img/live.jpg">
        {"isLiveBroadcast":true,"stream_id":"123","stream_title":"Live DraKoRiA agora"}''')

        result = await service._poll_twitch_public({"login": "diogompw", "display_name": "Diogo MPW", "ambassador": True}, "drakoria")

        self.assertIsNotNone(result)
        self.assertEqual(result.content_id, "123")
        self.assertTrue(result.is_ambassador)

    def test_manual_content_is_deterministic_and_marks_ambassador(self) -> None:
        bot = SimpleNamespace(config={"creator_announcements": {"twitch": [{"login": "diogompw", "ambassador": True}]}})
        service = CreatorAnnouncementService(bot)

        content = service.manual_content(
            platform="twitch", creator="diogompw", title="Live Drakoria", url="https://twitch.tv/diogompw"
        )

        self.assertTrue(content.content_id.startswith("manual-"))
        self.assertTrue(content.is_ambassador)
