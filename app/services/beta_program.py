from __future__ import annotations

import asyncio
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass(slots=True)
class BetaStartResult:
    status: str
    application_id: int | None
    detail: str


class BetaProgramService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._application_locks: dict[int, asyncio.Lock] = {}
        self._brand_logo_cache: dict[str, Image.Image] = {}

    def panel_enabled(self) -> bool:
        return self.bot.server_map.beta_program_enabled()

    def build_panel_embed(self, guild: discord.Guild | None) -> discord.Embed:
        description = (
            "O Drakoria está em fase ativa de beta teste, e buscamos membros comprometidos para contribuir "
            "diretamente com a evolução do projeto.\n\n"
            "Como Beta Tester, você ajudará a validar sistemas, identificar falhas, testar equilíbrio de experiência "
            "e produzir feedback técnico útil para a equipe.\n\n"
            "Você também terá acesso a recompensas exclusivas, como um cupom de 15% de desconto na nossa loja oficial, além de uma carteirinha digital personalizada e um cargo especial no servidor.\n\n"
            "Se deseja participar oficialmente do programa, envie sua candidatura no botão abaixo. 🙂"
        )
        embed = self.bot.embeds.make(
            title="🚧 Programa Oficial de Beta Testers",
            description=description,
            fields=[
                ("Canal de candidaturas", f"<#{self.bot.server_map.beta_program_application_channel_id()}>", True),
                ("Canal de carteirinhas", f"<#{self.bot.server_map.beta_program_card_channel_id()}>", True),
                ("Cargo do programa", f"<@&{self.bot.server_map.beta_program_role_id()}>", False),
            ],
        )
        footer_icon = self.bot.embeds.footer_icon or self.bot.embeds.guild_icon_url
        if footer_icon:
            embed.set_footer(text="Drakoria | Programa Beta", icon_url=footer_icon)
        else:
            embed.set_footer(text="Drakoria | Programa Beta")
        return embed

    async def publish_panel(self, guild: discord.Guild, actor: discord.Member | None = None) -> discord.Message:
        if not self.panel_enabled():
            raise RuntimeError("O módulo beta_program está desabilitado na configuração.")
        channel_id = self.bot.server_map.beta_program_panel_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal do painel beta não encontrado. Revise beta_program.panel_channel_id.")

        state = await self.bot.db.get_beta_program_panel_message(guild.id)
        message: discord.Message | None = None
        embed = self.build_panel_embed(guild)
        if state:
            saved_channel = guild.get_channel(int(state["channel_id"]))
            if isinstance(saved_channel, discord.TextChannel):
                try:
                    message = await saved_channel.fetch_message(int(state["message_id"]))
                    await message.edit(embed=embed, view=self.bot.view_factory.build_beta_program_panel_view())
                except discord.NotFound:
                    message = None

        if message is None:
            message = await channel.send(embed=embed, view=self.bot.view_factory.build_beta_program_panel_view())
        await self.bot.db.save_beta_program_panel_message(guild.id, channel.id, message.id)

        if actor is not None:
            await self._dispatch_log(
                title="Painel Beta Publicado",
                description=f"{actor.mention} publicou/sincronizou o painel do Programa Beta.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Canal", channel.mention, True),
                    ("Mensagem", f"indisponível", True),
                    ("Horário", self._now_human(), True),
                ],
            )
        return message

    async def start_or_resume_application(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> BetaStartResult:
        if interaction.guild is None or interaction.guild.id != self.bot.server_map.guild_id():
            raise RuntimeError("Este fluxo só pode ser usado no servidor oficial.")
        if member.bot:
            raise RuntimeError("Bots não podem enviar candidatura para o Programa Beta.")
        if not self.panel_enabled():
            raise RuntimeError("Programa Beta desabilitado no momento.")

        async with self._member_lock(member.id):
            latest = await self.bot.db.get_latest_beta_tester_application(interaction.guild.id, member.id)
            if latest:
                status = str(latest.get("status", ""))
                if status == "approved":
                    return BetaStartResult(
                        status="already_approved",
                        application_id=int(latest["id"]),
                        detail="Você já foi aprovado no Programa de Beta Testers.",
                    )
                if status in {"in_progress", "pending"}:
                    if status == "pending":
                        return BetaStartResult(
                            status="already_pending",
                            application_id=int(latest["id"]),
                            detail="Sua candidatura já foi enviada e aguarda avaliação da equipe.",
                        )
                    return BetaStartResult(
                        status="resume",
                        application_id=int(latest["id"]),
                        detail="Há uma candidatura em andamento para continuar.",
                    )
                if status == "rejected" and not self.bot.server_map.beta_program_allow_reapply_after_rejection():
                    return BetaStartResult(
                        status="blocked_reapply",
                        application_id=int(latest["id"]),
                        detail="No momento, não está habilitado novo envio após reprovação.",
                    )

            application_id = await self.bot.db.create_beta_tester_application(
                interaction.guild.id,
                member.id,
                panel_channel_id=interaction.channel_id,
                panel_message_id=interaction.message.id if interaction.message else None,
                status="in_progress",
            )
            await self._dispatch_log(
                title="Candidatura Beta Iniciada",
                description=f"{member.mention} iniciou candidatura do Programa Beta.",
                color=self.bot.embeds.default_color,
                fields=[
                    ("Usuário", f"{member}", False),
                    ("Candidatura", f"indisponível", True),
                    ("Horário", self._now_human(), True),
                ],
            )
            return BetaStartResult(
                status="started",
                application_id=application_id,
                detail="Candidatura iniciada com sucesso.",
            )

    async def save_step_answers(self, application_id: int, step: str, answers: dict[str, str]) -> None:
        application = await self.bot.db.get_beta_tester_application(application_id)
        if not application:
            raise RuntimeError("Candidatura não encontrada.")
        if str(application.get("status")) != "in_progress":
            raise RuntimeError("A candidatura não está mais em edição.")
        current_answers = json.loads(application.get("answers_json") or "{}")
        current_answers.update({key: value.strip()[:1500] for key, value in answers.items()})
        await self.bot.db.set_beta_tester_application_answers(application_id, answers=current_answers, last_step=step)

    async def submit_application(self, guild: discord.Guild, member: discord.Member, application_id: int) -> None:
        application = await self.bot.db.get_beta_tester_application(application_id)
        if not application:
            raise RuntimeError("Candidatura não localizada para envio.")
        if str(application.get("status")) != "in_progress":
            raise RuntimeError("Esta candidatura não está disponível para envio.")
        answers = json.loads(application.get("answers_json") or "{}")
        missing = [key for key in self.question_keys() if not str(answers.get(key, "")).strip()]
        if missing:
            raise RuntimeError("Ainda existem respostas obrigatórias não preenchidas.")

        channel_id = self.bot.server_map.beta_program_application_channel_id()
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Canal de candidaturas beta não encontrado.")

        await self.bot.db.update_beta_tester_application(
            application_id,
            {
                "status": "pending",
                "submitted_at": datetime.now(UTC).isoformat(),
                "application_channel_id": channel.id,
                "last_step": "submitted",
                "last_error": None,
            },
        )
        refreshed = await self.bot.db.get_beta_tester_application(application_id)
        embed = self.build_application_embed(member, refreshed, answers)
        message = await channel.send(embed=embed, view=self.bot.view_factory.build_beta_application_review_view(application_id))
        await self.bot.db.update_beta_tester_application(application_id, {"application_message_id": message.id})

        await self._dispatch_log(
            title="Candidatura Beta Enviada",
            description=f"{member.mention} enviou candidatura para avaliação da equipe.",
            color=self.bot.embeds.default_color,
            fields=[
                ("Candidatura", f"indisponível", True),
                ("Canal", channel.mention, True),
                ("Mensagem", f"indisponível", True),
            ],
        )

    async def approve_application(self, interaction: discord.Interaction, application_id: int) -> str:
        async with self._application_lock(application_id):
            application = await self.bot.db.get_beta_tester_application(application_id)
            if not application:
                raise RuntimeError("Candidatura não encontrada.")
            if str(application.get("status")) != "pending":
                raise RuntimeError("Esta candidatura já foi processada.")
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                raise RuntimeError("Contexto inválido para aprovação.")

            member = interaction.guild.get_member(int(application["user_id"]))
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(int(application["user_id"]))
                except discord.HTTPException:
                    raise RuntimeError("Membro da candidatura não foi encontrado no servidor.")

            beta_role = interaction.guild.get_role(self.bot.server_map.beta_program_role_id() or 0)
            if beta_role is None:
                raise RuntimeError("Cargo beta tester não foi encontrado.")

            role_applied = beta_role in member.roles
            if not role_applied:
                await member.add_roles(beta_role, reason=f"Aprovado no Programa Beta por {interaction.user}")
                role_applied = True

            card_payload: bytes | None = None
            card_filename: str = f"drakoria-beta-card-{member.id}.png"
            card_generated = False
            if self.bot.server_map.beta_program_generate_tester_card():
                card_payload, card_filename = await self.generate_tester_card(member, application_id)
                card_generated = True

            card_sent_dm = False
            dm_status = "não_tentado"
            if self.bot.server_map.beta_program_send_dm_on_approval():
                dm_embed = self.bot.embeds.success(
                    "Você foi aprovado no Programa de Beta Testers",
                    (
                        "Sua candidatura ao Programa de Beta Testers do Drakoria foi aprovada.\n\n"
                        "Agora você integra oficialmente o grupo de testers e poderá contribuir com validações, "
                        "reportes e evolução técnica do servidor."
                    ),
                )
                try:
                    files = [discord.File(io.BytesIO(card_payload), filename=card_filename)] if card_payload else []
                    await member.send(embed=dm_embed, files=files)
                    card_sent_dm = card_payload is not None
                    dm_status = "enviado"
                except discord.HTTPException:
                    dm_status = "falhou"

            card_sent_channel = False
            if card_payload is not None:
                card_channel_id = self.bot.server_map.beta_program_card_channel_id()
                card_channel = interaction.guild.get_channel(card_channel_id) if card_channel_id else None
                if isinstance(card_channel, discord.TextChannel):
                    channel_embed = self.bot.embeds.make(
                        title="Carteirinha Oficial Emitida",
                        description=f"{member.mention} foi aprovado no Programa de Beta Testers.",
                        fields=[
                            ("Candidatura", f"indisponível", True),
                            ("Aprovado por", interaction.user.mention, True),
                            ("Data", self._now_human(), False),
                        ],
                    )
                    await card_channel.send(
                        embed=channel_embed,
                        file=discord.File(io.BytesIO(card_payload), filename=card_filename),
                    )
                    card_sent_channel = True

            await self.bot.db.update_beta_tester_application(
                application_id,
                {
                    "status": "approved",
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewed_by_id": interaction.user.id,
                    "review_result": "approved",
                    "rejection_reason": None,
                    "role_applied": int(role_applied),
                    "card_generated": int(card_generated),
                    "card_sent_dm": int(card_sent_dm),
                    "card_sent_channel": int(card_sent_channel),
                    "last_step": "reviewed",
                    "last_error": None,
                },
            )
            await self.refresh_application_message(interaction.guild, application_id)
            await self._dispatch_log(
                title="Candidatura Beta Aprovada",
                description=f"{member.mention} foi aprovado no Programa Beta por {interaction.user.mention}.",
                color=self.bot.embeds.success_color,
                fields=[
                    ("Candidatura", f"indisponível", True),
                    ("Cargo aplicado", f"{beta_role.mention}", False),
                    ("DM", dm_status, True),
                    ("Carteirinha canal", "enviada" if card_sent_channel else "não enviada", True),
                ],
            )
            return "Aprovação registrada com sucesso."

    async def reject_application(
        self,
        interaction: discord.Interaction,
        application_id: int,
        reason: str,
    ) -> str:
        async with self._application_lock(application_id):
            application = await self.bot.db.get_beta_tester_application(application_id)
            if not application:
                raise RuntimeError("Candidatura não encontrada.")
            if str(application.get("status")) != "pending":
                raise RuntimeError("Esta candidatura já foi processada.")
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                raise RuntimeError("Contexto inválido para reprovação.")

            await self.bot.db.update_beta_tester_application(
                application_id,
                {
                    "status": "rejected",
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewed_by_id": interaction.user.id,
                    "review_result": "rejected",
                    "rejection_reason": reason[:500],
                    "last_step": "reviewed",
                    "last_error": None,
                },
            )
            member = interaction.guild.get_member(int(application["user_id"]))
            if member and self.bot.server_map.beta_program_send_dm_on_rejection():
                rejection_embed = self.bot.embeds.make(
                    title="Atualização sobre sua candidatura",
                    description=(
                        "Agradecemos pelo interesse em participar do Programa de Beta Testers do Drakoria.\n\n"
                        "Neste momento, sua candidatura não foi aprovada. Valorizamos seu interesse em contribuir "
                        "e novas oportunidades podem surgir nas próximas fases do projeto."
                    ),
                    fields=[("Motivo informado", reason[:1000], False)],
                )
                try:
                    await member.send(embed=rejection_embed)
                except discord.HTTPException:
                    pass

            await self.refresh_application_message(interaction.guild, application_id)
            await self._dispatch_log(
                title="Candidatura Beta Reprovada",
                description=f"Candidatura indisponível foi reprovada por {interaction.user.mention}.",
                color=self.bot.embeds.warning_color,
                fields=[
                    ("Motivo", reason[:1000], False),
                    ("Horário", self._now_human(), True),
                ],
            )
            return "Reprovação registrada com sucesso."

    async def refresh_application_message(self, guild: discord.Guild, application_id: int) -> None:
        application = await self.bot.db.get_beta_tester_application(application_id)
        if not application:
            return
        channel_id = application.get("application_channel_id")
        message_id = application.get("application_message_id")
        if not channel_id or not message_id:
            return
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(message_id))
        except discord.HTTPException:
            return
        member = guild.get_member(int(application["user_id"]))
        answers = json.loads(application.get("answers_json") or "{}")
        embed = self.build_application_embed(member, application, answers)
        view = self.bot.view_factory.build_beta_application_review_view(application_id) if application.get("status") == "pending" else None
        await message.edit(embed=embed, view=view)

    async def generate_tester_card(self, member: discord.Member, application_id: int) -> tuple[bytes, str]:
        width, height = 1500, 900
        issued_at = datetime.now(UTC)
        issued_label = issued_at.strftime("%d/%m/%Y %H:%M UTC")
        joined_label = (
            member.joined_at.astimezone(UTC).strftime("%d/%m/%Y")
            if member.joined_at is not None
            else "-"
        )
        protocol = f"BT-{application_id:06d}"
        auth_code = self._card_auth_code(member.id, application_id)

        card = Image.new("RGBA", (width, height), (7, 6, 14, 255))
        draw = ImageDraw.Draw(card)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(6 + (24 - 6) * ratio)
            g = int(6 + (10 - 6) * ratio)
            b = int(14 + (46 - 14) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((width - 640, -220, width + 260, 640), fill=(132, 70, 188, 95))
        glow_draw.ellipse((-360, 430, 560, 1160), fill=(244, 198, 77, 42))
        card = Image.alpha_composite(card, glow)
        draw = ImageDraw.Draw(card)

        for x in range(-height, width, 36):
            draw.line((x, 0, x + height, height), fill=(236, 194, 74, 14), width=1)

        outer = (22, 22, width - 22, height - 22)
        inner = (44, 44, width - 44, height - 44)
        header = (70, 70, width - 70, 198)
        content_top = header[3] + 18
        left_panel = (84, content_top, 484, 822)
        right_panel = (504, content_top, width - 84, 822)

        draw.rounded_rectangle(outer, radius=36, fill=(10, 8, 18, 228), outline=(236, 194, 74, 255), width=4)
        draw.rounded_rectangle(inner, radius=30, outline=(131, 77, 192, 185), width=2)
        draw.rounded_rectangle(header, radius=22, fill=(25, 14, 44, 240), outline=(228, 188, 75, 190), width=2)
        draw.rounded_rectangle(left_panel, radius=30, fill=(19, 11, 36, 244), outline=(236, 194, 74, 220), width=3)
        draw.rounded_rectangle(right_panel, radius=30, fill=(15, 10, 30, 238), outline=(131, 77, 192, 210), width=2)

        section_font = self._load_font(20, bold=False)
        small_font = self._load_font(19, bold=False)
        code_font = self._load_font(22, bold=True)
        status_font = self._load_font(31, bold=True)

        logo = await self._load_brand_logo_image()
        emblem_frame: tuple[int, int, int, int] | None = None
        if logo is not None:
            watermark_size = 300
            watermark = ImageOps.fit(logo, (watermark_size, watermark_size), method=Image.Resampling.LANCZOS)
            watermark.putalpha(28)
            watermark_x = right_panel[2] - watermark_size - 52
            watermark_y = right_panel[1] + 110
            card.paste(watermark, (watermark_x, watermark_y), watermark)

            emblem_size = 100
            emblem = ImageOps.fit(logo, (emblem_size, emblem_size), method=Image.Resampling.LANCZOS)
            emblem_frame_size = emblem_size + 24
            emblem_margin_right = 26
            emblem_margin_top = 22
            frame_x2 = inner[2] - emblem_margin_right
            frame_y1 = inner[1] + emblem_margin_top
            emblem_frame = (
                frame_x2 - emblem_frame_size,
                frame_y1,
                frame_x2,
                frame_y1 + emblem_frame_size,
            )
            emblem_x = emblem_frame[0] + 12
            emblem_y = emblem_frame[1] + 12
            draw.rounded_rectangle(
                emblem_frame,
                radius=22,
                fill=(20, 11, 36, 244),
                outline=(236, 194, 74, 230),
                width=3,
            )
            card.paste(emblem, (emblem_x, emblem_y), emblem)

        title = "CARTEIRINHA OFICIAL BETA TESTER"
        subtitle = "Drakoria | Nexar | Programa de Validacao Tecnica"
        title_left = header[0] + 26
        title_right = (emblem_frame[0] - 24) if emblem_frame else (header[2] - 26)
        title_max_width = max(220, title_right - title_left)
        title_font = self._fit_text_font(draw, title, max_width=title_max_width, preferred_size=48, min_size=36, bold=True)
        subtitle_font = self._fit_text_font(draw, subtitle, max_width=title_max_width, preferred_size=24, min_size=18, bold=False)
        title_h = self._text_dimensions(draw, title, title_font)[1]
        subtitle_h = self._text_dimensions(draw, subtitle, subtitle_font)[1]
        title_y = header[1] + 20
        subtitle_y = title_y + title_h + 20
        draw.text((title_left, title_y), title, fill=(250, 224, 145, 255), font=title_font)
        draw.text((title_left, subtitle_y), subtitle, fill=(194, 154, 245, 255), font=subtitle_font)
        line_y = subtitle_y + subtitle_h + 14
        draw.line((title_left, line_y, title_right, line_y), fill=(232, 191, 82, 205), width=2)

        left_title = "IDENTIDADE DO TESTER"
        left_title_font = self._fit_text_font(
            draw,
            left_title,
            max_width=(left_panel[2] - left_panel[0] - 36),
            preferred_size=20,
            min_size=16,
            bold=False,
        )
        left_title_w, left_title_h = self._text_dimensions(draw, left_title, left_title_font)
        left_title_x = left_panel[0] + ((left_panel[2] - left_panel[0]) - left_title_w) // 2
        left_title_y = left_panel[1] + 24
        draw.text((left_title_x, left_title_y), left_title, fill=(228, 194, 108, 255), font=left_title_font)

        avatar_size = 252
        avatar_x = left_panel[0] + (left_panel[2] - left_panel[0] - avatar_size) // 2
        protocol_box = (left_panel[0] + 24, left_panel[3] - 212, left_panel[2] - 24, left_panel[3] - 24)
        avatar_area_top = left_title_y + left_title_h + 22
        avatar_area_bottom = protocol_box[1] - 20
        avatar_y = avatar_area_top + max(0, (avatar_area_bottom - avatar_area_top - avatar_size) // 2)
        draw.ellipse((avatar_x - 12, avatar_y - 12, avatar_x + avatar_size + 12, avatar_y + avatar_size + 12), fill=(11, 8, 22, 236))
        draw.ellipse((avatar_x - 14, avatar_y - 14, avatar_x + avatar_size + 14, avatar_y + avatar_size + 14), outline=(236, 194, 74, 245), width=4)

        avatar_asset = member.display_avatar.replace(format="png", size=512)
        avatar = Image.new("RGBA", (avatar_size, avatar_size), (48, 66, 104, 255))
        try:
            avatar_bytes = await avatar_asset.read()
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar = ImageOps.fit(avatar, (avatar_size, avatar_size), method=Image.Resampling.LANCZOS)
        except Exception:
            pass

        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)
        avatar_circle = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
        avatar_circle.paste(avatar, (0, 0), mask)
        card.paste(avatar_circle, (avatar_x, avatar_y), avatar_circle)

        draw.rounded_rectangle(protocol_box, radius=18, fill=(12, 8, 24, 242), outline=(131, 77, 192, 205), width=2)
        px = protocol_box[0] + 18
        draw.text((px, protocol_box[1] + 14), "PROTOCOLO", fill=(226, 190, 100, 255), font=section_font)
        draw.text((px, protocol_box[1] + 42), protocol, fill=(250, 224, 145, 255), font=code_font)
        draw.text((px, protocol_box[1] + 86), "CODIGO", fill=(226, 190, 100, 255), font=section_font)
        draw.text((px, protocol_box[1] + 114), auth_code, fill=(212, 180, 248, 255), font=small_font)

        rx0, ry0, rx1, ry1 = right_panel
        content_pad = 34
        name_label_y = ry0 + 24
        draw.text((rx0 + content_pad, name_label_y), "PORTADOR", fill=(226, 190, 100, 255), font=section_font)
        name_text = self._truncate_text(member.display_name, 34)
        name_max_width = rx1 - rx0 - (content_pad * 2)
        name_font = self._fit_text_font(draw, name_text, max_width=name_max_width, preferred_size=46, min_size=34, bold=True)
        _, name_h = self._text_dimensions(draw, name_text, name_font)
        name_y = name_label_y + 28
        draw.text((rx0 + content_pad, name_y), name_text, fill=(252, 241, 214, 255), font=name_font)

        grid_top = name_y + name_h + 28
        column_gap = 48
        column_width = (rx1 - rx0 - (content_pad * 2) - column_gap) // 2
        left_col_x = rx0 + content_pad
        right_col_x = left_col_x + column_width + column_gap
        row_gap = 94
        field_label_font = section_font

        def draw_field(x: int, y: int, label: str, value: str) -> None:
            draw.text((x, y), label, fill=(218, 183, 96, 255), font=field_label_font)
            value_font_fit = self._fit_text_font(
                draw,
                value,
                max_width=column_width,
                preferred_size=30,
                min_size=22,
                bold=False,
            )
            draw.text((x, y + 30), value, fill=(218, 186, 248, 255), font=value_font_fit)

        draw_field(left_col_x, grid_top, "USUARIO DISCORD", self._truncate_text(str(member), 34))
        draw_field(right_col_x, grid_top, "EMISSAO", issued_label)
        draw_field(left_col_x, grid_top + row_gap, "ID DISCORD", str(member.id))
        draw_field(right_col_x, grid_top + row_gap, "INGRESSO NO SERVIDOR", joined_label)
        draw_field(left_col_x, grid_top + (row_gap * 2), "PROTOCOLO", protocol)
        draw_field(right_col_x, grid_top + (row_gap * 2), "CODIGO DE AUTENTICACAO", auth_code)

        status_box = (rx0 + content_pad, ry1 - 180, rx1 - content_pad, ry1 - 110)
        draw.rounded_rectangle(status_box, radius=20, fill=(67, 30, 112, 246), outline=(236, 194, 74, 255), width=3)
        status_text = "STATUS OPERACIONAL: APROVADO COMO BETA TESTER"
        status_w, status_h = self._text_dimensions(draw, status_text, status_font)
        status_x = status_box[0] + ((status_box[2] - status_box[0]) - status_w) // 2
        status_y = status_box[1] + ((status_box[3] - status_box[1]) - status_h) // 2
        draw.text((status_x, status_y), status_text, fill=(250, 224, 145, 255), font=status_font)

        security_box = (rx0 + content_pad, ry1 - 98, rx1 - content_pad, ry1 - 28)
        draw.rounded_rectangle(security_box, radius=18, fill=(10, 7, 20, 246), outline=(131, 77, 192, 220), width=2)
        security_line_1 = f"AUTENTICACAO DIGITAL: {auth_code}"
        security_line_2 = "Documento oficial do Programa Beta Drakoria. Uso interno de validacao."
        draw.text((security_box[0] + 20, security_box[1] + 12), security_line_1, fill=(250, 224, 145, 255), font=code_font)
        draw.text((security_box[0] + 20, security_box[1] + 40), security_line_2, fill=(204, 170, 244, 255), font=small_font)

        out = io.BytesIO()
        card.convert("RGB").save(out, format="PNG", optimize=True)
        out.seek(0)
        return out.getvalue(), f"drakoria-beta-card-{member.id}.png"

    @staticmethod
    def _card_auth_code(member_id: int, application_id: int) -> str:
        payload = f"{member_id}:{application_id}".encode("utf-8")
        digest = hashlib.sha1(payload).hexdigest()[:10].upper()
        return f"DRK-{application_id:06d}-{digest}"

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        value = text.strip()
        if len(value) <= max_chars:
            return value
        if max_chars <= 3:
            return value[:max_chars]
        return value[: max_chars - 3].rstrip() + "..."

    def _fit_text_font(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        max_width: int,
        preferred_size: int,
        min_size: int,
        bold: bool,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        size = preferred_size
        while size >= min_size:
            font = self._load_font(size, bold=bold)
            width, _ = self._text_dimensions(draw, text, font)
            if width <= max_width:
                return font
            size -= 1
        return self._load_font(min_size, bold=bold)

    @staticmethod
    def _text_dimensions(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> tuple[int, int]:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top

    async def _load_brand_logo_image(self) -> Image.Image | None:
        logo_url = self._brand_logo_url()
        if not logo_url:
            return None
        cached = self._brand_logo_cache.get(logo_url)
        if cached is not None:
            return cached.copy()
        logo_bytes = await asyncio.to_thread(self._download_logo_bytes, logo_url)
        if not logo_bytes:
            return None
        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        except OSError:
            return None
        self._brand_logo_cache[logo_url] = logo
        return logo.copy()

    def _brand_logo_url(self) -> str | None:
        style = self.bot.server_map.style()
        for key in ("logo_url", "thumbnail_url", "brand_logo_url", "footer_icon_url"):
            value = style.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return self.bot.server_map.announcements_logo_url()

    def _download_logo_bytes(self, logo_url: str) -> bytes | None:
        if logo_url.startswith(("http://", "https://")):
            request = Request(
                logo_url,
                headers={"User-Agent": "DrakoriaBot/1.0"},
            )
            try:
                with urlopen(request, timeout=8) as response:
                    return response.read()
            except Exception:
                return None

        local_path = self._resolve_local_logo_path(logo_url)
        if local_path is None:
            return None
        try:
            return local_path.read_bytes()
        except OSError:
            return None

    def _resolve_local_logo_path(self, logo_url: str) -> Path | None:
        candidate = Path(logo_url.strip())
        if candidate.is_absolute():
            return candidate if candidate.exists() else None

        base_dirs: list[Path] = [Path.cwd()]
        runtime_config = getattr(getattr(self.bot, "runtime", None), "config_path", None)
        if isinstance(runtime_config, Path):
            base_dirs.extend([runtime_config.parent, runtime_config.parent.parent])

        for base in base_dirs:
            try:
                resolved = (base / candidate).resolve()
            except OSError:
                continue
            if resolved.exists():
                return resolved
        return None

    @staticmethod
    def _load_font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = []
        if bold:
            candidates.extend(["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"])
        else:
            candidates.extend(["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
        for font_path in candidates:
            try:
                return ImageFont.truetype(font_path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def build_application_embed(
        self,
        member: discord.Member | None,
        application: dict[str, Any],
        answers: dict[str, str],
    ) -> discord.Embed:
        status = str(application.get("status", "unknown"))
        reviewer = application.get("reviewed_by_id")
        description = (
            f"Candidatura oficial do Programa Beta.\n"
            f"Status atual: **{status.upper()}**"
        )
        embed = self.bot.embeds.make(
            title=f"Candidatura Beta ",
            description=description,
            fields=[
                ("Usuário", f"{member.mention if member else f'<@{application['user_id']}>'}", False),
                ("Criada em", f"`{application.get('created_at')}`", True),
                ("Enviada em", f"`{application.get('submitted_at') or '-'}`", True),
                ("Revisada por", f"<@{reviewer}>" if reviewer else "-", True),
            ],
        )
        for key, label in self.questions():
            value = str(answers.get(key, "-")).strip() or "-"
            embed.add_field(name=label[:256], value=value[:1024], inline=False)
        if application.get("rejection_reason"):
            embed.add_field(name="Motivo da Reprovação", value=str(application["rejection_reason"])[:1024], inline=False)
        return embed

    async def _dispatch_log(
        self,
        *,
        title: str,
        description: str,
        color: int,
        fields: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        channel_id = self.bot.server_map.beta_program_log_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            self.bot.log.warning("Canal de log beta não encontrado: %s", channel_id)
            return
        embed = self.bot.embeds.make(title=title, description=description, color=color, fields=fields or [])
        embed.timestamp = datetime.now(UTC)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            self.bot.log.warning("Falha ao enviar log beta: %s", exc)

    def _member_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    def _application_lock(self, application_id: int) -> asyncio.Lock:
        if application_id not in self._application_locks:
            self._application_locks[application_id] = asyncio.Lock()
        return self._application_locks[application_id]

    @staticmethod
    def _now_human() -> str:
        now = datetime.now(UTC)
        return f"{discord.utils.format_dt(now, style='F')} | `{now.isoformat()}`"

    @staticmethod
    def questions() -> list[tuple[str, str]]:
        return [
            ("age", "1) Qual é a sua idade?"),
            ("availability", "2) Dias e horários de disponibilidade para testes"),
            ("bug_reaction", "3) Quando encontra bug, o que costuma fazer?"),
            ("detailist_example", "4) Você é detalhista? Cite um exemplo"),
            ("good_tester", "5) O que torna alguém um bom beta tester?"),
            ("critical_failure_report", "6) Como comunicaria uma falha importante?"),
            ("best_test_type", "7) Em qual tipo de teste se sai melhor?"),
            ("consistency_commitment", "8) Consegue manter constância e comprometimento?"),
            ("why_join", "9) Por que quer participar do Programa Beta Drakoria?"),
            ("expected_contribution", "10) Qual contribuição acredita que pode entregar?"),
        ]

    @classmethod
    def question_keys(cls) -> list[str]:
        return [key for key, _ in cls.questions()]




