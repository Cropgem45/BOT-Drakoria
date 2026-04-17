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

        card = Image.new("RGBA", (width, height), (9, 14, 30, 255))
        draw = ImageDraw.Draw(card)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(10 + (38 - 10) * ratio)
            g = int(14 + (16 - 14) * ratio)
            b = int(35 + (56 - 35) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((width - 640, -220, width + 260, 640), fill=(143, 100, 229, 78))
        glow_draw.ellipse((-300, 420, 540, 1120), fill=(48, 166, 221, 54))
        card = Image.alpha_composite(card, glow)
        draw = ImageDraw.Draw(card)

        for x in range(-height, width, 36):
            draw.line((x, 0, x + height, height), fill=(255, 255, 255, 11), width=1)

        draw.rounded_rectangle((22, 22, width - 22, height - 22), radius=36, fill=(8, 13, 30, 212), outline=(230, 195, 113, 255), width=4)
        draw.rounded_rectangle((44, 44, width - 44, height - 44), radius=30, outline=(92, 139, 213, 155), width=2)
        draw.rounded_rectangle((66, 66, width - 66, 142), radius=22, fill=(17, 27, 53, 235), outline=(224, 190, 110, 155), width=2)

        title_font = self._load_font(48, bold=True)
        subtitle_font = self._load_font(24, bold=False)
        section_font = self._load_font(22, bold=False)
        hero_font = self._load_font(42, bold=True)
        value_font = self._load_font(30, bold=False)
        small_font = self._load_font(22, bold=False)
        status_font = self._load_font(30, bold=True)
        code_font = self._load_font(24, bold=True)

        draw.text((96, 84), "CARTEIRINHA OFICIAL BETA TESTER", fill=(246, 229, 173, 255), font=title_font)
        draw.text((98, 124), "Drakoria | Nexar | Programa de Validacao Tecnica", fill=(167, 208, 255, 255), font=subtitle_font)

        logo = await self._load_brand_logo_image()
        if logo is not None:
            watermark_size = 420
            watermark = ImageOps.fit(logo, (watermark_size, watermark_size), method=Image.Resampling.LANCZOS)
            watermark.putalpha(36)
            card.paste(watermark, (1020, 260), watermark)
            emblem_size = 116
            emblem = ImageOps.fit(logo, (emblem_size, emblem_size), method=Image.Resampling.LANCZOS)
            emblem_x, emblem_y = width - 194, 82
            draw.rounded_rectangle(
                (emblem_x - 14, emblem_y - 14, emblem_x + emblem_size + 14, emblem_y + emblem_size + 14),
                radius=24,
                fill=(13, 21, 43, 240),
                outline=(229, 196, 114, 230),
                width=3,
            )
            card.paste(emblem, (emblem_x, emblem_y), emblem)

        left_panel = (78, 176, 484, 822)
        draw.rounded_rectangle(left_panel, radius=30, fill=(15, 24, 48, 238), outline=(226, 193, 113, 215), width=3)
        draw.text((112, 206), "IDENTIDADE DO TESTER", fill=(178, 214, 255, 255), font=section_font)

        avatar_size = 300
        avatar_x = left_panel[0] + (left_panel[2] - left_panel[0] - avatar_size) // 2
        avatar_y = 262
        draw.ellipse((avatar_x - 12, avatar_y - 12, avatar_x + avatar_size + 12, avatar_y + avatar_size + 12), fill=(6, 11, 26, 230))
        draw.ellipse((avatar_x - 14, avatar_y - 14, avatar_x + avatar_size + 14, avatar_y + avatar_size + 14), outline=(232, 198, 118, 245), width=4)

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

        draw.rounded_rectangle((112, 594, 450, 790), radius=20, fill=(10, 17, 35, 240), outline=(92, 139, 213, 180), width=2)
        draw.text((132, 620), "PROTOCOLO", fill=(163, 195, 241, 255), font=section_font)
        draw.text((132, 652), protocol, fill=(248, 232, 176, 255), font=code_font)
        draw.text((132, 698), "CODIGO", fill=(163, 195, 241, 255), font=section_font)
        draw.text((132, 730), auth_code, fill=(226, 235, 251, 255), font=small_font)

        info_panel = (516, 176, width - 78, 822)
        draw.rounded_rectangle(info_panel, radius=30, fill=(12, 21, 44, 226), outline=(92, 139, 213, 170), width=2)

        draw.text((552, 224), "PORTADOR", fill=(160, 195, 242, 255), font=section_font)
        draw.text((552, 256), self._truncate_text(member.display_name, 28), fill=(255, 255, 255, 255), font=hero_font)

        draw.text((552, 350), "USUARIO DISCORD", fill=(160, 195, 242, 255), font=section_font)
        draw.text((552, 382), self._truncate_text(str(member), 32), fill=(226, 235, 251, 255), font=value_font)

        draw.text((552, 458), "ID DISCORD", fill=(160, 195, 242, 255), font=section_font)
        draw.text((552, 490), str(member.id), fill=(245, 247, 255, 255), font=value_font)

        draw.text((980, 350), "EMISSAO", fill=(160, 195, 242, 255), font=section_font)
        draw.text((980, 382), issued_label, fill=(226, 235, 251, 255), font=value_font)

        draw.text((980, 458), "INGRESSO NO SERVIDOR", fill=(160, 195, 242, 255), font=section_font)
        draw.text((980, 490), joined_label, fill=(245, 247, 255, 255), font=value_font)

        status_box = (552, 588, width - 120, 674)
        draw.rounded_rectangle(status_box, radius=20, fill=(27, 87, 56, 242), outline=(147, 232, 181, 255), width=3)
        draw.text((582, 616), "STATUS OPERACIONAL: APROVADO COMO BETA TESTER", fill=(231, 255, 241, 255), font=status_font)

        security_box = (552, 702, width - 120, 790)
        draw.rounded_rectangle(security_box, radius=18, fill=(8, 14, 31, 240), outline=(227, 193, 113, 180), width=2)
        draw.text((582, 726), f"AUTENTICACAO DIGITAL: {auth_code}", fill=(245, 230, 173, 255), font=code_font)
        draw.text((582, 756), "Documento oficial do Programa Beta Drakoria. Uso interno de validacao.", fill=(174, 206, 250, 255), font=small_font)

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




