from __future__ import annotations

from typing import Any

import discord

from app.services.suggestion_repository import SuggestionRepository


class SuggestionService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.repo = SuggestionRepository(bot.db)

    def build_panel_embed(self) -> discord.Embed:
        return self.bot.embeds.make(
            title="💡 Central de Sugestões",
            description="✨ Tem uma ideia para melhorar Drakoria? Envie por aqui.\n🗳️ Cada sugestão vira uma publicação com votação e um tópico próprio para debate.",
            fields=[
                ("📌 Como funciona", "Clique no botão abaixo e escreva tua sugestão com clareza. 💬 A discussão será criada automaticamente.", False),
                ("🌟 Boa sugestão tem", "🎯 Objetivo claro, impacto esperado e detalhes suficientes para a staff entender.", False),
            ],
        )

    def build_suggestion_embed(self, *, suggestion_id: int, author: discord.abc.User, title: str, body: str, counts: dict[str, int] | None = None, thread_id: int | None = None) -> discord.Embed:
        counts = counts or {"yes": 0, "no": 0}
        total = int(counts.get("yes", 0)) + int(counts.get("no", 0))
        embed = self.bot.embeds.make(title=f"💡 Sugestão #{suggestion_id} | {title}", description=body[:3900], author_name=str(author), author_icon_url=author.display_avatar.url, timestamp=True)
        embed.add_field(name="👤 Autor", value=author.mention, inline=True)
        embed.add_field(name="✅ Votos Sim", value=str(int(counts.get("yes", 0))), inline=True)
        embed.add_field(name="❌ Votos Não", value=str(int(counts.get("no", 0))), inline=True)
        embed.add_field(name="🗳️ Total de votos", value=str(total), inline=True)
        embed.add_field(name="💬 Discussão", value=f"<#{thread_id}>" if thread_id else "⏳ Tópico sendo preparado...", inline=True)
        return embed

    async def publish_panel(self, guild: discord.Guild) -> discord.Message:
        await self.repo.ensure_schema()
        if not self.bot.server_map.suggestions_enabled():
            raise RuntimeError("O painel de sugestões está desativado.")
        channel_id = self.bot.server_map.suggestions_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("O canal do painel de sugestões não foi localizado.")
        state = await self.repo.get_panel(guild.id)
        message = None
        if state:
            try:
                message = await channel.fetch_message(int(state["message_id"]))
                await message.edit(embed=self.build_panel_embed(), view=self.bot.view_factory.build_suggestion_panel_view())
            except discord.NotFound:
                message = None
        if message is None:
            message = await channel.send(embed=self.build_panel_embed(), view=self.bot.view_factory.build_suggestion_panel_view())
        await self.repo.save_panel(guild.id, channel.id, message.id)
        return message

    async def create_suggestion(self, interaction: discord.Interaction, *, title: str, body: str) -> discord.Message:
        await self.repo.ensure_schema()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise RuntimeError("Sugestões só podem ser enviadas dentro do servidor oficial.")
        if not self.bot.server_map.suggestions_enabled():
            raise RuntimeError("A Central de Sugestões está desativada.")
        channel_id = self.bot.server_map.suggestions_output_channel_id()
        channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("O canal de sugestões não foi localizado.")
        clean_title, clean_body = title.strip()[:120], body.replace("\r\n", "\n").strip()
        if not clean_title or not clean_body:
            raise RuntimeError("Informe título e descrição para a sugestão.")
        suggestion_id = await self.repo.create(interaction.guild.id, interaction.user.id, channel.id, clean_title, clean_body)
        message = await channel.send(embed=self.build_suggestion_embed(suggestion_id=suggestion_id, author=interaction.user, title=clean_title, body=clean_body), view=self.bot.view_factory.build_suggestion_vote_view())
        await self.repo.update_message(suggestion_id, message.id)
        thread = await message.create_thread(name=f"Sugestão #{suggestion_id}: {clean_title}"[:100])
        await self.repo.update_message(suggestion_id, message.id, thread.id)
        await message.edit(embed=self.build_suggestion_embed(suggestion_id=suggestion_id, author=interaction.user, title=clean_title, body=clean_body, thread_id=thread.id), view=self.bot.view_factory.build_suggestion_vote_view())
        await thread.send(f"💬 Discussão aberta para a sugestão de {interaction.user.mention}.")
        return message

    async def register_vote(self, interaction: discord.Interaction, vote: str) -> None:
        await self.repo.ensure_schema()
        if not interaction.message:
            await interaction.response.send_message("Não foi possível identificar a sugestão.", ephemeral=True)
            return
        suggestion = await self.repo.get_by_message(interaction.message.id)
        if not suggestion:
            await interaction.response.send_message("Esta mensagem não está vinculada a uma sugestão.", ephemeral=True)
            return
        counts = await self.repo.set_vote(int(suggestion["id"]), interaction.user.id, vote)
        author = interaction.guild.get_member(int(suggestion["author_id"])) if interaction.guild else None
        author = author or await self.bot.fetch_user(int(suggestion["author_id"]))
        await interaction.response.edit_message(embed=self.build_suggestion_embed(suggestion_id=int(suggestion["id"]), author=author, title=str(suggestion["title"]), body=str(suggestion["body"]), counts=counts, thread_id=int(suggestion["thread_id"]) if suggestion.get("thread_id") else None), view=self.bot.view_factory.build_suggestion_vote_view(counts))
