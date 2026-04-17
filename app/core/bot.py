from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

from app.core.embeds import EmbedFactory
from app.core.logging import CentralLogger, configure_logging
from app.core.permissions import PermissionService
from app.core.server_map import ServerMap
from app.core.settings import ConfigManager, RuntimeSettings, load_runtime_settings
from app.core.views import ViewFactory
from app.repositories.database import Database
from app.services.diagnostics import HealthcheckService
from app.services.beta_program import BetaProgramService
from app.services.member_registration import MemberRegistrationService
from app.services.points import PointService
from app.services.registration import RegistrationService
from app.services.tickets import TicketService


COGS = [
    "app.cogs.administration",
    "app.cogs.beta_program",
    "app.cogs.registration",
    "app.cogs.member_registration",
    "app.cogs.points",
    "app.cogs.announcements",
    "app.cogs.tickets",
]


class DrakoriaBot(commands.Bot):
    def __init__(self, settings: RuntimeSettings, config: dict[str, Any]) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.voice_states = True
        # O projeto opera via slash commands; manter apenas menções evita exigir
        # o intent privilegiado de message content sem perder compatibilidade.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.runtime = settings
        self.config = config
        self.server_map = ServerMap(config)
        self.embeds = EmbedFactory(self.server_map.style())
        self.db = Database(settings.database_path)
        self.central_logger = CentralLogger(self)
        self.permission_service = PermissionService(self)
        self.view_factory = ViewFactory(self)
        self.point_service = PointService(self)
        self.registration_service = RegistrationService(self)
        self.member_registration_service = MemberRegistrationService(self)
        self.beta_program_service = BetaProgramService(self)
        self.ticket_service = TicketService(self)
        self.healthcheck_service = HealthcheckService(self)
        self.registered_persistent_views: dict[str, int] = {}
        self._voice_point_runtime_ready = False
        self.log = logging.getLogger("drakoria.bot")

    async def setup_hook(self) -> None:
        self.tree.on_error = self._on_tree_error
        await self.db.initialize()
        await self.db.ensure_guild(self.server_map.guild_id(), True)
        await self.view_factory.register_persistent_views()
        for cog in COGS:
            try:
                await self.load_extension(cog)
            except Exception:
                self.log.exception("Falha ao carregar a extensao %s", cog)
                raise
        guild = discord.Object(id=self.server_map.guild_id())
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        if self.user:
            self.log.info("Bot pronto como %s (%s)", self.user, self.user.id)
        guild = self.get_guild(self.server_map.guild_id())
        if not guild:
            self.log.warning(
                "A guild configurada (%s) nao foi localizada entre os servidores conectados.",
                self.server_map.guild_id(),
            )
        else:
            await self._resolve_local_logo(guild)
            if guild.icon:
                self.embeds.guild_icon_url = guild.icon.url
                if not self.embeds.default_thumbnail:
                    self.embeds.default_thumbnail = guild.icon.url
        if not self._voice_point_runtime_ready:
            self._voice_point_runtime_ready = True
            await self.point_service.bootstrap_runtime()
        if guild is not None:
            try:
                if self.server_map.registration_panel_enabled():
                    await self.registration_service.publish_panel(guild)
            except Exception:
                self.log.exception("Falha ao sincronizar painel de registro no on_ready.")
            try:
                if self.server_map.member_registration_enabled():
                    await self.member_registration_service.publish_panel(guild)
            except Exception:
                self.log.exception("Falha ao sincronizar painel de cadastro no on_ready.")
            try:
                if self.server_map.beta_program_enabled():
                    await self.beta_program_service.publish_panel(guild)
            except Exception:
                self.log.exception("Falha ao sincronizar painel do programa beta no on_ready.")

    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id != self.server_map.guild_id():
            return
        visitor_role_id = self.server_map.role("visitor")
        if visitor_role_id:
            role = member.guild.get_role(visitor_role_id)
            if role:
                await member.add_roles(role, reason="Entrada inicial no reino")
        welcome_channel_id = self.server_map.channel("welcome")
        welcome_channel = self.get_channel(welcome_channel_id) if welcome_channel_id else None
        if isinstance(welcome_channel, discord.TextChannel):
            await welcome_channel.send(
                embed=self.embeds.make(
                    title="Novo Viajante nas Fronteiras",
                    description=(
                        f"{member.mention} acaba de chegar a Drakoria.\n"
                        "Dirige-te ao painel de cadastro oficial para concluir tua entrada no servidor."
                    ),
                )
            )

    async def run_async(self) -> None:
        await self.start(self.runtime.token)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        await self.point_service.handle_voice_state_update(member, before, after)

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        await self.point_service.handle_member_update(before, after)

    async def _on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        root_error = getattr(error, "original", error)
        self.log.exception("Falha em slash command: %s", root_error)
        message = str(root_error) if str(root_error).strip() else "Erro inesperado ao processar o comando."
        embed = self.embeds.error("Falha no comando", message[:1800])
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            self.log.exception("Falha ao responder erro de slash command para interaction %s", interaction.id)


    def _get_local_logo_path(self) -> str | None:
        """Returns absolute path if style.logo_url points to a local file."""
        logo_url = self.server_map.style().get("logo_url", "")
        if not isinstance(logo_url, str) or logo_url.strip().startswith("http"):
            return None
        candidate = Path(logo_url.strip())
        if not candidate.is_absolute():
            candidate = self.runtime.config_path.parent.parent / candidate
        return str(candidate) if candidate.exists() else None

    @staticmethod
    def _cdn_url_expired(url: str) -> bool:
        match = re.search(r"[?&]ex=([0-9a-f]+)", url)
        if not match:
            return False
        try:
            return time.time() > int(match.group(1), 16)
        except ValueError:
            return False

    async def _resolve_local_logo(self, guild: discord.Guild) -> None:
        """Upload local logo to Discord CDN on startup; cache the signed URL."""
        local_path = self._get_local_logo_path()
        if not local_path:
            return

        cache_file = self.runtime.database_path.parent / "logo_cdn.txt"
        if cache_file.exists():
            cached = cache_file.read_text("utf-8").strip()
            if cached and not self._cdn_url_expired(cached):
                self.embeds.default_thumbnail = cached
                self.embeds.footer_icon = cached
                self.log.info("Logo CDN carregada do cache.")
                return

        channel_id = (
            self.server_map.log_channel("tickets")
            or self.server_map.log_channel("announcements")
            or self.server_map.log_channel("points")
        )
        channel = self.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            self.log.warning("Nenhum canal de log disponivel para upload da logo local.")
            return

        try:
            msg = await channel.send(
                content="— logo asset (nao apagar) —",
                file=discord.File(local_path, filename="logo.png"),
            )
            if msg.attachments:
                cdn_url = msg.attachments[0].url
                cache_file.write_text(cdn_url, encoding="utf-8")
                self.embeds.default_thumbnail = cdn_url
                self.embeds.footer_icon = cdn_url
                self.log.info("Logo local enviada para Discord CDN.")
        except Exception:
            self.log.exception("Falha ao fazer upload da logo local para Discord.")


def build_bot() -> DrakoriaBot:
    settings = load_runtime_settings()
    configure_logging(settings.log_level)
    config = ConfigManager(settings.config_path).load()
    return DrakoriaBot(settings, config)


