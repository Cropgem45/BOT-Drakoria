from __future__ import annotations

import asyncio
import json
import shutil
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import discord


TOP_DONATERS_CHANNEL_ID = 1506326402763460708
TOP_DONATER_ROLE_ID = 1506327687554400417
GENERAL_CHAT_CHANNEL_ID = 1487647482803392584
DONATIONS_CHANNEL_ID = 1487647476482838619
THRONE_GAP_ALERT_REAIS = 100
TOP_DONATERS_LIMIT = 10
THRONE_NAME_FRAME_WIDTH = 22


@dataclass(slots=True)
class DonationResult:
    user_id: int
    username: str
    previous_total_cents: int
    current_total_cents: int
    previous_top_id: str | None
    current_top_id: str | None
    throne_changed: bool


class DonaterService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self.path: Path = bot.runtime.database_path.parent / "donaters.json"
        self.backup_dir: Path = self.path.parent / "backups" / "donaters"
        self._lock = asyncio.Lock()
        self._cache: dict[str, Any] | None = None
        self._bootstrapped = False

    async def bootstrap(self, guild: discord.Guild) -> None:
        if self._bootstrapped:
            return
        self._bootstrapped = True
        await self.load()
        await self.refresh(guild, announce=False, create_if_missing=False)

    async def load(self) -> dict[str, Any]:
        async with self._lock:
            if self._cache is not None:
                return self._cache
            self._cache = self._load_from_disk()
            return self._cache

    async def add_donation(self, member: discord.Member, amount_reais: float, actor: discord.Member) -> DonationResult:
        cents = self._amount_to_cents(amount_reais)
        if cents <= 0:
            raise RuntimeError("O valor da doação precisa ser maior que zero.")
        return await self._mutate_user(member, actor, "add", cents)

    async def remove_donation(self, member: discord.Member, amount_reais: float, actor: discord.Member) -> DonationResult:
        cents = self._amount_to_cents(amount_reais)
        if cents <= 0:
            raise RuntimeError("O valor removido precisa ser maior que zero.")
        return await self._mutate_user(member, actor, "remove", cents)

    async def set_donation(self, member: discord.Member, amount_reais: float, actor: discord.Member) -> DonationResult:
        cents = self._amount_to_cents(amount_reais)
        if cents < 0:
            raise RuntimeError("O total definido não pode ser negativo.")
        return await self._mutate_user(member, actor, "set", cents)

    async def reset(self, guild: discord.Guild, actor: discord.Member) -> None:
        async with self._lock:
            data = await self._data_locked()
            previous_top_id = data["meta"].get("currentTopId")
            data["users"] = {}
            data["meta"].update(
                {
                    "currentTopId": None,
                    "topSince": None,
                    "lastUpdated": self._now_iso(),
                    "resetHistory": data["meta"].get("resetHistory", [])
                    + [{"at": self._now_iso(), "actorId": str(actor.id), "actorName": actor.display_name}],
                }
            )
            await self._save_locked()
        if previous_top_id:
            await self._sync_top_role(guild, previous_top_id, None)
        await self.refresh(guild, announce=False)
        await self._log(
            guild,
            "Reset do Trono dos Patronos",
            f"{actor.mention} resetou o ranking local de doadores.",
            color=0x8B0000,
        )

    async def refresh(
        self,
        guild: discord.Guild,
        *,
        announce: bool = False,
        create_if_missing: bool = True,
    ) -> discord.Message | None:
        async with self._lock:
            data = await self._data_locked()
            old_top_id = data["meta"].get("currentTopId")
            new_top_id = self._top_user_id(data)
            if new_top_id != old_top_id:
                data["meta"]["currentTopId"] = new_top_id
                data["meta"]["topSince"] = self._now_iso() if new_top_id else None
            data["meta"]["lastUpdated"] = self._now_iso()
            embed = self.build_ranking_embed(guild, data)
            await self._save_locked()

        await self._sync_top_role(guild, old_top_id, new_top_id)
        message = await self._upsert_ranking_message(guild, embed, create_if_missing=create_if_missing)
        if announce and new_top_id != old_top_id:
            await self._announce_throne_change(guild, old_top_id, new_top_id)
        return message

    async def announce_donation(self, guild: discord.Guild, member: discord.Member, amount_cents: int) -> None:
        channel = self._ranking_channel(guild)
        if not channel:
            return
        embed = discord.Embed(
            title="💎 O Reino Foi Fortalecido",
            description=(
                f"**{member.display_name}** fortaleceu Drakoria com **{self._format_money(amount_cents)}**!\n\n"
                "“Cada contribuição fortalece o reino.”"
            ),
            color=0xD6A23A,
        )
        embed.set_footer(text="Drakoria • Hall dos Grandes Patronos")
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    def build_ranking_embed(self, guild: discord.Guild, data: dict[str, Any]) -> discord.Embed:
        ranked = self._ranked_users(data)
        top = ranked[0] if ranked else None

        embed = discord.Embed(title="🔥 O TRONO DO REINO", color=0xB88922)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        if top:
            top_user_id, top_data = top
            top_member = guild.get_member(int(top_user_id))
            top_name = top_member.display_name if top_member else str(top_data.get("username") or f"Patrono {top_user_id}")
            top_since = self._parse_iso(data["meta"].get("topSince")) or self._parse_iso(top_data.get("dateJoined"))
            throne_days = max((datetime.now(UTC) - top_since).days, 0) if top_since else 0
            embed.add_field(
                name="👑 SOBERANO DO REINO",
                value=(
                    "╔══════════════════════╗\n"
                    f"{self._centered_throne_name(str(top_user_id), top_name)}\n"
                    "╚══════════════════════╝\n\n"
                    f"🔥 <@&{TOP_DONATER_ROLE_ID}>\n\n"
                    "💎 **TOTAL APOIADO**\n"
                    f"**{self._format_money(self._total_cents(top_data))}**\n\n"
                    "🏆 **NO TRONO HÁ**\n"
                    f"**{throne_days} DIAS**\n\n"
                    "████████████████████"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="👑 SOBERANO DO REINO",
                value=(
                    "╔══════════════════════╗\n"
                    f"{self._centered_plain_line('✨ TRONO VAZIO ✨')}\n"
                    "╚══════════════════════╝"
                ),
                inline=False,
            )

        ranking_blocks: list[str] = []
        medals = {1: "👑", 2: "🥈", 3: "🥉"}
        for position, (user_id, user_data) in enumerate(ranked[:TOP_DONATERS_LIMIT], start=1):
            if position == 1:
                continue
            ranking_blocks.append(
                f"{medals.get(position, '🏅')} **<@{user_id}>**\n"
                f"└ 💰 **{self._format_money(self._total_cents(user_data))}**"
            )
        embed.add_field(
            name=f"⚔️ GRANDES PATRONOS • TOP {TOP_DONATERS_LIMIT}",
            value="\n\n".join(ranking_blocks) if ranking_blocks else "Ainda não há desafiantes registrados no hall.",
            inline=False,
        )

        threat = self._throne_threat_line(guild, ranked)
        if threat:
            embed.add_field(name="⚠️ AMEAÇA AO TRONO", value=threat, inline=False)
        embed.set_footer(text="Drakoria • O Trono do Reino • Atualizado automaticamente")
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def _mutate_user(
        self,
        member: discord.Member,
        actor: discord.Member,
        action: str,
        value_cents: int,
    ) -> DonationResult:
        async with self._lock:
            data = await self._data_locked()
            previous_top_id = data["meta"].get("currentTopId")
            user_id = str(member.id)
            user_data = data["users"].setdefault(
                user_id,
                {
                    "username": member.display_name,
                    "total": 0,
                    "lastDonation": 0,
                    "history": [],
                    "dateJoined": self._now_iso(),
                },
            )
            previous_total = self._total_cents(user_data)
            if action == "add":
                current_total = previous_total + value_cents
                last_donation = value_cents
                event_type = "add"
            elif action == "remove":
                current_total = max(previous_total - value_cents, 0)
                last_donation = -min(value_cents, previous_total)
                event_type = "remove"
            elif action == "set":
                current_total = value_cents
                last_donation = current_total - previous_total
                event_type = "set"
            else:
                raise RuntimeError("Operação de doação desconhecida.")

            user_data["username"] = member.display_name
            user_data["total"] = self._cents_to_json_number(current_total)
            user_data["lastDonation"] = self._cents_to_json_number(last_donation)
            user_data.setdefault("dateJoined", self._now_iso())
            user_data.setdefault("history", []).append(
                {
                    "type": event_type,
                    "amount": self._cents_to_json_number(value_cents),
                    "delta": self._cents_to_json_number(last_donation),
                    "previousTotal": self._cents_to_json_number(previous_total),
                    "newTotal": self._cents_to_json_number(current_total),
                    "actorId": str(actor.id),
                    "actorName": actor.display_name,
                    "at": self._now_iso(),
                }
            )

            current_top_id = self._top_user_id(data)
            data["meta"]["lastUpdated"] = self._now_iso()
            await self._save_locked()

        return DonationResult(
            user_id=member.id,
            username=member.display_name,
            previous_total_cents=previous_total,
            current_total_cents=current_total,
            previous_top_id=previous_top_id,
            current_top_id=current_top_id,
            throne_changed=current_top_id != previous_top_id,
        )

    async def _upsert_ranking_message(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        *,
        create_if_missing: bool,
    ) -> discord.Message | None:
        channel = self._ranking_channel(guild)
        if not channel:
            raise RuntimeError("Canal 💎・top-doadores não encontrado ou inacessível.")

        async with self._lock:
            data = await self._data_locked()
            message_id = data["meta"].get("rankingMessageId")

        message: discord.Message | None = None
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
                message = None
        if message is None:
            if not create_if_missing:
                await self._log(
                    guild,
                    "Ranking de patronos não recriado",
                    (
                        "A mensagem fixa do ranking não foi encontrada durante a sincronização automática. "
                        "Use `/top refresh` para criar uma nova mensagem fixa, se necessário."
                    ),
                    color=0xD6A23A,
                )
                return None
            message = await channel.send(embed=embed)
            async with self._lock:
                data = await self._data_locked()
                data["meta"]["rankingChannelId"] = channel.id
                data["meta"]["rankingMessageId"] = message.id
                await self._save_locked()
        return message

    async def _sync_top_role(self, guild: discord.Guild, old_top_id: str | None, new_top_id: str | None) -> None:
        role = guild.get_role(TOP_DONATER_ROLE_ID)
        if role is None:
            await self._log(guild, "Cargo Top Donater ausente", f"Cargo `{TOP_DONATER_ROLE_ID}` não encontrado.", color=0x8B0000)
            return
        if old_top_id and old_top_id != new_top_id:
            old_member = guild.get_member(int(old_top_id))
            if old_member and role in old_member.roles:
                await old_member.remove_roles(role, reason="Perdeu o primeiro lugar no Trono dos Patronos")
        if new_top_id:
            new_member = guild.get_member(int(new_top_id))
            if new_member and role not in new_member.roles:
                await new_member.add_roles(role, reason="Conquistou o primeiro lugar no Trono dos Patronos")

    async def _announce_throne_change(self, guild: discord.Guild, old_top_id: str | None, new_top_id: str | None) -> None:
        if not new_top_id:
            return
        channel = guild.get_channel(GENERAL_CHAT_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            channel = self._ranking_channel(guild)
        if not channel:
            return
        data = await self.load()
        new_total = self._total_cents(data.get("users", {}).get(str(new_top_id), {}))
        old_mention = f"<@{old_top_id}>" if old_top_id else "o trono vazio"
        embed = discord.Embed(
            title="# 🚨 O TRONO MUDOU DE DONO!",
            description=(
                "👑 **UMA NOVA LENDA ASCENDEU!**\n\n"
                f"✨ <@{new_top_id}> derrubou {old_mention}\n"
                "e conquistou o posto de maior patrono de Drakoria.\n\n"
                "🔥 **Cargo recebido:**\n"
                f"<@&{TOP_DONATER_ROLE_ID}>\n\n"
                "💰 **Total apoiado:**\n"
                f"**{self._format_money(new_total)}**\n\n"
                "⚔️ O reino observa...\n"
                "Quem ousará tomar o trono?\n\n"
                "💎 **Veja o ranking:**\n"
                f"<#{TOP_DONATERS_CHANNEL_ID}>\n\n"
                "💎 Quer disputar o trono?\n"
                f"Faça sua doação em <#{DONATIONS_CHANNEL_ID}>"
            ),
            color=0xB11226,
        )
        embed.set_footer(text="Drakoria • Evento do Reino • Hall dos Grandes Patronos")
        embed.timestamp = discord.utils.utcnow()
        role = guild.get_role(TOP_DONATER_ROLE_ID)
        mention_payload = f"<@{new_top_id}> <@&{TOP_DONATER_ROLE_ID}>"
        allowed_mentions = discord.AllowedMentions(
            users=True,
            roles=True,
            everyone=False,
            replied_user=False,
        )
        if role is not None:
            allowed_mentions = discord.AllowedMentions(
                users=[discord.Object(id=int(new_top_id))],
                roles=[role],
                everyone=False,
                replied_user=False,
            )
        await channel.send(
            content=mention_payload,
            embed=embed,
            allowed_mentions=allowed_mentions,
        )

    async def _log(self, guild: discord.Guild, title: str, description: str, *, color: int) -> None:
        channel_id = self.bot.server_map.announcements_log_channel_id() or self.bot.server_map.log_channel("announcements")
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.bot.embeds.make(title=title, description=description, color=color, timestamp=True)
        await channel.send(embed=embed)

    def _load_from_disk(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            data = self._default_data()
            self._write_json(data)
            return data
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return self._normalize_data(data)
        except (json.JSONDecodeError, OSError):
            corrupt_path = self.path.with_suffix(f".corrupt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json")
            try:
                shutil.copy2(self.path, corrupt_path)
            except OSError:
                pass
            restored = self._restore_latest_backup()
            self._write_json(restored)
            return restored

    def _restore_latest_backup(self) -> dict[str, Any]:
        backups = sorted(self.backup_dir.glob("donaters-*.json"), reverse=True)
        for backup in backups:
            try:
                with backup.open("r", encoding="utf-8") as file:
                    return self._normalize_data(json.load(file))
            except (json.JSONDecodeError, OSError):
                continue
        return self._default_data()

    async def _data_locked(self) -> dict[str, Any]:
        if self._cache is None:
            self._cache = self._load_from_disk()
        return self._cache

    async def _save_locked(self) -> None:
        if self._cache is None:
            return
        self._write_json(self._cache)

    def _write_json(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            backup_path = self.backup_dir / f"donaters-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
            try:
                shutil.copy2(self.path, backup_path)
            except OSError:
                pass
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        tmp_path.replace(self.path)
        self._prune_backups()

    def _prune_backups(self) -> None:
        backups = sorted(self.backup_dir.glob("donaters-*.json"), reverse=True)
        for old_backup in backups[25:]:
            try:
                old_backup.unlink()
            except OSError:
                pass

    @staticmethod
    def _default_data() -> dict[str, Any]:
        return {
            "users": {},
            "meta": {
                "rankingChannelId": TOP_DONATERS_CHANNEL_ID,
                "rankingMessageId": None,
                "currentTopId": None,
                "topSince": None,
                "rotationIndex": 0,
                "lastUpdated": None,
                "resetHistory": [],
            },
        }

    def _normalize_data(self, raw: Any) -> dict[str, Any]:
        data = self._default_data()
        if isinstance(raw, dict):
            if isinstance(raw.get("users"), dict):
                data["users"] = deepcopy(raw["users"])
            if isinstance(raw.get("meta"), dict):
                data["meta"].update(raw["meta"])
        for user_id, user_data in list(data["users"].items()):
            if not isinstance(user_data, dict):
                del data["users"][user_id]
                continue
            user_data.setdefault("username", f"Patrono {user_id}")
            user_data.setdefault("total", 0)
            user_data.setdefault("lastDonation", 0)
            user_data.setdefault("history", [])
            user_data.setdefault("dateJoined", self._now_iso())
        return data

    def _ranked_users(self, data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        return sorted(
            data.get("users", {}).items(),
            key=lambda item: (self._total_cents(item[1]), item[1].get("dateJoined") or ""),
            reverse=True,
        )

    def _top_user_id(self, data: dict[str, Any]) -> str | None:
        ranked = [item for item in self._ranked_users(data) if self._total_cents(item[1]) > 0]
        return ranked[0][0] if ranked else None

    def _throne_threat_line(self, guild: discord.Guild, ranked: list[tuple[str, dict[str, Any]]]) -> str | None:
        if len(ranked) < 2:
            return None
        top_total = self._total_cents(ranked[0][1])
        second_id, second_data = ranked[1]
        gap = top_total - self._total_cents(second_data)
        if gap <= 0 or gap > THRONE_GAP_ALERT_REAIS * 100:
            return None
        return f"👀 <@{second_id}> está a apenas **{self._format_money(gap)}** de roubar o trono."

    def _ranking_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.get_channel(TOP_DONATERS_CHANNEL_ID)
        return channel if isinstance(channel, discord.TextChannel) else None

    @staticmethod
    def _centered_plain_line(text: str) -> str:
        clipped = text[:THRONE_NAME_FRAME_WIDTH]
        pad = max((THRONE_NAME_FRAME_WIDTH - len(clipped)) // 2, 0)
        return f"{' ' * pad}{clipped}"

    @staticmethod
    def _centered_throne_name(user_id: str, display_name: str) -> str:
        mention = f"✨ <@{user_id}> ✨"
        estimated_rendered_len = len((display_name or "").strip()) + 5
        pad = max((THRONE_NAME_FRAME_WIDTH - estimated_rendered_len) // 2, 0)
        return f"{' ' * pad}{mention}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _amount_to_cents(value: float) -> int:
        return int(round(float(value) * 100))

    @staticmethod
    def _total_cents(user_data: dict[str, Any]) -> int:
        return int(round(float(user_data.get("total", 0)) * 100))

    @staticmethod
    def _cents_to_json_number(cents: int) -> int | float:
        if cents % 100 == 0:
            return cents // 100
        return round(cents / 100, 2)

    @staticmethod
    def _format_money(cents: int) -> str:
        reais = cents / 100
        text = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if text.endswith(",00"):
            text = text[:-3]
        return f"R$ {text}"
