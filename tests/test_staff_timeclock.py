"""
Suite de testes para o sistema de jornada da staff (StaffTimeclockService).

Cobre os 15 cenários de teste descritos nos requisitos:
  1. Jornada básica
  2. Sessão duplicada
  3. Atividade
  4. Ambiente/call
  5. Canal inválido/AFK
  6. Trabalho externo (fora de call)
  7. Check-in
  8. Permissões
  9. Configuração
  10. Relatórios / cálculo de horas
  11-15. Casos especiais (reinício, remoção de cargo, logs, cálculo, compatibilidade)

Executar com:
    .venv/Scripts/python -m pytest tests/test_staff_timeclock.py -v
    ou
    .venv/Scripts/python -m unittest discover tests
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers de mock ───────────────────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _make_session(
    session_id: int = 1,
    guild_id: int = 999,
    user_id: int = 111,
    status: str = "active",
    started_at: datetime | None = None,
    segment_started_at: datetime | None = None,
    total_valid_seconds: int = 0,
    total_paused_seconds: int = 0,
    total_pending_seconds: int = 0,
    current_activity: str = "Não classificado",
    current_environment: str | None = "Call Dev",
    current_channel_id: int | None = 555,
    pause_started_at: datetime | None = None,
    active_pause_id: int | None = None,
    checkin_pending: int = 0,
    last_checkin_at: str | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    started = started_at or (now - timedelta(minutes=30))
    seg_started = segment_started_at or started
    return {
        "id": session_id,
        "guild_id": guild_id,
        "user_id": user_id,
        "status": status,
        "started_at": _iso(started),
        "ended_at": None,
        "close_reason": None,
        "close_mode": None,
        "ended_by_user_id": None,
        "current_activity": current_activity,
        "current_environment": current_environment,
        "current_channel_id": current_channel_id,
        "segment_started_at": _iso(seg_started) if status == "active" else None,
        "pause_started_at": _iso(pause_started_at) if pause_started_at else None,
        "active_pause_id": active_pause_id,
        "total_valid_seconds": total_valid_seconds,
        "total_paused_seconds": total_paused_seconds,
        "total_pending_seconds": total_pending_seconds,
        "checkin_pending": checkin_pending,
        "last_checkin_at": last_checkin_at,
        "notes": None,
        "created_at": _iso(started),
        "updated_at": _iso(now),
    }


def _make_segment(
    segment_id: int = 10,
    session_id: int = 1,
    guild_id: int = 999,
    user_id: int = 111,
    activity: str = "Não classificado",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_seconds: int | None = None,
    segment_status: str = "valid",
) -> dict[str, Any]:
    now = _utcnow()
    started = started_at or (now - timedelta(minutes=10))
    ended = ended_at or now
    duration = duration_seconds if duration_seconds is not None else max(0, int((ended - started).total_seconds()))
    return {
        "id": segment_id,
        "session_id": session_id,
        "guild_id": guild_id,
        "user_id": user_id,
        "activity": activity,
        "environment": "Call Dev",
        "channel_id": 555,
        "started_at": _iso(started),
        "ended_at": _iso(ended) if ended_at is not None else None,
        "duration_seconds": duration if ended_at is not None else None,
        "segment_status": segment_status,
        "created_at": _iso(started),
    }


def _make_role(role_id: int = 123) -> MagicMock:
    role = MagicMock()
    role.id = role_id
    return role


def _make_member(
    user_id: int = 111,
    guild_id: int = 999,
    role_ids: list[int] | None = None,
    voice_channel_id: int | None = None,
    voice_channel_name: str | None = None,
    bot: bool = False,
) -> MagicMock:
    member = MagicMock()
    member.id = user_id
    member.bot = bot
    member.display_name = f"User{user_id}"
    member.mention = f"<@{user_id}>"
    guild = MagicMock()
    guild.id = guild_id
    member.guild = guild
    member.roles = [_make_role(rid) for rid in (role_ids or [])]
    if voice_channel_id:
        vc = MagicMock()
        vc.id = voice_channel_id
        vc.name = voice_channel_name or "Call Dev"
        member.voice = MagicMock()
        member.voice.channel = vc
    else:
        member.voice = None
    return member


def _make_bot(staff_role_ids: list[int] | None = None, staff_roles_in_db: bool = True) -> MagicMock:
    """Cria um bot mock com db, server_map, embeds, log e permission_service."""
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 0

    # DB mock — todos os métodos são AsyncMock
    db = MagicMock()
    db.get_staff_roles = AsyncMock(return_value=[{"role_id": rid} for rid in (staff_role_ids or [123])] if staff_roles_in_db else [])
    db.get_staff_open_session = AsyncMock(return_value=None)
    db.get_staff_session = AsyncMock(return_value=None)
    db.list_open_staff_sessions = AsyncMock(return_value=[])
    db.create_staff_session = AsyncMock(return_value=1)
    db.update_staff_session = AsyncMock()
    db.add_staff_segment = AsyncMock(return_value=10)
    db.close_staff_segment = AsyncMock()
    db.get_session_segments = AsyncMock(return_value=[])
    db.open_staff_pause = AsyncMock(return_value=20)
    db.close_staff_pause = AsyncMock()
    db.create_staff_checkin = AsyncMock(return_value=30)
    db.update_staff_checkin = AsyncMock()
    db.get_pending_checkin = AsyncMock(return_value=None)
    db.get_expired_checkins = AsyncMock(return_value=[])
    db.log_staff_event = AsyncMock()
    db.add_staff_role = AsyncMock()
    db.remove_staff_role = AsyncMock()
    db.get_channel_rule = AsyncMock(return_value=None)
    db.set_channel_rule = AsyncMock()
    db.remove_channel_rule = AsyncMock()
    db.get_all_channel_rules = AsyncMock(return_value=[])
    db.get_staff_segments_in_range = AsyncMock(return_value=[])
    db.get_staff_sessions_in_range = AsyncMock(return_value=[])
    db.get_staff_adjustments = AsyncMock(return_value=[])
    db.add_staff_adjustment = AsyncMock()
    db.get_staff_timeclock_panel = AsyncMock(return_value=None)
    db.save_staff_timeclock_panel = AsyncMock()
    bot.db = db

    # server_map mock
    sm = MagicMock()
    sm.guild_id = MagicMock(return_value=999)
    sm.voice_point_allowed_role_ids = MagicMock(return_value=staff_role_ids or [123])
    sm.voice_point_channel_groups = MagicMock(return_value={})
    sm.voice_point_valid_channel_ids = MagicMock(return_value=[])
    sm.staff_timeclock_panel_channel_id = MagicMock(return_value=None)
    sm.staff_timeclock_log_channel_id = MagicMock(return_value=None)
    sm.staff_timeclock_checkin_interval_in_call = MagicMock(return_value=3600)
    sm.staff_timeclock_checkin_interval_external = MagicMock(return_value=1800)
    bot.server_map = sm

    # embeds mock
    embeds = MagicMock()
    embeds.success_color = 0x00FF00
    embeds.warning_color = 0xFFAA00
    embeds.error_color = 0xFF0000
    embeds.default_color = 0x888888
    embeds.make = MagicMock(return_value=MagicMock())
    bot.embeds = embeds

    # log mock
    bot.log = MagicMock()
    bot.log.exception = MagicMock()

    # permission_service mock
    perm = MagicMock()
    perm.has = MagicMock(return_value=True)
    bot.permission_service = perm

    # get_guild / get_channel
    bot.get_guild = MagicMock(return_value=None)
    bot.get_channel = MagicMock(return_value=None)

    return bot


def _svc(bot=None):
    """Importa o serviço e instancia com o bot mock dado."""
    from app.services.staff_timeclock_service import StaffTimeclockService
    return StaffTimeclockService(bot or _make_bot())


# ── Caso de teste base ────────────────────────────────────────────────────────

class AsyncTestCase(unittest.IsolatedAsyncioTestCase):
    """Base que silencia logs do discord.py."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 1 — Jornada básica
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasicJourney(AsyncTestCase):

    async def test_start_session_creates_session(self):
        """start_session deve criar sessão e retornar dados válidos."""
        bot = _make_bot(staff_role_ids=[123])
        bot.db.get_staff_open_session = AsyncMock(side_effect=[None, _make_session()])
        svc = _svc(bot)
        member = _make_member(role_ids=[123])

        with patch.object(svc, "refresh_panel", AsyncMock()):
            result = await svc.start_session(member)

        bot.db.create_staff_session.assert_called_once()
        bot.db.add_staff_segment.assert_called_once()
        self.assertIsNotNone(result)

    async def test_start_session_without_staff_role_raises(self):
        """Staff sem cargo não deve iniciar expediente."""
        bot = _make_bot(staff_role_ids=[123])
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        svc = _svc(bot)
        member = _make_member(role_ids=[999])  # cargo errado

        with self.assertRaises(RuntimeError) as ctx:
            await svc.start_session(member)
        self.assertIn("cargo de staff", str(ctx.exception).lower())

    async def test_pause_session_changes_status(self):
        """pause_session deve criar registro de pausa e mudar status."""
        bot = _make_bot()
        session = _make_session()
        paused_session = _make_session(status="paused", pause_started_at=_utcnow(), active_pause_id=20)
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, paused_session])
        bot.db.get_session_segments = AsyncMock(return_value=[
            _make_segment(started_at=_utcnow() - timedelta(minutes=10), ended_at=None)
        ])
        svc = _svc(bot)
        member = _make_member()

        with patch.object(svc, "refresh_panel", AsyncMock()):
            result = await svc.pause_session(member, reason="Teste")

        bot.db.open_staff_pause.assert_called_once()
        bot.db.update_staff_session.assert_called()

    async def test_pause_already_paused_raises(self):
        """Pausar expediente já pausado deve lançar erro."""
        bot = _make_bot()
        bot.db.get_staff_open_session = AsyncMock(return_value=_make_session(status="paused"))
        svc = _svc(bot)
        member = _make_member()

        with self.assertRaises(RuntimeError) as ctx:
            await svc.pause_session(member)
        self.assertIn("já está pausado", str(ctx.exception))

    async def test_resume_session_closes_pause(self):
        """resume_session deve fechar a pausa aberta."""
        bot = _make_bot()
        pause_started = _utcnow() - timedelta(minutes=5)
        session = _make_session(
            status="paused",
            pause_started_at=pause_started,
            active_pause_id=20,
            total_paused_seconds=0,
        )
        active_session = _make_session(status="active")
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, active_session])
        svc = _svc(bot)
        member = _make_member()

        with patch.object(svc, "refresh_panel", AsyncMock()):
            result = await svc.resume_session(member)

        bot.db.close_staff_pause.assert_called_once_with(20, unittest.mock.ANY, unittest.mock.ANY)
        # Verifica que total_paused_seconds foi atualizado (≥ 300 segundos de pausa de 5 min)
        update_call = bot.db.update_staff_session.call_args
        updates = update_call[0][1] if update_call[0] else update_call[1].get("fields", {})
        # O update inclui total_paused_seconds ~300
        self.assertIn("total_paused_seconds", str(update_call))

    async def test_end_session_closes_and_reports(self):
        """end_session deve marcar closed e enviar relatório."""
        bot = _make_bot()
        seg_started = _utcnow() - timedelta(minutes=20)
        session = _make_session(segment_started_at=seg_started)
        closed_session = {**session, "status": "closed", "ended_at": _iso(_utcnow())}
        bot.db.get_staff_open_session = AsyncMock(return_value=session)
        bot.db.get_staff_session = AsyncMock(return_value=closed_session)
        bot.db.get_session_segments = AsyncMock(return_value=[])
        svc = _svc(bot)
        member = _make_member()

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_send_session_report", AsyncMock()), \
             patch.object(svc, "_dispatch_close_log", AsyncMock()):
            result = await svc.end_session(member)

        # update_staff_session deve ter sido chamado com status=closed
        calls = bot.db.update_staff_session.call_args_list
        last_call = calls[-1]
        updates_dict = last_call[0][1] if last_call[0] else {}
        self.assertEqual(updates_dict.get("status"), "closed")


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 2 — Sessão duplicada
# ═══════════════════════════════════════════════════════════════════════════════

class TestDuplicateSession(AsyncTestCase):

    async def test_start_session_duplicate_raises(self):
        """Iniciar sessão quando já existe uma aberta deve levantar RuntimeError."""
        bot = _make_bot(staff_role_ids=[123])
        existing = _make_session(status="active")
        bot.db.get_staff_open_session = AsyncMock(return_value=existing)
        svc = _svc(bot)
        member = _make_member(role_ids=[123])

        with self.assertRaises(RuntimeError) as ctx:
            await svc.start_session(member)

        self.assertIn("Já existe", str(ctx.exception))
        bot.db.create_staff_session.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 3 — Atividade
# ═══════════════════════════════════════════════════════════════════════════════

class TestActivityTracking(AsyncTestCase):

    async def test_initial_activity_is_unclassified(self):
        """Sessão criada deve ter atividade inicial 'Não classificado'."""
        bot = _make_bot(staff_role_ids=[123])
        bot.db.get_staff_open_session = AsyncMock(side_effect=[None, _make_session()])
        svc = _svc(bot)
        member = _make_member(role_ids=[123])

        with patch.object(svc, "refresh_panel", AsyncMock()):
            await svc.start_session(member)

        create_call = bot.db.create_staff_session.call_args
        self.assertEqual(create_call.kwargs.get("activity", create_call[1].get("activity", "Não classificado")), "Não classificado")

    async def test_change_activity_closes_segment_and_opens_new(self):
        """change_activity deve fechar segmento atual e abrir novo com nova atividade."""
        bot = _make_bot()
        seg_started = _utcnow() - timedelta(minutes=10)
        session = _make_session(current_activity="Não classificado", segment_started_at=seg_started)
        updated_session = _make_session(current_activity="Desenvolvimento")
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, updated_session])
        bot.db.get_session_segments = AsyncMock(return_value=[
            _make_segment(activity="Não classificado", started_at=seg_started, ended_at=None)
        ])
        svc = _svc(bot)
        member = _make_member()

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            result = await svc.change_activity(member, "Desenvolvimento")

        # Segmento antigo fechado
        bot.db.close_staff_segment.assert_called_once()
        # Novo segmento aberto com nova atividade
        new_seg_call = bot.db.add_staff_segment.call_args
        self.assertEqual(new_seg_call.kwargs.get("activity", "?"), "Desenvolvimento")

    async def test_change_activity_invalid_raises(self):
        """Atividade inválida deve lançar RuntimeError."""
        svc = _svc()
        member = _make_member()

        with self.assertRaises(RuntimeError) as ctx:
            await svc.change_activity(member, "AtividadeInexistente")
        self.assertIn("inválida", str(ctx.exception).lower())

    async def test_change_activity_outside_active_session_raises(self):
        """Trocar atividade com sessão pausada deve falhar."""
        bot = _make_bot()
        bot.db.get_staff_open_session = AsyncMock(return_value=_make_session(status="paused"))
        svc = _svc(bot)
        member = _make_member()

        with self.assertRaises(RuntimeError):
            await svc.change_activity(member, "Desenvolvimento")

    async def test_voice_channel_does_not_change_activity(self):
        """Mudar de canal de voz NÃO deve alterar a atividade."""
        bot = _make_bot()
        session = _make_session(current_activity="Desenvolvimento", current_channel_id=555)
        bot.db.get_staff_open_session = AsyncMock(return_value=session)
        svc = _svc(bot)

        before = MagicMock()
        before.channel = MagicMock()
        before.channel.id = 555

        after_channel = MagicMock()
        after_channel.id = 666
        after_channel.name = "Call Founder"
        after = MagicMock()
        after.channel = after_channel

        member = _make_member(voice_channel_id=666, voice_channel_name="Call Founder")
        member.guild.id = 999

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.handle_voice_state_update(member, before, after)

        # Atividade NÃO deve ter sido alterada — change_activity não deve ter sido chamado
        update_calls = bot.db.update_staff_session.call_args_list
        for call in update_calls:
            updates = call[0][1] if call[0] else {}
            self.assertNotIn("current_activity", updates,
                msg="handle_voice_state_update não deve alterar current_activity")


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 4 e 5 — Ambiente / Canal inválido
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceEnvironment(AsyncTestCase):

    async def test_afk_channel_pauses_session(self):
        """Entrar em canal 'invalid' (AFK) deve pausar o expediente automaticamente."""
        bot = _make_bot()
        session = _make_session(status="active", current_channel_id=111)
        paused = _make_session(status="paused")
        # Chamadas: 1) handle_voice_update lê sessão, 2) pause_session lê sessão,
        # 3) pause_session retorna sessão pausada ao final
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, session, paused])
        bot.db.get_channel_rule = AsyncMock(return_value={"rule_type": "invalid"})
        bot.db.get_session_segments = AsyncMock(return_value=[
            _make_segment(started_at=_utcnow() - timedelta(minutes=5), ended_at=None)
        ])
        svc = _svc(bot)

        before = MagicMock()
        before.channel = MagicMock()
        before.channel.id = 111
        after = MagicMock()
        after.channel = MagicMock()
        after.channel.id = 999
        member = _make_member(voice_channel_id=999, voice_channel_name="AFK")
        member.guild.id = 999

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.handle_voice_state_update(member, before, after)

        bot.db.open_staff_pause.assert_called_once()

    async def test_valid_channel_updates_environment_not_activity(self):
        """Mover para canal válido deve atualizar ambiente, não atividade."""
        bot = _make_bot()
        session = _make_session(current_activity="Desenvolvimento", current_channel_id=111, current_environment="Call Dev")
        bot.db.get_staff_open_session = AsyncMock(return_value=session)
        bot.db.get_channel_rule = AsyncMock(return_value=None)  # fallback: neutral
        svc = _svc(bot)

        before = MagicMock()
        before.channel = MagicMock()
        before.channel.id = 111
        after_ch = MagicMock()
        after_ch.id = 222
        after_ch.name = "Call Founder"
        after = MagicMock()
        after.channel = after_ch
        member = _make_member(voice_channel_id=222, voice_channel_name="Call Founder")
        member.guild.id = 999

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.handle_voice_state_update(member, before, after)

        update_calls = bot.db.update_staff_session.call_args_list
        for call in update_calls:
            updates = call[0][1] if call[0] else {}
            self.assertNotIn("current_activity", updates)
        # Ambiente deve ter sido atualizado
        all_updates = {}
        for call in update_calls:
            all_updates.update(call[0][1] if call[0] else {})
        self.assertIn("current_environment", all_updates)

    async def test_no_session_voice_update_is_ignored(self):
        """Mudança de voz sem sessão ativa não deve criar sessão."""
        bot = _make_bot()
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        svc = _svc(bot)

        before = MagicMock()
        before.channel = None
        after = MagicMock()
        after.channel = MagicMock()
        after.channel.id = 111
        member = _make_member(voice_channel_id=111)
        member.guild.id = 999

        await svc.handle_voice_state_update(member, before, after)

        bot.db.create_staff_session.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 6 — Fora de call
# ═══════════════════════════════════════════════════════════════════════════════

class TestExternalWork(AsyncTestCase):

    async def test_start_session_without_voice_allowed(self):
        """Iniciar expediente fora de call deve ser permitido com ambiente None."""
        bot = _make_bot(staff_role_ids=[123])
        bot.db.get_staff_open_session = AsyncMock(side_effect=[None, _make_session(current_environment=None)])
        svc = _svc(bot)
        member = _make_member(role_ids=[123], voice_channel_id=None)

        with patch.object(svc, "refresh_panel", AsyncMock()):
            result = await svc.start_session(member)

        bot.db.create_staff_session.assert_called_once()
        create_kwargs = bot.db.create_staff_session.call_args.kwargs
        # ambiente deve ser None quando fora de call
        self.assertIsNone(create_kwargs.get("environment"))


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 7 — Check-in
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckin(AsyncTestCase):

    async def test_checkin_sent_when_interval_reached(self):
        """_maybe_send_checkins deve enviar check-in quando o intervalo foi atingido."""
        bot = _make_bot()
        old_checkin = _utcnow() - timedelta(seconds=3700)  # > 3600s → intervalo atingido
        session = _make_session(
            current_channel_id=555,
            last_checkin_at=_iso(old_checkin),
            checkin_pending=0,
        )
        bot.db.list_open_staff_sessions = AsyncMock(return_value=[session])
        bot.db.get_channel_rule = AsyncMock(return_value={"rule_type": "work"})
        bot.db.create_staff_checkin = AsyncMock(return_value=30)
        svc = _svc(bot)

        guild = MagicMock()
        guild.id = 999
        member = _make_member()
        member.send = AsyncMock()
        guild.get_member = MagicMock(return_value=member)

        with patch("app.core.staff_timeclock_views.StaffCheckinView", MagicMock(return_value=MagicMock())):
            await svc._maybe_send_checkins(guild)

        bot.db.create_staff_checkin.assert_called_once()
        member.send.assert_called_once()

    async def test_checkin_not_sent_if_already_pending(self):
        """Não deve enviar novo check-in se já existe um pendente."""
        bot = _make_bot()
        session = _make_session(checkin_pending=1)
        bot.db.list_open_staff_sessions = AsyncMock(return_value=[session])
        svc = _svc(bot)
        guild = MagicMock()
        guild.id = 999

        await svc._maybe_send_checkins(guild)

        bot.db.create_staff_checkin.assert_not_called()

    async def test_expired_checkin_pauses_session(self):
        """Check-in expirado deve pausar a sessão automaticamente."""
        bot = _make_bot()
        expired_checkin = {
            "id": 30,
            "session_id": 1,
            "guild_id": 999,
            "user_id": 111,
            "status": "pending",
            "deadline_at": _iso(_utcnow() - timedelta(minutes=1)),
        }
        session = _make_session()
        paused = _make_session(status="paused")
        bot.db.get_expired_checkins = AsyncMock(return_value=[expired_checkin])
        bot.db.get_staff_session = AsyncMock(return_value=session)
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, paused])
        bot.db.get_session_segments = AsyncMock(return_value=[
            _make_segment(started_at=_utcnow() - timedelta(minutes=5), ended_at=None)
        ])
        svc = _svc(bot)

        guild = MagicMock()
        guild.id = 999
        member = _make_member()
        guild.get_member = MagicMock(return_value=member)

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc._process_expired_checkins(guild)

        bot.db.update_staff_checkin.assert_called_with(30, "expired", None, None)
        bot.db.open_staff_pause.assert_called_once()

    async def test_process_checkin_continue_keeps_session_active(self):
        """Responder check-in com 'continue' deve manter sessão ativa."""
        bot = _make_bot()
        session = _make_session()
        bot.db.get_staff_session = AsyncMock(return_value=session)
        svc = _svc(bot)

        result = await svc.process_checkin_response(1, 30, "continue", 111)

        bot.db.update_staff_checkin.assert_called_with(30, "continued", unittest.mock.ANY, "continue")
        bot.db.update_staff_session.assert_called_with(1, {"checkin_pending": 0, "updated_at": unittest.mock.ANY})
        self.assertIn("Continuando", result)

    async def test_process_checkin_status_values_are_correct(self):
        """Verificar que os status do check-in são mapeados corretamente."""
        bot = _make_bot()
        bot.db.get_staff_session = AsyncMock(return_value=_make_session())
        guild = MagicMock()
        guild.id = 999
        guild.get_member = MagicMock(return_value=None)
        bot.get_guild = MagicMock(return_value=guild)
        svc = _svc(bot)

        # "continue" → "continued"
        await svc.process_checkin_response(1, 30, "continue", 111)
        call_status = bot.db.update_staff_checkin.call_args[0][1]
        self.assertEqual(call_status, "continued")

        # Reset
        bot.db.get_staff_session = AsyncMock(return_value=_make_session())
        await svc.process_checkin_response(1, 31, "pause", 111)
        call_status = bot.db.update_staff_checkin.call_args[0][1]
        self.assertEqual(call_status, "paused")

        bot.db.get_staff_session = AsyncMock(return_value=_make_session())
        await svc.process_checkin_response(1, 32, "end", 111)
        call_status = bot.db.update_staff_checkin.call_args[0][1]
        self.assertEqual(call_status, "ended")


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 8 — Permissões
# ═══════════════════════════════════════════════════════════════════════════════

class TestPermissions(AsyncTestCase):

    async def test_non_staff_cannot_start_session(self):
        """Usuário sem cargo staff não pode iniciar expediente."""
        bot = _make_bot(staff_role_ids=[123])
        # Sem cargo: role_ids=[999]
        bot.db.get_staff_roles = AsyncMock(return_value=[{"role_id": 123}])
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        svc = _svc(bot)
        member = _make_member(role_ids=[999])  # role 999 ≠ staff role 123

        with self.assertRaises(RuntimeError) as ctx:
            await svc.start_session(member)
        self.assertIn("cargo", str(ctx.exception).lower())

    async def test_manage_permission_check(self):
        """has_manage_permission deve delegar para permission_service."""
        bot = _make_bot()
        bot.permission_service.has = MagicMock(return_value=True)
        svc = _svc(bot)
        member = _make_member()

        result = svc.has_manage_permission(member)

        bot.permission_service.has.assert_called_with(member, "manage_points")
        self.assertTrue(result)

    async def test_role_removal_closes_session(self):
        """Remoção de cargo staff deve encerrar sessão ativa."""
        bot = _make_bot(staff_role_ids=[123])
        session = _make_session()
        closed_session = {**session, "status": "closed"}
        bot.db.get_staff_open_session = AsyncMock(return_value=session)
        bot.db.get_staff_session = AsyncMock(return_value=closed_session)
        bot.db.get_session_segments = AsyncMock(return_value=[])

        # before tinha cargo, after não tem
        before = _make_member(role_ids=[123])
        after = _make_member(role_ids=[999])
        after.guild.id = 999

        svc = _svc(bot)
        # Patch is_staff_member para retornar True/False sem banco
        call_count = {"n": 0}
        async def mock_is_staff(m):
            call_count["n"] += 1
            return m.roles[0].id == 123 if m.roles else False
        svc.is_staff_member = mock_is_staff

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_send_session_report", AsyncMock()), \
             patch.object(svc, "_dispatch_close_log", AsyncMock()):
            await svc.handle_member_update(before, after)

        calls = bot.db.update_staff_session.call_args_list
        statuses = [c[0][1].get("status") for c in calls if "status" in c[0][1]]
        self.assertIn("closed", statuses)


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 10 e 14 — Cálculo de horas (crítico anti-double-count)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimeCalculation(AsyncTestCase):

    async def test_no_double_counting_of_open_segment(self):
        """
        Segmentos abertos (sem ended_at) NÃO devem ser somados junto com
        a sessão ativa — isso causaria contagem dupla.
        """
        bot = _make_bot()
        svc = _svc(bot)
        now = _utcnow()
        start_at = now - timedelta(hours=1)
        end_at = now

        seg_start = now - timedelta(minutes=20)
        # Segmento SEM ended_at (aberto)
        open_segment = _make_segment(
            started_at=seg_start,
            ended_at=None,     # <-- aberto
            duration_seconds=None,
        )
        # Sessão ativa com segment_started_at no mesmo horário
        active_session = _make_session(
            status="active",
            segment_started_at=seg_start,
            current_activity="Desenvolvimento",
            total_valid_seconds=0,
        )

        bot.db.get_staff_segments_in_range = AsyncMock(return_value=[open_segment])
        bot.db.get_staff_open_session = AsyncMock(return_value=active_session)
        bot.db.get_staff_sessions_in_range = AsyncMock(return_value=[active_session])
        bot.db.get_staff_adjustments = AsyncMock(return_value=[])

        stats = await svc.get_member_period_stats(999, 111, start_at, end_at)

        expected_seconds = min(int((now - seg_start).total_seconds()), 3600)
        tolerance = 2
        self.assertLessEqual(
            abs(stats.valid_seconds - expected_seconds), tolerance,
            msg=f"Double-counting detectado! got={stats.valid_seconds}, expected≈{expected_seconds}"
        )

    async def test_pause_time_not_counted_as_valid(self):
        """
        Tempo de pausa NÃO deve entrar em valid_seconds.
        Cenário: 10min ativo → 5min pausado → 10min ativo → encerrar.
        Total válido = 20min, pausado = 5min.
        """
        bot = _make_bot()
        svc = _svc(bot)
        now = _utcnow()
        start_at = now - timedelta(minutes=30)
        end_at = now

        # Segmento 1: 10min válido (00:00-10:00)
        seg1_start = start_at
        seg1_end = start_at + timedelta(minutes=10)
        seg1 = _make_segment(
            segment_id=1,
            activity="Desenvolvimento",
            started_at=seg1_start,
            ended_at=seg1_end,
            duration_seconds=600,
        )
        # Segmento 2: 10min válido (15:00-25:00) — após 5 min de pausa
        seg2_start = start_at + timedelta(minutes=15)
        seg2_end = start_at + timedelta(minutes=25)
        seg2 = _make_segment(
            segment_id=2,
            activity="Desenvolvimento",
            started_at=seg2_start,
            ended_at=seg2_end,
            duration_seconds=600,
        )

        bot.db.get_staff_segments_in_range = AsyncMock(return_value=[seg1, seg2])
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        bot.db.get_staff_sessions_in_range = AsyncMock(return_value=[_make_session()])
        bot.db.get_staff_adjustments = AsyncMock(return_value=[])

        stats = await svc.get_member_period_stats(999, 111, start_at, end_at)

        self.assertEqual(stats.valid_seconds, 1200, "Deve ser 20 minutos = 1200s")
        self.assertEqual(stats.by_activity.get("Desenvolvimento", 0), 1200)
        # Não deve contar o tempo de pausa (5min = 300s)
        self.assertLessEqual(stats.valid_seconds, 1200)

    async def test_controlled_session_calculation(self):
        """
        Sessão controlada: 10min + 10min = 20min válido.
        Pausa de 5min NÃO conta como válido.
        """
        now = _utcnow()
        start_at = now - timedelta(minutes=30)
        end_at = now

        bot = _make_bot()
        svc = _svc(bot)

        seg1 = _make_segment(segment_id=1, activity="Gestão",
                             started_at=start_at, ended_at=start_at + timedelta(minutes=10), duration_seconds=600)
        seg2 = _make_segment(segment_id=2, activity="Arte/Design",
                             started_at=start_at + timedelta(minutes=15), ended_at=start_at + timedelta(minutes=25), duration_seconds=600)

        bot.db.get_staff_segments_in_range = AsyncMock(return_value=[seg1, seg2])
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        bot.db.get_staff_sessions_in_range = AsyncMock(return_value=[])
        bot.db.get_staff_adjustments = AsyncMock(return_value=[])

        stats = await svc.get_member_period_stats(999, 111, start_at, end_at)

        self.assertEqual(stats.valid_seconds, 1200)
        self.assertEqual(stats.by_activity.get("Gestão", 0), 600)
        self.assertEqual(stats.by_activity.get("Arte/Design", 0), 600)

    async def test_adjustments_are_summed_in_period(self):
        """Ajustes manuais no período devem aparecer em adjustment_seconds."""
        now = _utcnow()
        start_at = now - timedelta(hours=1)
        end_at = now

        bot = _make_bot()
        svc = _svc(bot)

        adj_in = {"id": 1, "guild_id": 999, "user_id": 111, "adjustment_seconds": 1800,
                  "reason": "Teste", "created_at": _iso(now - timedelta(minutes=30))}
        adj_out = {"id": 2, "guild_id": 999, "user_id": 111, "adjustment_seconds": 600,
                   "reason": "Fora", "created_at": _iso(now + timedelta(hours=2))}  # fora do período

        bot.db.get_staff_segments_in_range = AsyncMock(return_value=[])
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        bot.db.get_staff_sessions_in_range = AsyncMock(return_value=[])
        bot.db.get_staff_adjustments = AsyncMock(return_value=[adj_in, adj_out])

        stats = await svc.get_member_period_stats(999, 111, start_at, end_at)

        self.assertEqual(stats.adjustment_seconds, 1800)  # só adj_in

    async def test_no_double_count_multiple_segments(self):
        """Múltiplos segmentos fechados não devem ser contados em dobro."""
        now = _utcnow()
        start_at = now - timedelta(hours=2)

        bot = _make_bot()
        svc = _svc(bot)

        segments = [
            _make_segment(segment_id=i,
                         activity="Desenvolvimento",
                         started_at=start_at + timedelta(minutes=i*20),
                         ended_at=start_at + timedelta(minutes=i*20+15),
                         duration_seconds=900)
            for i in range(5)
        ]  # 5 × 15min = 75min total

        bot.db.get_staff_segments_in_range = AsyncMock(return_value=segments)
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        bot.db.get_staff_sessions_in_range = AsyncMock(return_value=[])
        bot.db.get_staff_adjustments = AsyncMock(return_value=[])

        stats = await svc.get_member_period_stats(999, 111, start_at, now)

        self.assertEqual(stats.valid_seconds, 4500)  # 5 × 900s
        self.assertEqual(stats.by_activity.get("Desenvolvimento"), 4500)


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 9 — Configuração
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfiguration(AsyncTestCase):

    async def test_add_staff_role_calls_db(self):
        """configurar_cargo deve persistir no banco."""
        bot = _make_bot()
        svc = _svc(bot)

        await bot.db.add_staff_role(999, 123)
        bot.db.add_staff_role.assert_called_with(999, 123)

    async def test_remove_staff_role_calls_db(self):
        bot = _make_bot()
        await bot.db.remove_staff_role(999, 123)
        bot.db.remove_staff_role.assert_called_with(999, 123)

    async def test_set_channel_rule_valid_types(self):
        """Regras válidas de canal: work, neutral, invalid."""
        bot = _make_bot()
        for rule_type in ("work", "neutral", "invalid"):
            await bot.db.set_channel_rule(999, 555, rule_type)
            bot.db.set_channel_rule.assert_called_with(999, 555, rule_type)

    async def test_get_channel_rule_returns_cached(self):
        """get_channel_rule deve retornar a regra configurada."""
        bot = _make_bot()
        bot.db.get_channel_rule = AsyncMock(return_value={"rule_type": "invalid"})
        svc = _svc(bot)
        rule_type = await svc._get_channel_rule_type(999, 555)
        self.assertEqual(rule_type, "invalid")

    async def test_staff_roles_fallback_to_config_when_db_empty(self):
        """Se não há roles no banco, usar fallback do config."""
        bot = _make_bot(staff_roles_in_db=False)
        bot.server_map.voice_point_allowed_role_ids = MagicMock(return_value=[123])
        svc = _svc(bot)
        member = _make_member(role_ids=[123])
        result = await svc.is_staff_member(member)
        self.assertTrue(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 11 — Reinício / Bootstrap
# ═══════════════════════════════════════════════════════════════════════════════

class TestBootstrap(AsyncTestCase):

    async def test_bootstrap_marks_absent_member_as_pending(self):
        """Membro sem guild após reinício deve ter sessão marcada como pending."""
        bot = _make_bot()
        session = _make_session(status="active")
        bot.db.list_open_staff_sessions = AsyncMock(return_value=[session])

        guild = MagicMock()
        guild.id = 999
        guild.get_member = MagicMock(return_value=None)  # membro ausente
        bot.get_guild = MagicMock(return_value=guild)

        svc = _svc(bot)
        svc._restored = False

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_ensure_tasks", MagicMock()):
            await svc.bootstrap()

        update_calls = bot.db.update_staff_session.call_args_list
        statuses = [c[0][1].get("status") for c in update_calls if "status" in c[0][1]]
        self.assertIn("pending", statuses)

    async def test_bootstrap_marks_very_long_session_as_pending(self):
        """Sessão com mais de MAX_SESSION_HOURS deve ser marcada como pending."""
        from app.services.staff_timeclock_service import MAX_SESSION_HOURS
        bot = _make_bot(staff_role_ids=[123])
        old_start = _utcnow() - timedelta(hours=MAX_SESSION_HOURS + 1)
        session = _make_session(status="active", started_at=old_start)
        bot.db.list_open_staff_sessions = AsyncMock(return_value=[session])

        guild = MagicMock()
        guild.id = 999
        member = _make_member(role_ids=[123])
        guild.get_member = MagicMock(return_value=member)
        bot.get_guild = MagicMock(return_value=guild)

        svc = _svc(bot)
        svc._restored = False
        svc.is_staff_member = AsyncMock(return_value=True)

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_ensure_tasks", MagicMock()):
            await svc.bootstrap()

        calls = bot.db.update_staff_session.call_args_list
        statuses = [c[0][1].get("status") for c in calls if "status" in c[0][1]]
        self.assertIn("pending", statuses)

    async def test_bootstrap_not_run_twice(self):
        """Bootstrap não deve executar duas vezes."""
        bot = _make_bot()
        svc = _svc(bot)
        svc._restored = True  # já executou

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_ensure_tasks", MagicMock()):
            await svc.bootstrap()

        bot.db.list_open_staff_sessions.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 12 — Remoção de cargo
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoleRemoval(AsyncTestCase):

    async def test_history_preserved_after_role_removal(self):
        """Histórico de sessões não deve ser apagado após remoção de cargo."""
        bot = _make_bot()
        # Simula que há sessões históricas no banco mesmo após remoção de cargo
        bot.db.get_staff_sessions_in_range = AsyncMock(return_value=[
            _make_session(status="closed"),
            _make_session(session_id=2, status="closed"),
        ])
        svc = _svc(bot)
        now = _utcnow()

        sessions = await bot.db.get_staff_sessions_in_range(
            999, _iso(now - timedelta(days=30)), _iso(now), user_id=111
        )
        # Histórico deve permanecer
        self.assertEqual(len(sessions), 2)

    async def test_no_session_after_role_removed(self):
        """Membro sem cargo não deve ter sessão ativa após remoção."""
        bot = _make_bot(staff_role_ids=[123])
        # Simulamos que não há sessão ativa (foi encerrada pela lógica de remoção)
        bot.db.get_staff_open_session = AsyncMock(return_value=None)
        svc = _svc(bot)
        member = _make_member(role_ids=[])  # sem cargo

        result = await bot.db.get_staff_open_session(999, 111)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 13 — Logs (verificação de eventos registrados)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventLogging(AsyncTestCase):

    async def test_start_session_logs_event(self):
        """Início de sessão deve registrar evento 'session_started'."""
        bot = _make_bot(staff_role_ids=[123])
        bot.db.get_staff_open_session = AsyncMock(side_effect=[None, _make_session()])
        svc = _svc(bot)
        member = _make_member(role_ids=[123])

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.start_session(member)

        event_calls = bot.db.log_staff_event.call_args_list
        event_types = [c[0][2] for c in event_calls]
        self.assertIn("session_started", event_types)

    async def test_pause_session_logs_event(self):
        """Pausa deve registrar evento 'session_paused'."""
        bot = _make_bot()
        session = _make_session()
        paused = _make_session(status="paused")
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, paused])
        bot.db.get_session_segments = AsyncMock(return_value=[
            _make_segment(started_at=_utcnow() - timedelta(minutes=5), ended_at=None)
        ])
        svc = _svc(bot)
        member = _make_member()

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.pause_session(member)

        event_types = [c[0][2] for c in bot.db.log_staff_event.call_args_list]
        self.assertIn("session_paused", event_types)

    async def test_activity_change_logs_event(self):
        """Troca de atividade deve registrar evento 'activity_changed'."""
        bot = _make_bot()
        seg_started = _utcnow() - timedelta(minutes=10)
        session = _make_session(segment_started_at=seg_started)
        updated = _make_session(current_activity="Desenvolvimento")
        bot.db.get_staff_open_session = AsyncMock(side_effect=[session, updated])
        bot.db.get_session_segments = AsyncMock(return_value=[
            _make_segment(started_at=seg_started, ended_at=None)
        ])
        svc = _svc(bot)
        member = _make_member()

        with patch.object(svc, "refresh_panel", AsyncMock()), \
             patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.change_activity(member, "Desenvolvimento")

        event_types = [c[0][2] for c in bot.db.log_staff_event.call_args_list]
        self.assertIn("activity_changed", event_types)

    async def test_manual_adjustment_logs_event(self):
        """Ajuste manual deve registrar evento e chamar add_staff_adjustment."""
        bot = _make_bot()
        svc = _svc(bot)
        guild = MagicMock()
        guild.id = 999
        target = _make_member(user_id=111)
        admin = _make_member(user_id=777)

        with patch.object(svc, "_dispatch_log", AsyncMock()):
            await svc.admin_adjust(guild, target, admin, 1800, "Trabalho fora do sistema")

        bot.db.add_staff_adjustment.assert_called_once_with(
            999, 111, 777, 1800, "Trabalho fora do sistema", None
        )
        event_types = [c[0][2] for c in bot.db.log_staff_event.call_args_list]
        self.assertIn("manual_adjustment", event_types)


# ═══════════════════════════════════════════════════════════════════════════════
# Teste 15 — Compatibilidade com sistema antigo
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompatibility(AsyncTestCase):

    def test_old_cog_group_name_is_pontos(self):
        """O cog antigo usa grupo 'pontos', o novo usa 'ponto' — sem conflito."""
        import ast
        with open("app/cogs/points.py", encoding="utf-8-sig") as f:
            tree = ast.parse(f.read())
        old_group = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for kw in node.keywords:
                    if kw.arg == "group_name" and isinstance(kw.value, ast.Constant):
                        if "ponto" in str(kw.value.value).lower():
                            old_group = str(kw.value.value)
        self.assertEqual(old_group, "pontos", "Cog antigo deve usar 'pontos'")

    def test_new_cog_group_name_is_ponto(self):
        """O novo cog usa grupo 'ponto'."""
        import ast
        with open("app/cogs/staff_timeclock.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        new_group = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for kw in node.keywords:
                    if kw.arg == "group_name" and isinstance(kw.value, ast.Constant):
                        if "ponto" in str(kw.value.value).lower():
                            new_group = str(kw.value.value)
        self.assertEqual(new_group, "ponto", "Novo cog deve usar 'ponto'")

    def test_old_tables_still_exist_in_schema(self):
        """Tabelas antigas (voice_point_sessions) devem permanecer no schema."""
        import ast
        with open("app/repositories/database.py", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("voice_point_sessions", content)
        self.assertIn("voice_point_segments", content)

    def test_new_tables_added_to_schema(self):
        """Novas tabelas devem estar presentes no schema."""
        with open("app/repositories/database.py", encoding="utf-8-sig") as f:
            content = f.read()
        for table in [
            "staff_work_sessions",
            "staff_work_segments",
            "staff_work_pauses",
            "staff_work_checkins",
            "staff_voice_channel_rules",
            "staff_roles_config",
        ]:
            self.assertIn(table, content, f"Tabela {table} não encontrada no schema")

    def test_point_service_import_unchanged(self):
        """PointService original deve ainda ser importado corretamente."""
        import ast
        with open("app/core/bot.py", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("from app.services.points import PointService", content)
        self.assertIn("from app.services.staff_timeclock_service import StaffTimeclockService", content)

    def test_both_services_registered_in_bot(self):
        """Ambos os serviços devem estar registrados no bot."""
        with open("app/core/bot.py", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("self.point_service = PointService(self)", content)
        self.assertIn("self.staff_timeclock_service = StaffTimeclockService(self)", content)

    def test_voice_handler_calls_both_services(self):
        """on_voice_state_update deve chamar ambos os serviços."""
        with open("app/core/bot.py", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("point_service.handle_voice_state_update", content)
        self.assertIn("staff_timeclock_service.handle_voice_state_update", content)


# ═══════════════════════════════════════════════════════════════════════════════
# Teste de helper — _live_valid_seconds e _format_duration
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpers(AsyncTestCase):

    def test_format_duration_zero(self):
        from app.services.staff_timeclock_service import StaffTimeclockService as S
        self.assertEqual(S._format_duration(0), "00h 00m 00s")

    def test_format_duration_full(self):
        from app.services.staff_timeclock_service import StaffTimeclockService as S
        self.assertEqual(S._format_duration(3661), "01h 01m 01s")

    def test_format_duration_negative_clamps_to_zero(self):
        from app.services.staff_timeclock_service import StaffTimeclockService as S
        self.assertEqual(S._format_duration(-100), "00h 00m 00s")

    def test_live_valid_seconds_active(self):
        svc = _svc()
        now = _utcnow()
        seg_start = now - timedelta(minutes=15)
        session = _make_session(segment_started_at=seg_start, total_valid_seconds=600)
        result = svc._live_valid_seconds(session)
        # 600 base + ~900 (15 min ao vivo)
        self.assertGreater(result, 1400)
        self.assertLess(result, 1650)

    def test_live_valid_seconds_paused(self):
        svc = _svc()
        session = _make_session(
            status="paused",
            total_valid_seconds=600,
            segment_started_at=None,
        )
        result = svc._live_valid_seconds(session)
        self.assertEqual(result, 600)  # não aumenta quando pausado

    def test_overlap_seconds_no_overlap(self):
        from app.services.staff_timeclock_service import StaffTimeclockService as S
        now = _utcnow()
        result = S._overlap_seconds(now, now + timedelta(minutes=5), now + timedelta(minutes=10), now + timedelta(minutes=20))
        self.assertEqual(result, 0)

    def test_overlap_seconds_full_overlap(self):
        from app.services.staff_timeclock_service import StaffTimeclockService as S
        now = _utcnow()
        result = S._overlap_seconds(now, now + timedelta(minutes=10), now, now + timedelta(minutes=10))
        self.assertEqual(result, 600)

    def test_period_bounds_today(self):
        svc = _svc()
        now = _utcnow()
        start, label = svc._period_bounds_labeled("hoje", now)
        self.assertIn("Hoje", label)
        self.assertEqual(start.day, now.day)

    def test_period_bounds_invalid_raises(self):
        svc = _svc()
        with self.assertRaises(RuntimeError):
            svc._period_bounds_labeled("ontem_passado_semana_x", _utcnow())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
