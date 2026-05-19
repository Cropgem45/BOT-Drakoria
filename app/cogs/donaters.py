from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks


class TopDonatersCog(commands.Cog):
    top = app_commands.Group(name="top", description="Controle do Trono dos Patronos")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.rotate_throne_presence.start()

    async def cog_unload(self) -> None:
        self.rotate_throne_presence.cancel()

    @tasks.loop(minutes=20)
    async def rotate_throne_presence(self) -> None:
        guild = self.bot.get_guild(self.bot.server_map.guild_id())
        if guild is None:
            return
        await self.bot.donater_service.refresh(guild, announce=False)

    @rotate_throne_presence.before_loop
    async def before_rotate_throne_presence(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="adddonate", description="Adiciona uma doação ao Trono dos Patronos")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Patrono que realizou a doação", valor="Valor em reais")
    async def adddonate(self, interaction: discord.Interaction, usuario: discord.Member, valor: float) -> None:
        if not await self._safe_defer(interaction):
            return
        actor = self._require_admin(interaction)
        result = await self.bot.donater_service.add_donation(usuario, valor, actor)
        await self.bot.donater_service.refresh(interaction.guild, announce=result.throne_changed)
        await self.bot.donater_service.announce_donation(
            interaction.guild,
            usuario,
            self.bot.donater_service._amount_to_cents(valor),
        )
        await self._audit(
            interaction,
            "Doação Registrada",
            f"{actor.mention} adicionou doação para {usuario.mention}.",
            [
                ("Valor", self.bot.donater_service._format_money(self.bot.donater_service._amount_to_cents(valor)), True),
                ("Total Atual", self.bot.donater_service._format_money(result.current_total_cents), True),
            ],
        )
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.success(
                "Patrono Fortalecido",
                f"{usuario.mention} agora possui **{self.bot.donater_service._format_money(result.current_total_cents)}** no Trono do Reino.",
            ),
        )

    @app_commands.command(name="removedonate", description="Remove valor de doação por correção administrativa")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Patrono que receberá a correção", valor="Valor em reais")
    async def removedonate(self, interaction: discord.Interaction, usuario: discord.Member, valor: float) -> None:
        if not await self._safe_defer(interaction):
            return
        actor = self._require_admin(interaction)
        result = await self.bot.donater_service.remove_donation(usuario, valor, actor)
        await self.bot.donater_service.refresh(interaction.guild, announce=result.throne_changed)
        await self._audit(
            interaction,
            "Doação Corrigida",
            f"{actor.mention} removeu valor do histórico de {usuario.mention}.",
            [
                ("Correção", self.bot.donater_service._format_money(self.bot.donater_service._amount_to_cents(valor)), True),
                ("Total Atual", self.bot.donater_service._format_money(result.current_total_cents), True),
            ],
        )
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.success(
                "Correção Aplicada",
                f"O total de {usuario.mention} foi ajustado para **{self.bot.donater_service._format_money(result.current_total_cents)}**.",
            ),
        )

    @app_commands.command(name="setdonate", description="Define o valor exato de doação de um patrono")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Patrono que terá o total definido", valor="Valor exato em reais")
    async def setdonate(self, interaction: discord.Interaction, usuario: discord.Member, valor: float) -> None:
        if not await self._safe_defer(interaction):
            return
        actor = self._require_admin(interaction)
        result = await self.bot.donater_service.set_donation(usuario, valor, actor)
        await self.bot.donater_service.refresh(interaction.guild, announce=result.throne_changed)
        await self._audit(
            interaction,
            "Total de Patrono Definido",
            f"{actor.mention} definiu manualmente o total de {usuario.mention}.",
            [
                ("Total Anterior", self.bot.donater_service._format_money(result.previous_total_cents), True),
                ("Total Novo", self.bot.donater_service._format_money(result.current_total_cents), True),
            ],
        )
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.success(
                "Total Definido",
                f"{usuario.mention} agora está registrado com **{self.bot.donater_service._format_money(result.current_total_cents)}**.",
            ),
        )

    @top.command(name="refresh", description="Força a atualização manual da embed do Trono do Reino")
    @app_commands.guild_only()
    async def refresh(self, interaction: discord.Interaction) -> None:
        if not await self._safe_defer(interaction):
            return
        actor = self._require_admin(interaction)
        message = await self.bot.donater_service.refresh(interaction.guild, announce=False)
        await self._audit(
            interaction,
            "Trono Atualizado Manualmente",
            f"{actor.mention} forçou a atualização do ranking de patronos.",
            [("Mensagem", f"`{message.id}`", True)],
        )
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.success("Trono Atualizado", "A mensagem fixa do ranking foi sincronizada."),
        )

    @top.command(name="reset", description="Reseta o ranking de patronos com confirmação")
    @app_commands.guild_only()
    @app_commands.describe(confirmar="Digite CONFIRMAR para executar o reset")
    async def reset(self, interaction: discord.Interaction, confirmar: str) -> None:
        if not await self._safe_defer(interaction):
            return
        actor = self._require_admin(interaction)
        if confirmar.strip().upper() != "CONFIRMAR":
            await self._safe_reply(
                interaction,
                embed=self.bot.embeds.warning(
                    "Reset Bloqueado",
                    "Para resetar o ranking, execute `/top reset` com `confirmar: CONFIRMAR`.",
                ),
            )
            return
        await self.bot.donater_service.reset(interaction.guild, actor)
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.success("Trono Resetado", "O ranking dos patronos foi limpo e sincronizado."),
        )

    def _require_admin(self, interaction: discord.Interaction) -> discord.Member:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Este comando só pode ser usado dentro do servidor oficial.")
        if interaction.guild.id != self.bot.server_map.guild_id():
            raise app_commands.CheckFailure("Este comando é exclusivo da guild oficial de Drakoria.")
        if not self.bot.permission_service.has(interaction.user, "manage_donaters"):
            raise app_commands.CheckFailure("Apenas a administração pode manipular o Trono dos Patronos.")
        return interaction.user

    async def _audit(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        fields: list[tuple[str, str, bool]],
    ) -> None:
        if not interaction.guild:
            return
        channel_id = self.bot.server_map.announcements_log_channel_id() or self.bot.server_map.log_channel("announcements")
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = self.bot.embeds.make(
            title=title,
            description=description,
            color=self.bot.embeds.default_color,
            fields=fields + [("Executor", interaction.user.mention, True)],
            timestamp=True,
        )
        await channel.send(embed=embed)

    async def _safe_defer(self, interaction: discord.Interaction) -> bool:
        if interaction.response.is_done():
            return True
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            return True
        except discord.HTTPException as exc:
            code = getattr(exc, "code", None)
            if code == 40060:
                self.bot.log.warning(
                    "Interacao %s ja estava reconhecida no defer de Top Donaters; continuando execucao.",
                    interaction.id,
                )
                return True
            if code == 10062:
                self.bot.log.warning(
                    "Interacao %s expirou antes do defer de Top Donaters.",
                    interaction.id,
                )
                return False
            raise

    async def _safe_reply(self, interaction: discord.Interaction, *, embed: discord.Embed) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as exc:
            code = getattr(exc, "code", None)
            if code == 40060:
                try:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                except discord.HTTPException as followup_exc:
                    if getattr(followup_exc, "code", None) == 10062:
                        self.bot.log.warning("Interacao %s expirou antes do followup de Top Donaters.", interaction.id)
                        return
                    raise
                return
            if code == 10062:
                self.bot.log.warning("Interacao %s expirou antes da resposta final de Top Donaters.", interaction.id)
                return
            raise

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        try:
            embed = self.bot.embeds.error("Falha no Trono dos Patronos", str(getattr(error, "original", error)))
            await self._safe_reply(interaction, embed=embed)
        except discord.HTTPException:
            self.bot.log.warning("Não foi possível responder erro de Top Donaters para interaction %s", interaction.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TopDonatersCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))
