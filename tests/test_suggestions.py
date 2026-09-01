from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import discord

from app.repositories.database import Database
from app.services.suggestions import SuggestionService
from app.services.suggestion_repository import SuggestionRepository


class SuggestionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "suggestions.sqlite3")
        await self.db.initialize()
        self.repo = SuggestionRepository(self.db)
        await self.repo.ensure_schema()

    async def asyncTearDown(self) -> None:
        self.tempdir.cleanup()

    async def test_vote_is_unique_and_can_be_switched(self) -> None:
        suggestion_id = await self.repo.create(10, 20, 99, "Título", "Descrição")

        self.assertEqual({"yes": 1, "no": 0}, await self.repo.set_vote(suggestion_id, 30, "yes"))
        self.assertEqual({"yes": 1, "no": 0}, await self.repo.set_vote(suggestion_id, 30, "yes"))
        self.assertEqual({"yes": 0, "no": 1}, await self.repo.set_vote(suggestion_id, 30, "no"))
        self.assertEqual({"yes": 0, "no": 1}, await self.repo.set_vote(suggestion_id, 30, "no"))

    async def test_suggestion_numbers_are_sequential_per_guild(self) -> None:
        first = await self.repo.create(10, 20, 99, "Um", "A")
        second = await self.repo.create(10, 21, 99, "Dois", "B")
        other_guild = await self.repo.create(11, 22, 99, "Outro", "C")

        self.assertEqual(1, first)
        self.assertEqual(2, second)
        self.assertEqual(3, other_guild)

    def test_embed_contains_vote_totals_and_discussion(self) -> None:
        bot = SimpleNamespace(
            db=SimpleNamespace(),
            embeds=SimpleNamespace(
                make=lambda **kwargs: self._make_embed(**kwargs)
            ),
            get_guild=lambda _: None,
        )
        suggestion = {
            "guild_id": 10,
            "author_id": 20,
            "number": 18,
            "title": "Melhorar árvores",
            "description": "Minha sugestão",
            "yes_votes": 3,
            "no_votes": 1,
        }
        author = SimpleNamespace(display_avatar=SimpleNamespace(url="https://example.com/avatar.png"), mention="<@20>", __str__=lambda self: "tasquett(o)")
        embed = SuggestionService(bot).build_suggestion_embed(
            suggestion_id=suggestion["number"], author=author, title=suggestion["title"], body=suggestion["description"],
            counts={"yes": suggestion["yes_votes"], "no": suggestion["no_votes"]},
        )
        self.assertIn("Sugestão #18", embed.title or "")
        self.assertIn("🗳️ Total de votos", {field.name for field in embed.fields})
        self.assertIn("4", {field.value for field in embed.fields})

    @staticmethod
    def _make_embed(**kwargs: object) -> discord.Embed:
        embed = discord.Embed(title=str(kwargs["title"]), description=str(kwargs["description"]))
        for name, value, inline in kwargs.get("fields", []):
            embed.add_field(name=name, value=value, inline=inline)
        return embed
