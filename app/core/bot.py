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
from app.services.donaters import DonaterService
from app.services.member_registration import MemberRegistrationService
from app.services.points import PointService
from app.services.registration import RegistrationService
from app.services.staff_timeclock_service import StaffTimeclockService
from app.services.tickets import TicketService


TIMECLOCK_SYSTEMS_ENABLED = False

COGS = [
    "app.cogs.administration",
    "app.cogs.beta_program",
    "app.cogs.registration",
    "app.cogs.member_registration",
    "app.cogs.announcements",
    "app.cogs.tickets",
    "app.cogs.donaters",
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
        self.staff_timeclock_service = StaffTimeclockService(self)
        self.registration_service = RegistrationService(self)
        self.member_registration_service = MemberRegistrationService(self)
        self.beta_program_service = BetaProgramService(self)
        self.ticket_service = TicketService(self)
        self.donater_service = DonaterService(self)
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
        synced_commands = await self.tree.sync(guild=guild)
        self.log.info(
            "Slash commands sincronizados na guild %s: %s",
            self.server_map.guild_id(),
            ", ".join(sorted(command.name for command in synced_commands)),
        )

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
        if TIMECLOCK_SYSTEMS_ENABLED and not self._voice_point_runtime_ready:
            self._voice_point_runtime_ready = True
            await self.point_service.bootstrap_runtime()
            await self.staff_timeclock_service.bootstrap()
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
                    await self.beta_program_service.publish_quota_panel(guild)
            except Exception:
                self.log.exception("Falha ao sincronizar painel do programa beta no on_ready.")
            try:
                await self.donater_service.bootstrap(guild)
            except Exception:
                self.log.exception("Falha ao sincronizar Trono dos Patronos no on_ready.")

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
        if not TIMECLOCK_SYSTEMS_ENABLED:
            return
        await self.point_service.handle_voice_state_update(member, before, after)
        await self.staff_timeclock_service.handle_voice_state_update(member, before, after)

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not TIMECLOCK_SYSTEMS_ENABLED:
            return
        await self.point_service.handle_member_update(before, after)
        await self.staff_timeclock_service.handle_member_update(before, after)

    async def _on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        root_error = getattr(error, "original", error)
        data = interaction.data if isinstance(interaction.data, dict) else {}
        raw_name = str(data.get("name") or "")
        if isinstance(root_error, discord.app_commands.CommandSignatureMismatch):
            command_name = str(getattr(getattr(interaction, "command", None), "name", "") or "")
            raw_subcommand = ""
            for option in data.get("options") or []:
                if isinstance(option, dict) and option.get("type") in {1, 2}:
                    raw_subcommand = str(option.get("name") or "")
                    break
            if command_name == "cadastrar_influencer" or (raw_name == "beta_program" and raw_subcommand == "cadastrar_influencer"):
                self.log.warning(
                    "Signature mismatch do comando antigo cadastrar_influencer ignorado no handler global: interaction=%s data=%s",
                    interaction.id,
                    interaction.data,
                )
                return
        if isinstance(root_error, discord.HTTPException) and getattr(root_error, "code", None) in {40060, 10062}:
            self.log.warning(
                "Interacao %s indisponivel no handler global (code=%s); erro ignorado.",
                interaction.id,
                getattr(root_error, "code", None),
            )
            return
        if isinstance(root_error, discord.app_commands.CommandNotFound):
            command_name = str(getattr(root_error, "name", "") or "")
            if command_name == "gerar_codigo" or raw_name == "gerar_codigo":
                try:
                    await self._handle_raw_generate_beta_code(interaction)
                    self.log.warning(
                        "gerar_codigo processado pelo fallback raw apos CommandNotFound: interaction=%s data=%s",
                        interaction.id,
                        interaction.data,
                    )
                    return
                except Exception as exc:
                    root_error = exc
            if command_name in {"cadastrar_influencer", "listar_influencers"}:
                embed = self.embeds.warning(
                    "Comando antigo removido",
                    (
                        "Esse atalho foi removido para evitar duplicidade.\n\n"
                        "Use o comando oficial: `/beta_program gerar_codigo`.\n"
                        "Se o Discord ainda sugerir `/cadastrar_influencer`, feche e abra o Discord ou use `Ctrl+R` para recarregar."
                    ),
                )
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception:
                    self.log.exception("Falha ao responder comando antigo para interaction %s", interaction.id)
                return
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

    async def user_has_permission_role(self, interaction: discord.Interaction, permission_key: str) -> bool:
        if not interaction.guild:
            return False
        allowed_roles = set(self.server_map.permission_roles(permission_key))
        if not allowed_roles:
            return False
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is not None and allowed_roles.intersection(role.id for role in member.roles):
            return True
        cached_member = interaction.guild.get_member(interaction.user.id)
        if cached_member is not None and allowed_roles.intersection(role.id for role in cached_member.roles):
            return True
        try:
            fetched_member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.HTTPException:
            self.log.warning(
                "Nao foi possivel buscar membro %s para permissao %s.",
                interaction.user.id,
                permission_key,
            )
            return False
        has_role = bool(allowed_roles.intersection(role.id for role in fetched_member.roles))
        if not has_role:
            self.log.warning(
                "Permissao %s negada para %s. Esperado=%s | cargos=%s",
                permission_key,
                interaction.user.id,
                sorted(allowed_roles),
                [role.id for role in fetched_member.roles],
            )
        return has_role

    async def _handle_raw_generate_beta_code(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            raise discord.app_commands.CheckFailure("Este comando deve ser usado no servidor.")
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        if not await self.user_has_permission_role(interaction, "generate_beta_code"):
            raise discord.app_commands.CheckFailure("Apenas Criadores de Conteúdo podem gerar códigos beta.")

        data = interaction.data if isinstance(interaction.data, dict) else {}
        options = {
            str(option.get("name")): option.get("value")
            for option in data.get("options") or []
            if isinstance(option, dict) and option.get("name")
        }
        nome = str(options.get("nome") or "").strip()
        if not nome:
            raise RuntimeError("Informe o nome público do influencer ou campanha.")
        usuario = None
        if options.get("usuario") is not None:
            try:
                usuario = await interaction.guild.fetch_member(int(options["usuario"]))
            except (TypeError, ValueError, discord.HTTPException):
                usuario = None
        owner = usuario or interaction.user

        result = await self.beta_program_service.generate_single_use_influencer_code(
            interaction.guild.id,
            influencer_name=nome,
            owner_user_id=owner.id,
            created_by_id=interaction.user.id,
        )
        await self.beta_program_service.publish_quota_panel(interaction.guild)
        embed = discord.Embed(
            title="✅ Código Individual Gerado",
            description=(
                f"🎟️ Código: `{result['code']}`\n"
                f"👤 Influencer: **{nome}** ({owner.mention})\n"
                "📌 Uso: **1 pessoa, 1 única vez**\n"
                f"📊 Convites restantes para gerar: **{int(result['remaining'])}/5**"
            ),
            color=self.embeds.success_color,
        )
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Drakoria | Convite beta individual")
        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

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
