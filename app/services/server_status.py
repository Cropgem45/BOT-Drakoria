from __future__ import annotations

import asyncio
import json
import re
import socket
import struct
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import discord


@dataclass(slots=True)
class MinecraftStatus:
    online: bool
    players_online: int
    players_max: int | None
    latency_ms: int | None
    version: str | None
    motd: str | None
    error: str | None = None


class ServerStatusService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._task: asyncio.Task[None] | None = None

    def enabled(self) -> bool:
        return self.bot.server_map.server_status_enabled()

    async def bootstrap(self, guild: discord.Guild) -> None:
        if not self.enabled():
            return
        # DESATIVADO TEMPORARIAMENTE - 03/06/2026
        # await self.publish_panel(guild)
        # if self._task is None or self._task.done():
        #     self._task = asyncio.create_task(self._auto_refresh_loop(), name="drakoria-server-status-refresh")

    async def _auto_refresh_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                guild = self.bot.get_guild(self.bot.server_map.guild_id())
                if guild is not None and self.enabled():
                    await self.refresh_panel(guild)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.bot.log.exception("Falha ao atualizar painel de status do servidor.")
            await asyncio.sleep(self.bot.server_map.server_status_update_interval_seconds())

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        if not self.enabled():
            raise RuntimeError("Painel de status do servidor desabilitado na configuracao.")
        channel_id = self.bot.server_map.server_status_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do painel de status do servidor nao encontrado.")

        embed = await self.build_status_embed(guild)
        stored = await self.bot.db.get_server_status_panel_message(guild.id)
        if stored:
            saved_channel = guild.get_channel(int(stored["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel) and saved_channel.id == channel.id:
                try:
                    message = await saved_channel.fetch_message(int(stored["message_id"]))
                    await message.edit(embed=embed)
                    await self.bot.db.save_server_status_panel_message(guild.id, saved_channel.id, message.id)
                    return message
                except discord.NotFound:
                    pass

        message = await channel.send(embed=embed)
        await self.bot.db.save_server_status_panel_message(guild.id, channel.id, message.id)
        return message

    async def refresh_panel(self, guild: discord.Guild) -> None:
        stored = await self.bot.db.get_server_status_panel_message(guild.id)
        if not stored:
            await self.publish_panel(guild)
            return
        channel = guild.get_channel(int(stored["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(stored["message_id"]))
        except discord.NotFound:
            await self.publish_panel(guild)
            return
        await message.edit(embed=await self.build_status_embed(guild))

    async def build_status_embed(self, guild: discord.Guild) -> discord.Embed:
        now = datetime.now(UTC)
        minecraft = await self.minecraft_status() if self.bot.server_map.server_status_players_source() == "minecraft" else None
        status = "Online" if minecraft and minecraft.online else self.bot.server_map.server_status_state()
        if minecraft and not minecraft.online:
            status = "Em manutencao"
        players_online = minecraft.players_online if minecraft else self.players_online(guild)
        max_players = minecraft.players_max if minecraft and minecraft.players_max is not None else self.bot.server_map.server_status_max_players()
        players_label = f"{players_online}/{max_players}" if max_players else str(players_online)
        status_icon = "🟢" if status.lower() == "online" else "🔴"
        latency_ms = minecraft.latency_ms if minecraft and minecraft.latency_ms is not None else round(self.bot.latency * 1000) if self.bot.latency else 0
        description = minecraft.motd if minecraft and minecraft.motd else self.bot.server_map.server_status_description()
        if minecraft and not minecraft.online:
            players_label = "0"
            description = "O servidor esta em manutencao no momento. Volte em breve para acompanhar a proxima aventura."

        embed = discord.Embed(
            title=f"⚔️ {self.bot.server_map.server_status_name()}",
            description=description,
            color=self.bot.embeds.success_color if status.lower() == "online" else self.bot.embeds.error_color,
        )
        embed.add_field(name="Status", value=f"{status_icon} **{status}**", inline=True)
        embed.add_field(name="Players Online", value=f"👥 **{players_label}**", inline=True)
        embed.add_field(name="Ping do Servidor", value=f"📡 **{latency_ms} ms**", inline=True)
        if minecraft and minecraft.version:
            embed.add_field(name="Versao", value=f"`{minecraft.version}`", inline=True)
        embed.add_field(name="Comunidade", value=f"🏰 **{guild.member_count or len(guild.members)}** membros", inline=True)
        embed.add_field(name="Atualizacao", value=discord.utils.format_dt(now, style="R"), inline=True)
        if minecraft and minecraft.error:
            embed.add_field(name="Leitura do Servidor", value=f"`{minecraft.error[:900]}`", inline=False)
        else:
            embed.add_field(name="Reino", value="✨ Dados lidos diretamente do servidor.", inline=True)
        thumb = self.bot.embeds.default_thumbnail or self.bot.embeds.guild_icon_url
        if thumb:
            embed.set_thumbnail(url=thumb)
        footer_icon = self.bot.embeds.footer_icon or self.bot.embeds.guild_icon_url
        if footer_icon:
            embed.set_footer(text="Drakoria | Status atualizado automaticamente", icon_url=footer_icon)
        else:
            embed.set_footer(text="Drakoria | Status atualizado automaticamente")
        embed.timestamp = now
        return embed

    async def minecraft_status(self) -> MinecraftStatus:
        host = self.bot.server_map.server_status_minecraft_host()
        if not host:
            return MinecraftStatus(False, 0, None, None, None, None, "minecraft_host nao configurado")
        port = self.bot.server_map.server_status_minecraft_port()
        timeout = self.bot.server_map.server_status_minecraft_timeout_seconds()
        try:
            return await asyncio.to_thread(self._query_minecraft_status, host, port, timeout)
        except Exception as exc:
            return MinecraftStatus(False, 0, None, None, None, None, str(exc)[:300])

    def _query_minecraft_status(self, host: str, port: int, timeout: float) -> MinecraftStatus:
        start = time.perf_counter()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            host_bytes = host.encode("utf-8")
            handshake = (
                self._write_varint(765)
                + self._write_varint(len(host_bytes))
                + host_bytes
                + struct.pack(">H", port)
                + self._write_varint(1)
            )
            sock.sendall(self._write_varint(len(handshake) + 1) + self._write_varint(0) + handshake)
            sock.sendall(self._write_varint(1) + self._write_varint(0))
            self._read_varint(sock)
            self._read_varint(sock)
            payload_length = self._read_varint(sock)
            payload = self._read_exact(sock, payload_length)
        latency_ms = round((time.perf_counter() - start) * 1000)
        data = json.loads(payload.decode("utf-8"))
        players = data.get("players") if isinstance(data.get("players"), dict) else {}
        version = data.get("version") if isinstance(data.get("version"), dict) else {}
        return MinecraftStatus(
            online=True,
            players_online=int(players.get("online") or 0),
            players_max=int(players["max"]) if players.get("max") is not None else None,
            latency_ms=latency_ms,
            version=str(version.get("name") or "") or None,
            motd=self._minecraft_text(data.get("description")),
        )

    @classmethod
    def _minecraft_text(cls, value: Any) -> str | None:
        if isinstance(value, str):
            text = value
        elif isinstance(value, dict):
            chunks = [str(value.get("text") or "")]
            extra = value.get("extra")
            if isinstance(extra, list):
                chunks.extend(cls._minecraft_text(item) or "" for item in extra)
            text = "".join(chunks)
        elif isinstance(value, list):
            text = "".join(cls._minecraft_text(item) or "" for item in value)
        else:
            return None
        text = re.sub(r"§.", "", text).strip()
        return text[:500] if text else None

    @staticmethod
    def _write_varint(value: int) -> bytes:
        output = b""
        while True:
            byte = value & 0x7F
            value >>= 7
            output += bytes([byte | (0x80 if value else 0)])
            if not value:
                return output

    @staticmethod
    def _read_varint(sock: socket.socket) -> int:
        value = 0
        shift = 0
        for _ in range(5):
            raw = sock.recv(1)
            if not raw:
                raise EOFError("conexao encerrada pelo servidor")
            byte = raw[0]
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7
        raise ValueError("varint invalido na resposta do servidor")

    @staticmethod
    def _read_exact(sock: socket.socket, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise EOFError("conexao encerrada pelo servidor")
            data += chunk
        return data

    def players_online(self, guild: discord.Guild) -> int:
        source = self.bot.server_map.server_status_players_source()
        if source == "manual":
            return self.bot.server_map.server_status_manual_players_online()
        if source == "voice":
            configured = set(self.bot.server_map.server_status_voice_channel_ids())
            channels = [
                channel
                for channel in guild.voice_channels
                if not configured or channel.id in configured
            ]
            return sum(1 for channel in channels for member in channel.members if not member.bot)
        return sum(1 for member in guild.members if not member.bot)
