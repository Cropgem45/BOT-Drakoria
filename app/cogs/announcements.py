from __future__ import annotations

from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands


class AnnouncementModal(discord.ui.Modal, title="Publicar Anúncio"):
    mensagem = discord.ui.TextInput(
        label="Mensagem",
        style=discord.TextStyle.paragraph,
        placeholder="Digite o corpo do anúncio aqui. O Enter virará quebra de linha normal.",
        required=True,
        max_length=3800,
    )

    def __init__(self, cog: "AnnouncementCog", titulo: str, marcacao: discord.Role | None) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.titulo = titulo
        self.marcacao = marcacao

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._publish_announcement(
            interaction=interaction,
            titulo=self.titulo,
            mensagem=str(self.mensagem.value),
            marcacao=self.marcacao,
        )


class AnnouncementCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="anuncio", description="Abre o editor de anuncio oficial")
    @app_commands.guild_only()
    async def anuncio(
        self,
        interaction: discord.Interaction,
        titulo: str,
        marcacao: discord.Role | None = None,
    ) -> None:
        await interaction.response.send_modal(AnnouncementModal(self, titulo=titulo, marcacao=marcacao))

    async def _publish_announcement(
        self,
        *,
        interaction: discord.Interaction,
        titulo: str,
        mensagem: str,
        marcacao: discord.Role | None = None,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Este comando só pode ser usado dentro do servidor oficial.")
        if interaction.guild.id != self.bot.server_map.guild_id():
            raise app_commands.CheckFailure("Este comando é exclusivo da guild oficial de Drakoria.")
        if not isinstance(interaction.channel, discord.TextChannel):
            raise app_commands.CheckFailure("Este comando precisa ser usado em um canal de texto.")
        if not self.bot.server_map.announcements_enabled():
            raise app_commands.CheckFailure("O sistema de anúncios está desativado em configuração.")
        if not self.bot.permission_service.has(interaction.user, "publish_announcements"):
            raise app_commands.CheckFailure("Não possuis o selo da coroa para publicar anúncios.")
        if not self.bot.permission_service.has_any_role_id(
            interaction.user,
            self.bot.server_map.announcements_allowed_role_ids(),
        ) and not interaction.user.guild_permissions.administrator:
            raise app_commands.CheckFailure(
                "Teu cargo nao consta na lista `announcements.allowed_role_ids` e nao pode publicar comunicados."
            )

        target_channel = interaction.channel
        me = interaction.guild.me or interaction.guild.get_member(self.bot.user.id if self.bot.user else 0)
        if me is None:
            raise app_commands.CheckFailure("Não foi possível localizar o bot na guild.")
        missing_permissions = [
            label
            for attr, label in (
                ("view_channel", "View Channel"),
                ("send_messages", "Send Messages"),
                ("embed_links", "Embed Links"),
            )
            if not getattr(target_channel.permissions_for(me), attr, False)
        ]
        if missing_permissions:
            raise app_commands.CheckFailure(
                "O bot não possui permissões suficientes para anunciar neste canal.\n"
                f"Permissões ausentes: {', '.join(missing_permissions)}"
            )

        mention_content: str | None = None
        allowed_mentions = discord.AllowedMentions.none()
        if marcacao is not None:
            if not interaction.user.guild_permissions.mention_everyone:
                raise app_commands.CheckFailure("Teu usuário não possui permissão para marcar cargos.")
            if not target_channel.permissions_for(me).mention_everyone:
                raise app_commands.CheckFailure("O bot não possui permissão `Mention Everyone` neste canal.")
            mention_content = marcacao.mention
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=[marcacao], users=False)

        title_text = titulo.strip()
        body_text = mensagem.replace("\r\n", "\n").strip()
        if not title_text:
            raise app_commands.CheckFailure("O título não pode ser vazio.")
        if not body_text:
            raise app_commands.CheckFailure("A mensagem não pode ser vazia.")

        logo_icon_url, large_logo_url = self._resolve_logo_urls(interaction.guild)
        if not logo_icon_url:
            raise app_commands.CheckFailure(
                "A logo oficial não foi encontrada. Configure `announcements.logo_url` com uma URL válida."
            )
        embed = self.bot.embeds.make(
            title=title_text,
            description=body_text,
            color=self.bot.server_map.announcements_embed_color() or self.bot.embeds.default_color,
            thumbnail_url=large_logo_url,
            footer_text=self.bot.server_map.announcements_default_footer(),
            footer_icon_url=logo_icon_url,
            timestamp=True,
        )

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            sent_message = await target_channel.send(
                content=mention_content,
                embed=embed,
                allowed_mentions=allowed_mentions,
            )
            await self.bot.db.create_announcement(
                interaction.guild_id,
                interaction.user.id,
                target_channel.id,
                title_text,
                body_text,
            )
        except discord.HTTPException as exc:
            await self._safe_log(
                interaction=interaction,
                target_channel=target_channel,
                title=title_text,
                mention_text=mention_content,
                status="failed",
                failure_reason=f"Discord HTTPException: {exc}",
            )
            await interaction.followup.send(
                embed=self.bot.embeds.error(
                    "Falha no Envio",
                    "Não foi possível enviar o anúncio. Verifique permissões e tente novamente.",
                ),
                ephemeral=True,
            )
            return

        await self._safe_log(
            interaction=interaction,
            target_channel=target_channel,
            title=title_text,
            mention_text=mention_content,
            status="success",
            failure_reason=None,
        )
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Anúncio Publicado",
                f"O anúncio foi publicado em {target_channel.mention}.\nMensagem: indisponível.",
            ),
            ephemeral=True,
        )

    async def _safe_log(
        self,
        *,
        interaction: discord.Interaction,
        target_channel: discord.TextChannel,
        title: str,
        mention_text: str | None,
        status: str,
        failure_reason: str | None,
    ) -> None:
        try:
            log_channel_id = self.bot.server_map.announcements_log_channel_id()
            log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id and interaction.guild else None
            if not isinstance(log_channel, discord.TextChannel):
                return
            fields = [
                ("Autor", f"{interaction.user}", False),
                ("Canal de destino", f"{target_channel.mention}", False),
                ("Titulo", title[:200], False),
                ("Marcação", mention_text or "nenhuma", True),
                ("Resultado", status, True),
            ]
            if failure_reason:
                fields.append(("Falha", failure_reason[:1024], False))
            embed = self.bot.embeds.make(
                title="Auditoria de Anúncio",
                description="Registro administrativo de publicação de comunicado.",
                color=self.bot.embeds.success_color if status == "success" else self.bot.embeds.error_color,
                fields=fields,
                timestamp=True,
            )
            await log_channel.send(embed=embed)
        except Exception:
            self.bot.log.exception("Falha ao registrar log administrativo de anuncio")

    @staticmethod
    def _valid_url(raw: str) -> bool:
        parsed = urlparse(raw)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _resolve_logo_urls(self, guild: discord.Guild) -> tuple[str | None, str | None]:
        icon_logo = self.bot.server_map.announcements_logo_url()
        large_logo = self.bot.server_map.announcements_large_logo_url()
        if icon_logo and not self._valid_asset_url(icon_logo):
            icon_logo = None
        if large_logo and not self._valid_asset_url(large_logo):
            large_logo = None
        style_logo = self.bot.embeds.footer_icon
        if not icon_logo and isinstance(style_logo, str) and style_logo.strip() and self._valid_asset_url(style_logo.strip()):
            icon_logo = style_logo.strip()
        guild_icon_url = str(guild.icon.url) if guild.icon else None
        if not icon_logo and guild_icon_url and self._valid_url(guild_icon_url):
            icon_logo = guild_icon_url
        if not large_logo:
            large_logo = icon_logo
        return icon_logo, large_logo

    def _valid_asset_url(self, raw: str) -> bool:
        if not self._valid_url(raw):
            return False
        parsed = urlparse(raw)
        blocked_hosts = {"example.com", "www.example.com"}
        if parsed.netloc.lower() in blocked_hosts:
            return False
        return True

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha no Anúncio", str(error)),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha no Anúncio", str(error)),
                    ephemeral=True,
                )
        except discord.HTTPException:
            self.bot.log.warning("Não foi possível responder erro de anúncio para interaction %s", interaction.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnnouncementCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))



