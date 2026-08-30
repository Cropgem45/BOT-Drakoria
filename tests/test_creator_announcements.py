from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
