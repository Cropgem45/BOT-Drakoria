from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class AdministrationCog(
    commands.GroupCog,
    group_name="admin",
    group_description="Decretos administrativos de Drakoria",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    def _render_target(label: str, target_id: int | None, target: discord.abc.Snowflake | None) -> str:
        if not target_id:
            return f"`{label}` -> não configurado"
        if target is None:
            return f"`{label}` -> `{target_id}` | ausente"
        name = getattr(target, "name", str(target))
        return f"`{label}` -> `{target_id}` | {name}"

    @app_commands.command(name="server_map", description="Exibe o mapa operacional por ID do servidor")
    @app_commands.guild_only()
    async def server_map(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "view_server_map"):
            raise app_commands.CheckFailure("Não possuis acesso ao mapa do servidor.")
        guild = interaction.guild
        lines = [f"Guild oficial: `{self.bot.server_map.guild_id()}` | {guild.name}", "", "**Canais**"]
        for key, value in self.bot.config.get("channels", {}).items():
            lines.append(self._render_target(key, int(value), guild.get_channel(int(value))))
        lines.extend(["", "**Categorias**"])
        for key, value in self.bot.config.get("categories", {}).items():
            lines.append(self._render_target(key, int(value), guild.get_channel(int(value))))
        lines.extend(["", "**Cargos**"])
        for key, value in self.bot.config.get("roles", {}).items():
            lines.append(self._render_target(key, int(value), guild.get_role(int(value))))
        lines.extend(["", "**Logs**"])
        for key, value in self.bot.config.get("logs", {}).get("channels", {}).items():
            lines.append(self._render_target(key, int(value), guild.get_channel(int(value))))

        lines.extend(["", "**Voice Points**"])
        lines.append(f"`enabled` -> `{self.bot.server_map.voice_points_enabled()}`")
        lines.append(self._render_target("panel_channel_id", self.bot.server_map.voice_point_panel_channel_id(), guild.get_channel(self.bot.server_map.voice_point_panel_channel_id() or 0)))
        lines.append(self._render_target("report_channel_id", self.bot.server_map.voice_point_report_channel_id(), guild.get_channel(self.bot.server_map.voice_point_report_channel_id() or 0)))
        lines.append(self._render_target("log_channel_id", self.bot.server_map.voice_point_log_channel_id(), guild.get_channel(self.bot.server_map.voice_point_log_channel_id() or 0)))
        lines.append("")
        lines.append("**Calls Válidas**")
        for channel_id in self.bot.server_map.voice_point_valid_channel_ids():
            channel = guild.get_channel(channel_id)
            group = self.bot.server_map.voice_point_channel_group(channel_id) or "sem grupo"
            lines.append(f"`voice_channel` -> `{channel_id}` | {getattr(channel, 'name', 'ausente')} | grupo: {group}")

        lines.extend(["", "**Cadastro Inicial (Registrar-se)**"])
        lines.append(f"`enabled` -> `{self.bot.server_map.registration_panel_enabled()}`")
        lines.append(self._render_target("panel_channel_id", self.bot.server_map.registration_panel_channel_id(), guild.get_channel(self.bot.server_map.registration_panel_channel_id() or 0)))
        lines.append(self._render_target("registered_role_id", self.bot.server_map.registration_registered_role_id(), guild.get_role(self.bot.server_map.registration_registered_role_id() or 0)))
        lines.append(self._render_target("visitor_role_id", self.bot.server_map.registration_visitor_role_id(), guild.get_role(self.bot.server_map.registration_visitor_role_id() or 0)))
        lines.append(self._render_target("log_channel_id", self.bot.server_map.registration_log_channel_id(), guild.get_channel(self.bot.server_map.registration_log_channel_id() or 0)))

        lines.extend(["", "**Cadastro Oficial**"])
        lines.append(f"`enabled` -> `{self.bot.server_map.member_registration_enabled()}`")
        lines.append(self._render_target("panel_channel_id", self.bot.server_map.member_registration_panel_channel_id(), guild.get_channel(self.bot.server_map.member_registration_panel_channel_id() or 0)))
        lines.append(self._render_target("member_role_id", self.bot.server_map.member_registration_member_role_id(), guild.get_role(self.bot.server_map.member_registration_member_role_id() or 0)))
        lines.append(self._render_target("log_channel_id", self.bot.server_map.member_registration_log_channel_id(), guild.get_channel(self.bot.server_map.member_registration_log_channel_id() or 0)))

        lines.extend(["", "**Programa Beta**"])
        lines.append(f"`enabled` -> `{self.bot.server_map.beta_program_enabled()}`")
        lines.append(self._render_target("panel_channel_id", self.bot.server_map.beta_program_panel_channel_id(), guild.get_channel(self.bot.server_map.beta_program_panel_channel_id() or 0)))
        lines.append(self._render_target("application_channel_id", self.bot.server_map.beta_program_application_channel_id(), guild.get_channel(self.bot.server_map.beta_program_application_channel_id() or 0)))
        lines.append(self._render_target("card_channel_id", self.bot.server_map.beta_program_card_channel_id(), guild.get_channel(self.bot.server_map.beta_program_card_channel_id() or 0)))
        lines.append(self._render_target("log_channel_id", self.bot.server_map.beta_program_log_channel_id(), guild.get_channel(self.bot.server_map.beta_program_log_channel_id() or 0)))
        lines.append(self._render_target("beta_role_id", self.bot.server_map.beta_program_role_id(), guild.get_role(self.bot.server_map.beta_program_role_id() or 0)))

        lines.extend(["", "**Tickets**"])
        lines.append(self._render_target("panel_channel_id", self.bot.server_map.ticket_panel_channel_id(), guild.get_channel(self.bot.server_map.ticket_panel_channel_id() or 0)))
        lines.append(self._render_target("category_id", self.bot.server_map.ticket_category_id(), guild.get_channel(self.bot.server_map.ticket_category_id() or 0)))
        lines.append(self._render_target("log_channel_id", self.bot.server_map.ticket_log_channel_id(), guild.get_channel(self.bot.server_map.ticket_log_channel_id() or 0)))
        lines.append(self._render_target("transcript_channel_id", self.bot.server_map.ticket_transcript_channel_id(), guild.get_channel(self.bot.server_map.ticket_transcript_channel_id() or 0)))

        await interaction.response.send_message(
            embed=self.bot.embeds.make(
                title="Mapa Operacional de Drakoria",
                description="\n".join(lines),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="healthcheck", description="Audita o estado operacional do bot no servidor")
    @app_commands.guild_only()
    async def healthcheck(self, interaction: discord.Interaction) -> None:
        if not self.bot.permission_service.has(interaction.user, "view_server_map"):
            raise app_commands.CheckFailure("Não possuis autoridade para consultar o healthcheck operacional.")

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild or self.bot.get_guild(self.bot.server_map.guild_id())
        entries = await self.bot.healthcheck_service.run(guild)
        embed = self.bot.healthcheck_service.build_embed(guild, entries)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error("Decreto Recusado", str(error)),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Decreto Recusado", str(error)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdministrationCog(bot), guild=discord.Object(id=bot.server_map.guild_id()))


