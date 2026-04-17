from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
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
        width, height = 1400, 820
        issued_at = datetime.now(UTC).strftime("%d/%m/%Y")

        card = Image.new("RGBA", (width, height), (12, 8, 24, 255))
        draw = ImageDraw.Draw(card)
        for i in range(height):
            ratio = i / max(height - 1, 1)
            r = int(14 + (40 - 14) * ratio)
            g = int(10 + (24 - 10) * ratio)
            b = int(30 + (62 - 30) * ratio)
            draw.line([(0, i), (width, i)], fill=(r, g, b, 255))

        draw.rounded_rectangle((26, 26, width - 26, height - 26), radius=34, outline=(227, 194, 110, 255), width=4)
        draw.rounded_rectangle((56, 56, width - 56, height - 56), radius=28, outline=(104, 77, 151, 180), width=2)

        title_font = self._load_font(56, bold=True)
        subtitle_font = self._load_font(30, bold=False)
        label_font = self._load_font(30, bold=False)
        value_font = self._load_font(40, bold=True)
        small_font = self._load_font(24, bold=False)
        badge_font = self._load_font(34, bold=True)

        draw.text((96, 96), "Carteirinha Oficial de Beta Tester", fill=(246, 230, 173, 255), font=title_font)
        draw.text((98, 164), "Programa Beta Drakoria", fill=(191, 170, 233, 255), font=subtitle_font)
        logo = await self._load_brand_logo_image()
        if logo is not None:
            logo_size = 176
            logo = ImageOps.fit(logo, (logo_size, logo_size), method=Image.Resampling.LANCZOS)
            x = width - 100 - logo_size
            y = 92
            badge_bg = Image.new("RGBA", (logo_size + 24, logo_size + 24), (18, 12, 34, 220))
            badge_mask = Image.new("L", badge_bg.size, 0)
            badge_draw = ImageDraw.Draw(badge_mask)
            badge_draw.rounded_rectangle((0, 0, badge_bg.width - 1, badge_bg.height - 1), radius=26, fill=255)
            card.paste(badge_bg, (x - 12, y - 12), badge_mask)
            card.paste(logo, (x, y), logo)
            draw.rounded_rectangle(
                (x - 12, y - 12, x + logo_size + 12, y + logo_size + 12),
                radius=26,
                outline=(228, 193, 113, 220),
                width=3,
            )

        avatar_box = (94, 236, 434, 576)
        draw.rounded_rectangle(avatar_box, radius=40, fill=(33, 22, 55, 255), outline=(228, 193, 113, 255), width=4)
        avatar_asset = member.display_avatar.replace(format="png", size=512)
        avatar_bytes = await avatar_asset.read()
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = ImageOps.fit(avatar, (300, 300), method=Image.Resampling.LANCZOS)
        mask = Image.new("L", (300, 300), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 299, 299), fill=255)
        avatar_circle = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        avatar_circle.paste(avatar, (0, 0), mask)
        card.paste(avatar_circle, (114, 256), avatar_circle)

        draw.text((490, 266), "NOME", fill=(172, 153, 211, 255), font=label_font)
        draw.text((490, 304), member.display_name[:28], fill=(255, 255, 255, 255), font=value_font)
        draw.text((490, 384), "ID DO TESTER", fill=(172, 153, 211, 255), font=label_font)
        draw.text((490, 422), f"APROVADO", fill=(240, 220, 162, 255), font=value_font)
        draw.text((490, 500), "USUÁRIO", fill=(172, 153, 211, 255), font=label_font)
        draw.text((490, 538), str(member)[:28], fill=(227, 223, 238, 255), font=self._load_font(34, bold=False))

        badge_box = (490, 614, 1232, 706)
        draw.rounded_rectangle(badge_box, radius=20, fill=(44, 27, 78, 255), outline=(231, 197, 115, 255), width=3)
        draw.text((522, 644), "STATUS: APROVADO COMO BETA TESTER", fill=(248, 233, 176, 255), font=badge_font)

        draw.text((96, 744), f"Emitido em: {issued_at}", fill=(162, 145, 198, 255), font=small_font)
        draw.text((1038, 744), "Drakoria", fill=(162, 145, 198, 255), font=small_font)

        out = io.BytesIO()
        card.convert("RGB").save(out, format="PNG", optimize=True)
        out.seek(0)
        return out.getvalue(), f"drakoria-beta-card-{member.id}.png"

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

    @staticmethod
    def _download_logo_bytes(logo_url: str) -> bytes | None:
        request = Request(
            logo_url,
            headers={"User-Agent": "DrakoriaBot/1.0"},
        )
        try:
            with urlopen(request, timeout=8) as response:
                return response.read()
        except Exception:
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




