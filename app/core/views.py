from __future__ import annotations

from typing import Any

import discord


class ViewFactory:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def register_persistent_views(self) -> None:
        self.bot.registered_persistent_views = {}
        self.bot.add_view(RegistrationPanelView(self.bot))
        self.bot.registered_persistent_views["registration_panel"] = 1
        self.bot.add_view(MemberRegistrationPanelView(self.bot))
        self.bot.registered_persistent_views["member_registration_panel"] = 1
        self.bot.add_view(MemberRegistrationContinueView(self.bot))
        self.bot.registered_persistent_views["member_registration_continue"] = 1
        self.bot.add_view(BetaProgramPanelView(self.bot))
        self.bot.registered_persistent_views["beta_program_panel"] = 1
        self.bot.add_view(BetaProgramContinueView(self.bot))
        self.bot.registered_persistent_views["beta_program_continue"] = 1
        self.bot.add_view(TicketPanelView(self.bot))
        self.bot.registered_persistent_views["ticket_panel"] = 1
        self.bot.add_view(TicketControlView(self.bot))
        self.bot.registered_persistent_views["ticket_controls"] = 1
        self.bot.add_view(VoicePointPanelView(self.bot))
        self.bot.registered_persistent_views["voice_point_panel"] = 1
        beta_review_count = 0
        for application_id in await self.bot.db.list_pending_beta_tester_application_ids(self.bot.server_map.guild_id()):
            self.bot.add_view(BetaApplicationReviewView(self.bot, application_id))
            beta_review_count += 1
        self.bot.registered_persistent_views["beta_program_reviews"] = beta_review_count

    def build_review_view(self, target_user_id: int) -> discord.ui.View:
        return OnboardingReviewView(self.bot, target_user_id)

    def build_registration_panel_view(self) -> discord.ui.View:
        return RegistrationPanelView(self.bot)

    def build_member_registration_panel_view(self) -> discord.ui.View:
        return MemberRegistrationPanelView(self.bot)

    def build_beta_program_panel_view(self) -> discord.ui.View:
        return BetaProgramPanelView(self.bot)

    def build_beta_application_review_view(self, application_id: int) -> discord.ui.View:
        return BetaApplicationReviewView(self.bot, application_id)

    def build_voice_point_panel_view(self) -> discord.ui.View:
        return VoicePointPanelView(self.bot)

    def build_ticket_panel_view(self) -> discord.ui.View:
        return TicketPanelView(self.bot)

    def build_ticket_control_view(self) -> discord.ui.View:
        return TicketControlView(self.bot)


class RegistrationPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Registrar-se",
        emoji="\N{WHITE HEAVY CHECK MARK}",
        style=discord.ButtonStyle.success,
        custom_id="drakoria:registration:panel:start",
    )
    async def register_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Contexto Inválido",
                    "Este painel de registro só pode ser usado por membros dentro do servidor oficial.",
                ),
                ephemeral=True,
            )
            return
        if interaction.guild_id != self.bot.server_map.guild_id():
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Servidor Incorreto",
                    "Este painel não pertence a este servidor. Use o painel oficial de Drakoria.",
                ),
                ephemeral=True,
            )
            return
        if not self.bot.server_map.registration_panel_enabled():
            await interaction.response.send_message(
                embed=self.bot.embeds.warning(
                    "Registro Temporariamente Fechado",
                    "O sistema de registro inicial está desabilitado no momento. Aguarde orientação da administração.",
                ),
                ephemeral=True,
            )
            return

        confirmation_embed = self.bot.registration_service.build_confirmation_embed()
        await interaction.response.send_message(
            embed=confirmation_embed,
            view=RegistrationConfirmationView(self.bot),
            ephemeral=True,
        )


class RegistrationConfirmationView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(
        label="Confirmo leitura e concordância",
        style=discord.ButtonStyle.success,
    )
    async def confirm_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto Inválido", "Não foi possível validar teu contexto no servidor."),
                ephemeral=True,
            )
            return
        try:
            result = await self.bot.registration_service.register_member(interaction, interaction.user)
        except RuntimeError as exc:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha no Registro", str(exc)),
                ephemeral=True,
            )
            return

        if result.status == "already_registered":
            await interaction.response.send_message(
                embed=self.bot.embeds.make(
                    title="Registro Já Concluído",
                    description=result.detail,
                ),
                ephemeral=True,
            )
            return

        details = [f"Cargo aplicado: {result.registered_role.mention if result.registered_role else 'Não informado'}."]
        if result.removed_role:
            details.append(f"Cargo removido: {result.removed_role.mention}.")
        await interaction.response.send_message(
            embed=self.bot.embeds.success(
                "Registro Confirmado",
                "\n".join(details),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=self.bot.embeds.warning(
                "Registro Cancelado",
                "Nenhuma alteração foi aplicada. Quando desejar, volte ao painel e confirme teu registro.",
            ),
            ephemeral=True,
        )


class MemberRegistrationPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Iniciar Cadastro",
        style=discord.ButtonStyle.success,
        custom_id="drakoria:member_registration:panel:start",
    )
    async def start_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Contexto Inválido",
                        "O cadastro oficial só pode ser iniciado dentro do servidor.",
                    ),
                    ephemeral=True,
                )
                return
            if interaction.guild_id != self.bot.server_map.guild_id():
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Servidor Incorreto",
                        "Este painel não pertence ao servidor oficial do cadastro.",
                    ),
                    ephemeral=True,
                )
                return
            if not self.bot.server_map.member_registration_enabled():
                await interaction.response.send_message(
                    embed=self.bot.embeds.warning(
                        "Cadastro Temporariamente Fechado",
                        "O cadastro oficial está desabilitado no momento.",
                    ),
                    ephemeral=True,
                )
                return

            result = await self.bot.member_registration_service.start_session(interaction, interaction.user)
            if result.status == "already_completed":
                await interaction.response.send_message(
                    embed=self.bot.embeds.make(
                        title="Cadastro Já Concluído",
                        description=result.detail,
                    ),
                    ephemeral=True,
                )
                return

            if result.session_id is None:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Sessão Inválida",
                        "Não foi possível criar/retomar tua sessão de cadastro.",
                    ),
                    ephemeral=True,
                )
                return
            session = await self.bot.db.get_member_registration_session(result.session_id)
            last_step = str(session.get("last_step", "started")) if session else "started"
            if last_step in {"started"}:
                await interaction.response.send_modal(MemberRegistrationStepOneModal(self.bot, result.session_id))
                return
            if last_step in {"step_1"}:
                await interaction.response.send_modal(MemberRegistrationStepTwoModal(self.bot, result.session_id))
                return
            if last_step in {"step_2"}:
                await interaction.response.send_modal(MemberRegistrationStepThreeModal(self.bot, result.session_id))
                return
            await interaction.response.send_message(
                embed=self.bot.embeds.warning(
                    "Sessão já finalizada",
                    "Essa sessão de cadastro já foi encerrada. Inicie novamente somente se necessário.",
                ),
                ephemeral=True,
            )
        except RuntimeError as exc:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha ao Iniciar Cadastro", str(exc)),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha ao Iniciar Cadastro", str(exc)),
                    ephemeral=True,
                )
        except Exception as exc:
            self.bot.log.exception("Falha inesperada ao iniciar cadastro", exc_info=exc)
            detail = str(exc).strip()
            if detail:
                detail = detail[:300]
            else:
                detail = "Erro interno inesperado no início do cadastro. Tente novamente em instantes."
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error(
                        "Falha ao Iniciar Cadastro",
                        detail,
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Falha ao Iniciar Cadastro",
                        detail,
                    ),
                    ephemeral=True,
                )


class MemberRegistrationContinueView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Continuar Cadastro",
        style=discord.ButtonStyle.primary,
        custom_id="drakoria:member_registration:continue",
    )
    async def continue_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Contexto Inválido", "Use o cadastro somente dentro do servidor."),
                    ephemeral=True,
                )
                return
            latest = await self.bot.db.get_latest_member_registration_session(interaction.guild_id, interaction.user.id)
            if not latest or str(latest.get("status")) != "in_progress":
                await interaction.response.send_message(
                    embed=self.bot.embeds.warning(
                        "Sem Cadastro em Andamento",
                        "Não existe sessão de cadastro ativa para continuar.",
                    ),
                    ephemeral=True,
                )
                return
            session_id = int(latest["id"])
            last_step = str(latest.get("last_step") or "started")
            if last_step in {"started"}:
                await interaction.response.send_modal(MemberRegistrationStepOneModal(self.bot, session_id))
                return
            if last_step in {"step_1"}:
                await interaction.response.send_modal(MemberRegistrationStepTwoModal(self.bot, session_id))
                return
            if last_step in {"step_2"}:
                await interaction.response.send_modal(MemberRegistrationStepThreeModal(self.bot, session_id))
                return
            await interaction.response.send_message(
                embed=self.bot.embeds.warning(
                    "Sessão Encerrada",
                    "Essa sessão já foi finalizada. Inicie novo cadastro apenas se necessário.",
                ),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha ao continuar cadastro por botao persistente", exc_info=exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error(
                        "Falha ao Continuar Cadastro",
                        "Ocorreu um erro interno ao abrir a próxima etapa. Tente novamente em instantes.",
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Falha ao Continuar Cadastro",
                        "Ocorreu um erro interno ao abrir a próxima etapa. Tente novamente em instantes.",
                    ),
                    ephemeral=True,
                )


class MemberRegistrationStepOneModal(discord.ui.Modal, title="Cadastro Oficial Drakoria | Etapa 1/3"):
    age = discord.ui.TextInput(
        label="1) Qual é a sua idade?",
        placeholder="Exemplo: 21",
        max_length=2,
        required=True,
    )
    game_nick = discord.ui.TextInput(
        label="2) Qual será seu nick no Drakoria?",
        placeholder="Exemplo: Arthur Monteiro",
        max_length=32,
        required=True,
    )
    how_found = discord.ui.TextInput(
        label="3) Como você conheceu o Drakoria?",
        placeholder="Exemplo: Amigos, TikTok, YouTube, Discord...",
        max_length=120,
        required=True,
    )
    prior_rpg = discord.ui.TextInput(
        label="4) Você já jogou RPG antes?",
        placeholder="Exemplo: Sim, em outros servidores / Não",
        max_length=120,
        required=True,
    )

    def __init__(self, bot: Any, session_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Contexto Inválido", "Este modal só funciona dentro do servidor."),
                    ephemeral=True,
                )
                return
            try:
                age = int(self.age.value.strip())
            except ValueError:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Idade Inválida", "Informe a idade usando apenas números."),
                    ephemeral=True,
                )
                return
            await self.bot.member_registration_service.save_step_one(
                self.session_id,
                age=age,
                game_nick=self.game_nick.value,
                how_found_drakoria=self.how_found.value,
                prior_rpg_experience=self.prior_rpg.value,
            )
            await interaction.response.send_message(
                embed=self.bot.embeds.success(
                    "Etapa 1 Concluída",
                    "Suas respostas iniciais foram registradas. Clique em continuar cadastro.",
                ),
                view=MemberRegistrationContinueView(self.bot),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha na Etapa 1", str(exc)),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha inesperada na etapa 1 do cadastro", exc_info=exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha na Etapa 1", "Erro interno inesperado. Tente novamente."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha na Etapa 1", "Erro interno inesperado. Tente novamente."),
                    ephemeral=True,
                )


class MemberRegistrationStepTwoModal(discord.ui.Modal, title="Cadastro Oficial Drakoria | Etapa 2/3"):
    weekly_availability = discord.ui.TextInput(
        label="5) Qual estilo de gameplay você mais curte?",
        placeholder="Exemplo: PvP, exploração, economia, missões, roleplay...",
        max_length=120,
        required=True,
    )
    interest_area = discord.ui.TextInput(
        label="6) Qual classe você prefere no jogo?",
        placeholder="Exemplo: Arqueiro, mago, guerreiro, ladino, suporte...",
        max_length=120,
        required=True,
    )
    what_called_attention = discord.ui.TextInput(
        label="7) O que mais te chamou atenção no Drakoria?",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
    )
    rules_confirmation = discord.ui.TextInput(
        label="8) Confirma leitura das regras principais?",
        placeholder="Responda: SIM",
        max_length=20,
        required=True,
    )

    def __init__(self, bot: Any, session_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Contexto Inválido", "Este modal só funciona dentro do servidor."),
                    ephemeral=True,
                )
                return
            if self.rules_confirmation.value.strip().lower() not in {"sim", "confirmo", "ok", "li e confirmo"}:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Confirmação Inválida",
                        "Para continuar, confirme explicitamente que leu as regras respondendo `SIM`.",
                    ),
                    ephemeral=True,
                )
                return
            await self.bot.member_registration_service.save_step_two(
                self.session_id,
                weekly_availability=self.weekly_availability.value,
                interest_area=self.interest_area.value,
                what_called_attention=self.what_called_attention.value,
                rules_confirmation=self.rules_confirmation.value,
            )
            await interaction.response.send_message(
                embed=self.bot.embeds.success(
                    "Etapa 2 concluída",
                    "Excelente. Clique em continuar cadastro para finalizar.",
                ),
                view=MemberRegistrationContinueView(self.bot),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha na Etapa 2", str(exc)),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha inesperada na etapa 2 do cadastro", exc_info=exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha na Etapa 2", "Erro interno inesperado. Tente novamente."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha na Etapa 2", "Erro interno inesperado. Tente novamente."),
                    ephemeral=True,
                )


class MemberRegistrationStepThreeModal(discord.ui.Modal, title="Cadastro Oficial Drakoria | Etapa 3/3"):
    truth_confirmation = discord.ui.TextInput(
        label="9) Confirma veracidade das informações?",
        placeholder="Responda: SIM",
        max_length=20,
        required=True,
    )
    final_notes = discord.ui.TextInput(
        label="10) Observação final (opcional)",
        placeholder="Se quiser, deixe uma observação adicional",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=False,
    )

    def __init__(self, bot: Any, session_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Contexto Inválido", "Este modal só funciona dentro do servidor."),
                    ephemeral=True,
                )
                return
            if self.truth_confirmation.value.strip().lower() not in {"sim", "confirmo", "ok"}:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error(
                        "Confirmação Inválida",
                        "Para finalizar, confirme explicitamente a veracidade respondendo `SIM`.",
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.defer(ephemeral=True)
            result = await self.bot.member_registration_service.finalize(
                interaction,
                interaction.user,
                self.session_id,
                truth_confirmation=self.truth_confirmation.value,
                final_notes=self.final_notes.value,
            )
            if result.status == "rejected_underage":
                await interaction.followup.send(
                    embed=self.bot.embeds.warning("Cadastro Encerrado", result.detail),
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                embed=self.bot.embeds.success("Cadastro Concluído", result.detail),
                ephemeral=True,
            )
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha ao Finalizar Cadastro", str(exc)),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha inesperada na etapa 3 do cadastro", exc_info=exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha ao Finalizar Cadastro", "Erro interno inesperado. Tente novamente."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha ao Finalizar Cadastro", "Erro interno inesperado. Tente novamente."),
                    ephemeral=True,
                )


class BetaProgramPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Enviar Cadastro",
        emoji="\N{MEMO}",
        style=discord.ButtonStyle.success,
        custom_id="drakoria:beta:panel:start",
    )
    async def start_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Contexto Inválido", "Este painel só funciona no servidor oficial."),
                    ephemeral=True,
                )
                return
            result = await self.bot.beta_program_service.start_or_resume_application(interaction, interaction.user)
            if result.status in {"already_approved", "already_pending", "blocked_reapply"}:
                await interaction.response.send_message(
                    embed=self.bot.embeds.warning("Cadastro Beta", result.detail),
                    ephemeral=True,
                )
                return
            if result.application_id is None:
                raise RuntimeError("Não foi possível abrir candidatura beta.")
            app = await self.bot.db.get_beta_tester_application(result.application_id)
            last_step = str(app.get("last_step") if app else "started")
            if last_step in {"started"}:
                await interaction.response.send_modal(BetaApplicationStepOneModal(self.bot, result.application_id))
                return
            if last_step in {"step_1"}:
                await interaction.response.send_modal(BetaApplicationStepTwoModal(self.bot, result.application_id))
                return
            await interaction.response.send_modal(BetaApplicationStepThreeModal(self.bot, result.application_id))
        except RuntimeError as exc:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha ao iniciar candidatura beta", str(exc)),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha inesperada no start do painel beta", exc_info=exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha no Programa Beta", "Erro interno inesperado."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha no Programa Beta", "Erro interno inesperado."),
                    ephemeral=True,
                )


class BetaProgramContinueView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Continuar Candidatura",
        style=discord.ButtonStyle.primary,
        custom_id="drakoria:beta:continue",
    )
    async def continue_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Contexto Inválido", "Use esta ação dentro do servidor oficial."),
                    ephemeral=True,
                )
                return
            app = await self.bot.db.get_latest_beta_tester_application(interaction.guild_id, interaction.user.id)
            if not app or str(app.get("status")) != "in_progress":
                await interaction.response.send_message(
                    embed=self.bot.embeds.warning("Sem candidatura em andamento", "Não há cadastro beta ativo para continuar."),
                    ephemeral=True,
                )
                return
            app_id = int(app["id"])
            step = str(app.get("last_step") or "started")
            if step in {"started"}:
                await interaction.response.send_modal(BetaApplicationStepOneModal(self.bot, app_id))
                return
            if step in {"step_1"}:
                await interaction.response.send_modal(BetaApplicationStepTwoModal(self.bot, app_id))
                return
            await interaction.response.send_modal(BetaApplicationStepThreeModal(self.bot, app_id))
        except Exception as exc:
            self.bot.log.exception("Falha ao continuar candidatura beta", exc_info=exc)
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Falha no Programa Beta", "Erro interno ao continuar candidatura."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Falha no Programa Beta", "Erro interno ao continuar candidatura."),
                    ephemeral=True,
                )


class BetaApplicationStepOneModal(discord.ui.Modal, title="Programa Beta | Etapa 1/3"):
    age = discord.ui.TextInput(label="1) Qual é a sua idade?", max_length=3, required=True)
    availability = discord.ui.TextInput(
        label="2) Dias/horários de disponibilidade",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
    )
    bug_reaction = discord.ui.TextInput(
        label="3) Quando encontra bug, o que faz?",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
    )
    detailist_example = discord.ui.TextInput(
        label="4) Você é detalhista? Cite exemplo",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
    )

    def __init__(self, bot: Any, application_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.application_id = application_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            int(self.age.value.strip())
            await self.bot.beta_program_service.save_step_answers(
                self.application_id,
                "step_1",
                {
                    "age": self.age.value,
                    "availability": self.availability.value,
                    "bug_reaction": self.bug_reaction.value,
                    "detailist_example": self.detailist_example.value,
                },
            )
            await interaction.response.send_message(
                embed=self.bot.embeds.success(
                    "Etapa 1 concluída",
                    "Suas respostas iniciais foram registradas. Clique em continuar candidatura.",
                ),
                view=BetaProgramContinueView(self.bot),
                ephemeral=True,
            )
        except ValueError:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Idade inválida", "Informe a idade com número inteiro."),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha etapa 1 beta", exc_info=exc)
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha na Etapa 1", str(exc)[:300]),
                ephemeral=True,
            )


class BetaApplicationStepTwoModal(discord.ui.Modal, title="Programa Beta | Etapa 2/3"):
    good_tester = discord.ui.TextInput(
        label="5) O que torna alguém um bom beta tester?",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
    )
    critical_failure_report = discord.ui.TextInput(
        label="6) Como comunicaria uma falha importante?",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True,
    )
    best_test_type = discord.ui.TextInput(
        label="7) Em qual tipo de teste se sai melhor?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    def __init__(self, bot: Any, application_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.application_id = application_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.bot.beta_program_service.save_step_answers(
                self.application_id,
                "step_2",
                {
                    "good_tester": self.good_tester.value,
                    "critical_failure_report": self.critical_failure_report.value,
                    "best_test_type": self.best_test_type.value,
                },
            )
            await interaction.response.send_message(
                embed=self.bot.embeds.success(
                    "Etapa 2 concluída",
                    "Excelente. Clique em continuar candidatura para finalizar.",
                ),
                view=BetaProgramContinueView(self.bot),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha etapa 2 beta", exc_info=exc)
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Falha na Etapa 2", str(exc)[:300]),
                ephemeral=True,
            )


class BetaApplicationStepThreeModal(discord.ui.Modal, title="Programa Beta | Etapa 3/3"):
    consistency_commitment = discord.ui.TextInput(
        label="8) Consegue manter constância e compromisso?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )
    why_join = discord.ui.TextInput(
        label="9) Por que quer participar do Programa Beta?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )
    expected_contribution = discord.ui.TextInput(
        label="10) Qual contribuição pode entregar?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    def __init__(self, bot: Any, application_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.application_id = application_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto inválido", "Use esta ação no servidor oficial."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.beta_program_service.save_step_answers(
                self.application_id,
                "step_3",
                {
                    "consistency_commitment": self.consistency_commitment.value,
                    "why_join": self.why_join.value,
                    "expected_contribution": self.expected_contribution.value,
                },
            )
            await self.bot.beta_program_service.submit_application(interaction.guild, interaction.user, self.application_id)
            await interaction.followup.send(
                embed=self.bot.embeds.success(
                    "Candidatura Enviada",
                    "Sua candidatura beta foi enviada para avaliação da equipe.",
                ),
                ephemeral=True,
            )
        except Exception as exc:
            self.bot.log.exception("Falha etapa 3 beta", exc_info=exc)
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha ao enviar candidatura", str(exc)[:300]),
                ephemeral=True,
            )


class BetaApplicationReviewView(discord.ui.View):
    def __init__(self, bot: Any, application_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.application_id = application_id
        approve = discord.ui.Button(
            label="Aprovar",
            style=discord.ButtonStyle.success,
            custom_id=f"drakoria:beta:review:approve:{application_id}",
        )
        approve.callback = self.approve_button
        reject = discord.ui.Button(
            label="Reprovar",
            style=discord.ButtonStyle.danger,
            custom_id=f"drakoria:beta:review:reject:{application_id}",
        )
        reject.callback = self.reject_button
        refresh = discord.ui.Button(
            label="Atualizar Candidatura",
            style=discord.ButtonStyle.secondary,
            custom_id=f"drakoria:beta:review:refresh:{application_id}",
        )
        refresh.callback = self.refresh_button
        self.add_item(approve)
        self.add_item(reject)
        self.add_item(refresh)

    async def approve_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto inválido", "A revisão exige contexto de guild."),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("manage_beta_program"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.beta_program_service.approve_application(interaction, self.application_id)
            await interaction.followup.send(embed=self.bot.embeds.success("Candidatura Aprovada", result), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha na aprovação", str(exc)[:300]),
                ephemeral=True,
            )

    async def reject_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto inválido", "A revisão exige contexto de guild."),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("manage_beta_program"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(BetaApplicationRejectModal(self.bot, self.application_id))

    async def refresh_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto inválido", "A revisão exige contexto de guild."),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "manage_beta_program"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("manage_beta_program"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.beta_program_service.refresh_application_message(interaction.guild, self.application_id)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Candidatura Atualizada", "A mensagem da candidatura foi sincronizada."),
            ephemeral=True,
        )


class BetaApplicationRejectModal(discord.ui.Modal, title="Reprovar Candidatura Beta"):
    reason = discord.ui.TextInput(
        label="Motivo da reprovação",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True,
    )

    def __init__(self, bot: Any, application_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.application_id = application_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.beta_program_service.reject_application(
                interaction,
                self.application_id,
                self.reason.value,
            )
            await interaction.followup.send(embed=self.bot.embeds.success("Candidatura Reprovada", result), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Falha na reprovação", str(exc)[:300]),
                ephemeral=True,
            )


class OfficialPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Ingressar na Whitelist",
        style=discord.ButtonStyle.success,
        custom_id="drakoria:panel:onboarding",
    )
    async def onboarding_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild:
            return
        is_open = await self.bot.onboarding_service.is_open(interaction.guild_id)
        if not is_open:
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Portões Fechados",
                    "Os portões de onboarding estão cerrados neste momento. Aguarda novo decreto da coroa.",
                ),
                ephemeral=True,
            )
            return
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Convocação Inválida",
                    "Este painel só pode ser usado por membros do reino dentro do servidor oficial.",
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(OnboardingModal(self.bot))

    @discord.ui.button(
        label="Abrir Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="drakoria:panel:ticket",
    )
    async def ticket_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.bot.ticket_service.send_panel_entrypoint(interaction)

    @discord.ui.button(
        label="Consultar Pontos",
        style=discord.ButtonStyle.secondary,
        custom_id="drakoria:panel:points",
    )
    async def points_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        total = await self.bot.db.get_points(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            embed=self.bot.embeds.make(
                title="Quadro de Méritos",
                description=f"{interaction.user.mention}, teu registro atual é de **{total}** pontos.",
            ),
            ephemeral=True,
        )


class OnboardingModal(discord.ui.Modal):
    def __init__(self, bot: Any) -> None:
        super().__init__(title="Pergaminho de Ingresso")
        self.bot = bot
        for question in bot.server_map.onboarding_questions()[:5]:
            self.add_item(
                discord.ui.TextInput(
                    label=question["label"][:45],
                    placeholder=question.get("placeholder", ""),
                    required=question.get("required", True),
                    style=discord.TextStyle.paragraph if question.get("paragraph", True) else discord.TextStyle.short,
                    max_length=question.get("max_length", 500),
                )
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {item.label: item.value for item in self.children if isinstance(item, discord.ui.TextInput)}
        await interaction.response.defer(ephemeral=True)
        try:
            application_id = await self.bot.onboarding_service.submit_application(interaction, answers)
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Pergaminho Recusado", str(exc)),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Pedido Entregue",
                f"Teu pergaminho foi enviado com sucesso. Registro oficial: **indisponível**.",
            ),
            ephemeral=True,
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketTypeSelect(bot))


class TicketTypeSelect(discord.ui.Select):
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        options = [
            discord.SelectOption(
                label=ticket_type["label"][:100],
                description=ticket_type["description"][:100],
                emoji=ticket_type["emoji"],
                value=ticket_type["key"],
            )
            for ticket_type in self.bot.ticket_service.ticket_types()
        ]
        super().__init__(
            placeholder="Selecione a categoria correta para o atendimento",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="drakoria:tickets:panel:type-select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                if interaction.response.is_done():
                    await interaction.followup.send(
                        embed=self.bot.embeds.error(
                            "Contexto inválido",
                            "Tickets só podem ser abertos por membros dentro do servidor oficial.",
                        ),
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        embed=self.bot.embeds.error(
                            "Contexto inválido",
                            "Tickets só podem ser abertos por membros dentro do servidor oficial.",
                        ),
                        ephemeral=True,
                    )
                return

            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)

            channel = await self.bot.ticket_service.open_ticket(
                interaction.user,
                self.values[0],
                origin="Painel Tickets",
            )
            await interaction.followup.send(
                embed=self.bot.embeds.success(
                    "Ticket aberto",
                    f"Seu canal de atendimento foi criado em {channel.mention}. A equipe foi notificada.",
                ),
                ephemeral=True,
            )
        except RuntimeError as exc:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self.bot.embeds.error("Não foi possível abrir o ticket", str(exc)),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self.bot.embeds.error("Não foi possível abrir o ticket", str(exc)),
                    ephemeral=True,
                )
        except Exception as exc:
            self.bot.log.exception("Falha inesperada ao abrir ticket pelo painel", exc_info=exc)
            error_embed = self.bot.embeds.error(
                "Falha ao abrir ticket",
                "Ocorreu um erro inesperado ao processar sua solicitação. Tente novamente em instantes.",
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)


class OnboardingReviewView(discord.ui.View):
    def __init__(self, bot: Any, target_user_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.target_user_id = target_user_id
        approve = discord.ui.Button(
            label="Aprovar",
            style=discord.ButtonStyle.success,
            custom_id=f"drakoria:onboarding:approve:{target_user_id}",
        )
        approve.callback = self.approve_button
        reject = discord.ui.Button(
            label="Reprovar",
            style=discord.ButtonStyle.danger,
            custom_id=f"drakoria:onboarding:reject:{target_user_id}",
        )
        reject.callback = self.reject_button
        self.add_item(approve)
        self.add_item(reject)

    async def approve_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Convocação Inválida",
                    "O julgamento de pergaminhos só pode ocorrer dentro do servidor oficial.",
                ),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "review_onboarding"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("review_onboarding"),
                ephemeral=True,
            )
            return
        member = interaction.guild.get_member(self.target_user_id)
        if not member:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Aventureiro Ausente", "Não foi possível localizar o membro no reino."),
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        try:
            await self.bot.onboarding_service.approve(interaction, member, reason="Aceito pela corte")
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Julgamento Bloqueado", str(exc)),
                ephemeral=True,
            )
            return
        if interaction.message:
            await interaction.message.edit(
                embed=self.bot.embeds.success(
                    "Pedido Aprovado",
                    f"{member.mention} foi recebido oficialmente nos salões de Drakoria.",
                ),
                view=None,
            )
        try:
            await member.send(
                embed=self.bot.embeds.success(
                    "Tu Foste Aceito",
                    "A coroa aprovou teu ingresso. Prepara-te para servir ao reino de Drakoria.",
                )
            )
        except discord.HTTPException:
            pass

    async def reject_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Convocação Inválida",
                    "O julgamento de pergaminhos só pode ocorrer dentro do servidor oficial.",
                ),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "review_onboarding"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("review_onboarding"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(OnboardingRejectModal(self.bot, self.target_user_id, interaction.message))


class OnboardingRejectModal(discord.ui.Modal, title="Reprovar Pergaminho"):
    reason = discord.ui.TextInput(
        label="Motivo da reprovação",
        placeholder="Explica com clareza o motivo do decreto",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    def __init__(self, bot: Any, target_user_id: int, origin_message: discord.Message | None) -> None:
        super().__init__()
        self.bot = bot
        self.target_user_id = target_user_id
        self.origin_message = origin_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        member = interaction.guild.get_member(self.target_user_id)
        if not member:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Aventureiro Ausente", "Não foi possível localizar o membro no reino."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.onboarding_service.reject(interaction, member, self.reason.value)
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Julgamento Bloqueado", str(exc)),
                ephemeral=True,
            )
            return
        if self.origin_message:
            await self.origin_message.edit(
                embed=self.bot.embeds.error(
                    "Pedido Reprovado",
                    f"{member.mention} teve o ingresso recusado.\nMotivo: **{self.reason.value}**",
                ),
                view=None,
            )
        await interaction.followup.send(
            embed=self.bot.embeds.success("Decreto Registrado", "A reprovação foi lavrada com sucesso."),
            ephemeral=True,
        )
        try:
            await member.send(
                embed=self.bot.embeds.error(
                    "Ingresso Recusado",
                    f"A corte de Drakoria recusou teu pedido.\nMotivo: **{self.reason.value}**",
                )
            )
        except discord.HTTPException:
            pass


class VoicePointPanelView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Meu Estado", style=discord.ButtonStyle.secondary, custom_id="drakoria:voicepoint:status")
    async def status_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Convocação Inválida", "Este painel só pode ser usado dentro do servidor oficial."),
                ephemeral=True,
            )
            return
        status = await self.bot.point_service.describe_member_status(interaction.user)
        title = "Estado Atual do Expediente" if status.active else "Registro do Expediente"
        await interaction.response.send_message(
            embed=self.bot.embeds.make(title=title, description=status.summary),
            ephemeral=True,
        )

    @discord.ui.button(label="Encerrar meu expediente", style=discord.ButtonStyle.danger, custom_id="drakoria:voicepoint:stop")
    async def stop_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Convocação Inválida", "O expediente só pode ser controlado dentro do servidor oficial."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.point_service.manual_close(
                interaction.user,
                interaction.user,
                close_reason="Encerrado manualmente pelo próprio membro via painel.",
            )
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Não Foi Possível Encerrar", str(exc)),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=self.bot.embeds.success("Expediente Encerrado", "Teu expediente foi encerrado e o relatório foi lavrado."),
            ephemeral=True,
        )

    @discord.ui.button(label="Atualizar Painel", style=discord.ButtonStyle.secondary, custom_id="drakoria:voicepoint:refresh")
    async def refresh_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Convocação Inválida", "O painel só pode ser administrado dentro do servidor oficial."),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "manage_points"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("manage_points"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.point_service.publish_panel(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            embed=self.bot.embeds.success("Painel Atualizado", "O painel do expediente foi sincronizado novamente."),
            ephemeral=True,
        )


class TicketControlView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _safe_reply(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        *,
        view: discord.ui.View | None = None,
    ) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]) -> None:
        self.bot.log.exception("Falha em interação de ticket (item=%s)", getattr(item, "custom_id", "unknown"), exc_info=error)
        await self._safe_reply(
            interaction,
            self.bot.embeds.error(
                "Falha na interação",
                "Não foi possível concluir esta ação do ticket. Tente novamente em instantes.",
            ),
        )

    async def _ensure_staff(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await self._safe_reply(
                interaction,
                embed=self.bot.embeds.error(
                    "Contexto inválido",
                    "Os controles de ticket só funcionam em canais de ticket.",
                ),
            )
            return False
        if not self.bot.permission_service.has(interaction.user, "manage_tickets"):
            await self._safe_reply(interaction, self.bot.permission_service.denial_embed("manage_tickets"))
            return False
        return True

    async def _ensure_can_close(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await self._safe_reply(
                interaction,
                embed=self.bot.embeds.error(
                    "Contexto inválido",
                    "Os controles de ticket só funcionam em canais de ticket.",
                ),
            )
            return False
        if not isinstance(interaction.channel, discord.TextChannel):
            await self._safe_reply(
                interaction,
                embed=self.bot.embeds.error("Canal inválido", "Este controle exige um canal de texto válido."),
            )
            return False
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await self._safe_reply(
                interaction,
                embed=self.bot.embeds.error("Ticket inválido", "Este canal não está vinculado a nenhum ticket oficial."),
            )
            return False
        is_staff = self.bot.permission_service.has(interaction.user, "manage_tickets")
        is_author = int(ticket["user_id"]) == interaction.user.id
        if not is_staff and not is_author:
            await self._safe_reply(
                interaction,
                embed=self.bot.embeds.error(
                    "Encerramento negado",
                    "Somente a staff responsável ou o autor do ticket pode encerrar este atendimento.",
                ),
            )
            return False
        return True

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.primary, custom_id="drakoria:ticket:claim")
    async def claim_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            ticket = await self.bot.ticket_service.claim_ticket(interaction)
        except RuntimeError as exc:
            await self._safe_reply(interaction, self.bot.embeds.error("Não foi possível assumir", str(exc)))
            return
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.success(
                "Atendimento Assumido",
                f"{interaction.user.mention} agora responde oficialmente pelo ticket **indisponível**.",
            ),
        )

    @discord.ui.button(label="Transferir Ticket", style=discord.ButtonStyle.secondary, custom_id="drakoria:ticket:transfer")
    async def transfer_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_staff(interaction):
            return
        await interaction.response.send_modal(TicketTransferModal(self.bot))

    @discord.ui.button(label="Alterar Status", style=discord.ButtonStyle.secondary, custom_id="drakoria:ticket:status")
    async def status_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_staff(interaction):
            return
        await self._safe_reply(
            interaction,
            embed=self.bot.embeds.make(
                title="Estado do Ticket",
                description="Selecione abaixo o novo status operacional deste atendimento.",
            ),
            view=TicketStatusView(self.bot),
        )

    @discord.ui.button(label="Encerrar Ticket", style=discord.ButtonStyle.danger, custom_id="drakoria:ticket:close")
    async def close_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_can_close(interaction):
            return
        await interaction.response.send_modal(TicketCloseModal(self.bot))

    @discord.ui.button(label="Atualizar Painel do Ticket", style=discord.ButtonStyle.secondary, custom_id="drakoria:ticket:refresh")
    async def refresh_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._ensure_staff(interaction):
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await self._safe_reply(
                interaction,
                self.bot.embeds.error("Canal inválido", "Este controle exige um canal de texto válido."),
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.ticket_service.refresh_ticket_panel(interaction.channel)
        except RuntimeError as exc:
            await self._safe_reply(interaction, self.bot.embeds.error("Não foi possível atualizar", str(exc)))
            return
        await self._safe_reply(
            interaction,
            self.bot.embeds.success("Painel sincronizado", "O painel interno deste ticket foi atualizado."),
        )


class TicketStatusView(discord.ui.View):
    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.add_item(TicketStatusSelect(bot))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]) -> None:
        self.bot.log.exception("Falha em interação de status de ticket", exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=self.bot.embeds.error(
                    "Falha na interação",
                    "Não foi possível atualizar o status do ticket nesta tentativa.",
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=self.bot.embeds.error(
                    "Falha na interação",
                    "Não foi possível atualizar o status do ticket nesta tentativa.",
                ),
                ephemeral=True,
            )


class TicketStatusSelect(discord.ui.Select):
    def __init__(self, bot: Any) -> None:
        self.bot = bot
        options = [
            discord.SelectOption(label=self.bot.ticket_service.status_label("open"), value="open"),
            discord.SelectOption(label=self.bot.ticket_service.status_label("in_progress"), value="in_progress"),
            discord.SelectOption(label=self.bot.ticket_service.status_label("waiting_user"), value="waiting_user"),
        ]
        super().__init__(
            placeholder="Selecione o estado operacional",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.bot.embeds.error("Contexto inválido", "Esta ação só pode ser usada no servidor oficial."),
                ephemeral=True,
            )
            return
        if not self.bot.permission_service.has(interaction.user, "manage_tickets"):
            await interaction.response.send_message(
                embed=self.bot.permission_service.denial_embed("manage_tickets"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            ticket = await self.bot.ticket_service.set_status(interaction, self.values[0])
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Estado Bloqueado", str(exc)),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Estado Atualizado",
                f"O ticket **indisponível** agora está marcado como **{self.bot.ticket_service.status_label(self.values[0])}**.",
            ),
            ephemeral=True,
        )


class TicketTransferModal(discord.ui.Modal, title="Transferir Ticket"):
    staff_id = discord.ui.TextInput(
        label="ID do novo responsável",
        placeholder="Informe o ID numérico do membro que assumirá o ticket",
        max_length=32,
    )

    def __init__(self, bot: Any) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            target_member_id = int(self.staff_id.value.strip())
        except ValueError:
            await interaction.response.send_message(
                embed=self.bot.embeds.error("ID inválido", "Informe um ID numérico válido para a transferência."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            ticket = await self.bot.ticket_service.transfer_ticket(interaction, target_member_id)
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Transferência negada", str(exc)),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=self.bot.embeds.success(
                "Ticket Transferido",
                f"O ticket **indisponível** foi transferido com sucesso para <@{target_member_id}>.",
            ),
            ephemeral=True,
        )


class TicketCloseModal(discord.ui.Modal, title="Encerrar Ticket"):
    reason = discord.ui.TextInput(
        label="Motivo do encerramento",
        placeholder="Resuma o desfecho administrativo deste atendimento",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    def __init__(self, bot: Any) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.ticket_service.close_ticket(interaction, self.reason.value)
        except RuntimeError as exc:
            await interaction.followup.send(
                embed=self.bot.embeds.error("Encerramento Negado", str(exc)),
                ephemeral=True,
            )
            return

        summary = (
            "O ticket foi encerrado, registrado no banco e a transcrição foi arquivada."
            f"\nStatus da DM ao usuário: **{result.dm_status}**."
        )
        if result.transcript_channel_id and result.transcript_message_id:
            summary += (
                f"\nArquivo arquivado em <#{result.transcript_channel_id}> "
                f"sob a mensagem indisponível."
            )
        await interaction.followup.send(
            embed=self.bot.embeds.success("Ticket Encerrado", summary),
            ephemeral=True,
        )
        if isinstance(interaction.channel, discord.TextChannel):
            if result.close_behavior == "archive":
                ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
                await interaction.channel.edit(
                    name=f"encerrado-{interaction.channel.name}"[:90],
                    reason=f"Ticket encerrado por {interaction.user}",
                )
                if ticket:
                    author = interaction.guild.get_member(int(ticket["user_id"])) if interaction.guild else None
                    if author is not None:
                        await interaction.channel.set_permissions(
                            author,
                            overwrite=discord.PermissionOverwrite(
                                view_channel=True,
                                send_messages=False,
                                read_message_history=True,
                                attach_files=False,
                            ),
                            reason="Encerramento administrativo do ticket",
                        )
                    for role_id in self.bot.server_map.ticket_support_role_ids():
                        role = interaction.guild.get_role(int(role_id)) if interaction.guild else None
                        if role is not None:
                            await interaction.channel.set_permissions(
                                role,
                                overwrite=discord.PermissionOverwrite(
                                    view_channel=True,
                                    send_messages=False,
                                    read_message_history=True,
                                    attach_files=False,
                                    manage_messages=True,
                                ),
                                reason="Arquivamento administrativo do ticket",
                            )
            else:
                await interaction.channel.delete(reason=f"Ticket encerrado por {interaction.user}")







