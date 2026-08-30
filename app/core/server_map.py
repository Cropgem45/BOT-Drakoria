from __future__ import annotations

from typing import Any


class ServerMap:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @staticmethod
    def _coerce_id(raw: Any) -> int | None:
        if raw in (None, "", 0):
            return None
        return int(raw)

    def guild_id(self) -> int:
        return int(self.config["guild"]["id"])

    def channel(self, key: str) -> int | None:
        return self._coerce_id(self.config.get("channels", {}).get(key))

    def category(self, key: str) -> int | None:
        return self._coerce_id(self.config.get("categories", {}).get(key))

    def role(self, key: str) -> int | None:
        return self._coerce_id(self.config.get("roles", {}).get(key))

    def log_channel(self, key: str) -> int | None:
        return self._coerce_id(self.config.get("logs", {}).get("channels", {}).get(key))

    def permission_roles(self, key: str) -> list[int]:
        roles = self.config.get("permissions", {}).get(key, [])
        return [int(role_id) for role_id in roles]

    def style(self) -> dict[str, Any]:
        return self.config.get("style", {})

    def onboarding_questions(self) -> list[dict[str, Any]]:
        return list(self.config.get("onboarding", {}).get("questions", []))

    def onboarding_open(self) -> bool:
        return bool(self.config.get("onboarding", {}).get("open", True))

    def point_roles(self) -> dict[str, int]:
        return {
            key: int(value)
            for key, value in self.config.get("points", {}).get("reward_roles", {}).items()
        }

    def voice_points(self) -> dict[str, Any]:
        return self.config.get("voice_points", {})

    def voice_points_enabled(self) -> bool:
        return bool(self.voice_points().get("enabled", False))

    def voice_point_panel_channel_id(self) -> int | None:
        return self._coerce_id(self.voice_points().get("panel_channel_id"))

    def voice_point_report_channel_id(self) -> int | None:
        return self._coerce_id(self.voice_points().get("report_channel_id"))

    def voice_point_log_channel_id(self) -> int | None:
        return self._coerce_id(self.voice_points().get("log_channel_id"))

    def voice_point_allowed_role_ids(self) -> list[int]:
        return [int(role_id) for role_id in self.voice_points().get("allowed_role_ids", [])]

    def voice_point_valid_channel_ids(self) -> list[int]:
        return [int(channel_id) for channel_id in self.voice_points().get("valid_voice_channel_ids", [])]

    def voice_point_channel_groups(self) -> dict[str, list[int]]:
        groups = self.voice_points().get("channel_groups", {})
        return {key: [int(channel_id) for channel_id in value] for key, value in groups.items()}

    def voice_point_grace_period_seconds(self) -> int:
        return int(self.voice_points().get("grace_period_seconds", 300))

    def voice_point_channel_group(self, channel_id: int | None) -> str | None:
        if channel_id is None:
            return None
        for group_name, ids in self.voice_point_channel_groups().items():
            if int(channel_id) in ids:
                return group_name
        return None

    def is_valid_voice_point_channel(self, channel_id: int | None) -> bool:
        return channel_id is not None and int(channel_id) in set(self.voice_point_valid_channel_ids())

    def voice_point_channel_ids_by_group(self, group_name: str) -> list[int]:
        return list(self.voice_point_channel_groups().get(group_name, []))

    def voice_point_group_override_by_channel_id(self) -> dict[int, str]:
        mapping = self.voice_points().get("group_override_by_channel_id", {})
        if not isinstance(mapping, dict):
            return {}
        normalized: dict[int, str] = {}
        for channel_id_text, group_name in mapping.items():
            if group_name is None:
                continue
            normalized[int(channel_id_text)] = str(group_name)
        return normalized

    def tickets(self) -> dict[str, Any]:
        return self.config.get("tickets", {})

    def ticket_panel_channel_id(self) -> int | None:
        return self._coerce_id(self.tickets().get("panel_channel_id"))

    def ticket_category_id(self) -> int | None:
        return self._coerce_id(self.tickets().get("category_id")) or self.category("tickets")

    def ticket_log_channel_id(self) -> int | None:
        return self._coerce_id(self.tickets().get("log_channel_id")) or self.log_channel("tickets")

    def ticket_transcript_channel_id(self) -> int | None:
        return self._coerce_id(self.tickets().get("transcript_channel_id")) or self.log_channel("tickets")

    def ticket_support_role_ids(self) -> list[int]:
        role_ids = self.tickets().get("support_role_ids")
        if isinstance(role_ids, list) and role_ids:
            return [int(role_id) for role_id in role_ids]
        support_role_id = self.role("support")
        return [support_role_id] if support_role_id else []

    def ticket_types(self) -> list[dict[str, Any]]:
        types = self.tickets().get("ticket_types", [])
        return [dict(ticket_type) for ticket_type in types if isinstance(ticket_type, dict)]

    def ticket_type(self, key: str) -> dict[str, Any] | None:
        normalized_key = key.strip().lower()
        for ticket_type in self.ticket_types():
            if str(ticket_type.get("key", "")).strip().lower() == normalized_key:
                return ticket_type
        return None

    def ticket_status_labels(self) -> dict[str, str]:
        defaults = {
            "open": "Aberto",
            "in_progress": "Em Atendimento",
            "waiting_user": "Aguardando Usuario",
            "closed": "Encerrado",
        }
        custom = self.tickets().get("status_labels", {})
        if isinstance(custom, dict):
            for key, value in custom.items():
                if isinstance(value, str) and value.strip():
                    defaults[str(key)] = value.strip()
        return defaults

    def ticket_status_label(self, key: str) -> str:
        return self.ticket_status_labels().get(key, key)

    def ticket_allow_one_open_per_user(self) -> bool:
        return bool(self.tickets().get("allow_one_open_ticket_per_user", True))

    def ticket_close_behavior(self) -> str:
        return str(self.tickets().get("close_behavior", "delete")).strip().lower() or "delete"

    def registration_panel(self) -> dict[str, Any]:
        return self.config.get("registration_panel", {})

    def registration_panel_enabled(self) -> bool:
        return bool(self.registration_panel().get("enabled", False))

    def registration_panel_channel_id(self) -> int | None:
        return self._coerce_id(self.registration_panel().get("panel_channel_id"))

    def registration_registered_role_id(self) -> int | None:
        return self._coerce_id(self.registration_panel().get("registered_role_id"))

    def registration_visitor_role_id(self) -> int | None:
        return self._coerce_id(self.registration_panel().get("visitor_role_id"))

    def registration_log_channel_id(self) -> int | None:
        return self._coerce_id(self.registration_panel().get("log_channel_id"))

    def registration_rules_channel_ids(self) -> list[int]:
        return [int(channel_id) for channel_id in self.registration_panel().get("rules_channel_ids", [])]

    def registration_remove_visitor_role(self) -> bool:
        return bool(self.registration_panel().get("remove_visitor_role_on_register", True))

    def member_registration(self) -> dict[str, Any]:
        return self.config.get("member_registration", {})

    def member_registration_enabled(self) -> bool:
        return bool(self.member_registration().get("enabled", False))

    def member_registration_panel_channel_id(self) -> int | None:
        return self._coerce_id(self.member_registration().get("panel_channel_id"))

    def member_registration_member_role_id(self) -> int | None:
        return self._coerce_id(self.member_registration().get("member_role_id"))

    def member_registration_log_channel_id(self) -> int | None:
        return self._coerce_id(self.member_registration().get("log_channel_id"))

    def member_registration_completed_channel_id(self) -> int | None:
        configured = self._coerce_id(self.member_registration().get("completed_channel_id"))
        if configured:
            return configured
        return 1487647471520714763

    def member_registration_minimum_age(self) -> int:
        return int(self.member_registration().get("minimum_age", 16))

    def member_registration_rename_member_on_success(self) -> bool:
        return bool(self.member_registration().get("rename_member_on_success", True))

    def member_registration_auto_reject_under_minimum_age(self) -> bool:
        return bool(self.member_registration().get("auto_reject_under_minimum_age", True))

    def beta_program(self) -> dict[str, Any]:
        return self.config.get("beta_program", {})

    def beta_program_enabled(self) -> bool:
        return bool(self.beta_program().get("enabled", False))

    def beta_program_panel_channel_id(self) -> int | None:
        return self._coerce_id(self.beta_program().get("panel_channel_id"))

    def beta_program_application_channel_id(self) -> int | None:
        return self._coerce_id(self.beta_program().get("application_channel_id"))

    def beta_program_card_channel_id(self) -> int | None:
        return self._coerce_id(self.beta_program().get("card_channel_id"))

    def beta_program_log_channel_id(self) -> int | None:
        return self._coerce_id(self.beta_program().get("log_channel_id"))

    def beta_program_role_id(self) -> int | None:
        return self._coerce_id(self.beta_program().get("beta_role_id"))

    def beta_program_allow_reapply_after_rejection(self) -> bool:
        return bool(self.beta_program().get("allow_reapply_after_rejection", True))

    def beta_program_send_dm_on_approval(self) -> bool:
        return bool(self.beta_program().get("send_dm_on_approval", True))

    def beta_program_send_dm_on_rejection(self) -> bool:
        return bool(self.beta_program().get("send_dm_on_rejection", True))

    def beta_program_generate_tester_card(self) -> bool:
        return bool(self.beta_program().get("generate_tester_card", True))

    def server_status(self) -> dict[str, Any]:
        return self.config.get("server_status", {})

    def server_status_enabled(self) -> bool:
        return bool(self.server_status().get("enabled", False))

    def server_status_channel_id(self) -> int | None:
        return self._coerce_id(self.server_status().get("channel_id"))

    def server_status_update_interval_seconds(self) -> int:
        return max(30, int(self.server_status().get("update_interval_seconds", 60)))

    def server_status_name(self) -> str:
        raw = self.server_status().get("name")
        return str(raw).strip() if isinstance(raw, str) and raw.strip() else "DRAKORIA MMORPG"

    def server_status_state(self) -> str:
        raw = self.server_status().get("status")
        return str(raw).strip() if isinstance(raw, str) and raw.strip() else "Online"

    def server_status_players_source(self) -> str:
        raw = str(self.server_status().get("players_source", "members")).strip().lower()
        return raw if raw in {"members", "voice", "manual", "minecraft"} else "members"

    def server_status_minecraft_host(self) -> str | None:
        raw = self.server_status().get("minecraft_host")
        if not isinstance(raw, str) or not raw.strip():
            return None
        return raw.strip()

    def server_status_minecraft_port(self) -> int:
        return int(self.server_status().get("minecraft_port", 25565))

    def server_status_minecraft_timeout_seconds(self) -> float:
        return max(1.0, float(self.server_status().get("minecraft_timeout_seconds", 5)))

    def server_status_manual_players_online(self) -> int:
        return max(0, int(self.server_status().get("manual_players_online", 0)))

    def server_status_max_players(self) -> int | None:
        raw = self.server_status().get("max_players")
        if raw in (None, "", 0):
            return None
        return max(1, int(raw))

    def server_status_voice_channel_ids(self) -> list[int]:
        return [int(channel_id) for channel_id in self.server_status().get("voice_channel_ids", [])]

    def server_status_description(self) -> str:
        raw = self.server_status().get("description")
        return str(raw).strip() if isinstance(raw, str) and raw.strip() else "Acompanhe aqui o estado oficial do reino."

    def discord_guilds(self) -> dict[str, Any]:
        return self.config.get("discord_guilds", {})

    def discord_guilds_enabled(self) -> bool:
        return bool(self.discord_guilds().get("enabled", False))

    def discord_guilds_auto_approve_creation(self) -> bool:
        return bool(self.discord_guilds().get("auto_approve_creation", False))

    def discord_guilds_recruitment_channel_id(self) -> int | None:
        return self._coerce_id(self.discord_guilds().get("recruitment_channel_id"))

    def discord_guilds_mural_channel_id(self) -> int | None:
        return self._coerce_id(self.discord_guilds().get("mural_channel_id"))

    def discord_guilds_staff_review_channel_id(self) -> int | None:
        return self._coerce_id(self.discord_guilds().get("staff_review_channel_id"))

    def discord_guilds_allowed_emojis(self) -> list[str]:
        return [str(item).strip() for item in self.discord_guilds().get("allowed_emojis", []) if str(item).strip()]

    def discord_guilds_staff_exempt_role_ids(self) -> list[int]:
        return [int(role_id) for role_id in self.discord_guilds().get("staff_exempt_role_ids", [])]

    def discord_guilds_nickname_style(self) -> str:
        style = str(self.discord_guilds().get("nickname_style", "full")).strip().lower()
        return style if style in {"full", "tag"} else "full"

    def discord_guilds_min_name_length(self) -> int:
        return max(1, int(self.discord_guilds().get("min_name_length", 3)))

    def discord_guilds_max_name_length(self) -> int:
        return max(self.discord_guilds_min_name_length(), int(self.discord_guilds().get("max_name_length", 24)))

    def discord_guilds_rename_cooldown_hours(self) -> int:
        return max(0, int(self.discord_guilds().get("rename_cooldown_hours", 72)))

    def discord_guilds_emblem_cooldown_hours(self) -> int:
        return max(0, int(self.discord_guilds().get("emblem_cooldown_hours", 24)))

    def discord_guilds_minimum_members_for_officialization(self) -> int:
        return max(0, int(self.discord_guilds().get("minimum_members_for_officialization", 3)))

    def announcements(self) -> dict[str, Any]:
        return self.config.get("announcements", {})

    def announcements_enabled(self) -> bool:
        return bool(self.announcements().get("enabled", True))

    def announcements_log_channel_id(self) -> int | None:
        return self._coerce_id(self.announcements().get("log_channel_id"))

    def announcements_allowed_role_ids(self) -> list[int]:
        return [int(role_id) for role_id in self.announcements().get("allowed_role_ids", [])]

    def announcements_embed_color(self) -> int | None:
        raw = self.announcements().get("embed_color")
        if raw in (None, ""):
            return None
        return int(raw)

    def announcements_logo_url(self) -> str | None:
        raw = self.announcements().get("logo_url")
        if not isinstance(raw, str) or not raw.strip():
            return None
        return raw.strip()

    def announcements_large_logo_url(self) -> str | None:
        raw = self.announcements().get("large_logo_url")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return self.announcements_logo_url()

    def announcements_default_footer(self) -> str:
        raw = self.announcements().get("default_footer")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return "Drakoria - Comunicacao Oficial"

    def management_dashboard(self) -> dict[str, Any]:
        return self.config.get("management_dashboard", {})

    def management_dashboard_enabled(self) -> bool:
        return bool(self.management_dashboard().get("enabled", False))

    def management_dashboard_channel_id(self) -> int | None:
        return self._coerce_id(self.management_dashboard().get("dashboard_channel_id"))

    def management_dashboard_allowed_role_ids(self) -> list[int]:
        return [int(role_id) for role_id in self.management_dashboard().get("allowed_role_ids", [])]

    def management_dashboard_show_weekly_metrics(self) -> bool:
        return bool(self.management_dashboard().get("show_weekly_metrics", True))

    def management_dashboard_show_monthly_metrics(self) -> bool:
        return bool(self.management_dashboard().get("show_monthly_metrics", True))

    def management_dashboard_show_alerts(self) -> bool:
        return bool(self.management_dashboard().get("show_alerts", True))

    def staff_timeclock(self) -> dict[str, Any]:
        return self.config.get("staff_timeclock", {})

    def staff_timeclock_enabled(self) -> bool:
        return bool(self.staff_timeclock().get("enabled", True))

    def staff_timeclock_panel_channel_id(self) -> int | None:
        raw = self.staff_timeclock().get("panel_channel_id")
        if raw in (None, "", 0):
            return self.voice_point_panel_channel_id()
        return int(raw)

    def staff_timeclock_log_channel_id(self) -> int | None:
        raw = self.staff_timeclock().get("logs_channel_id", self.staff_timeclock().get("log_channel_id"))
        if raw in (None, "", 0):
            return self.voice_point_log_channel_id()
        return int(raw)

    def staff_timeclock_control_channel_id(self) -> int | None:
        raw = self.staff_timeclock().get("control_channel_id")
        if raw in (None, "", 0):
            return self.staff_timeclock_panel_channel_id()
        return int(raw)

    def staff_timeclock_reminder_after_seconds(self) -> int:
        return int(self.staff_timeclock().get("reminder_after_seconds", self.staff_timeclock().get("reminder_after_minutes", 3) * 60))

    def staff_timeclock_admin_alert_after_seconds(self) -> int:
        return int(self.staff_timeclock().get("admin_alert_after_seconds", self.staff_timeclock().get("admin_alert_after_minutes", 10) * 60))

    def staff_timeclock_auto_pause_delay_seconds(self) -> int:
        return int(self.staff_timeclock().get("auto_pause_delay_seconds", self.staff_timeclock().get("auto_pause_delay_minutes", 2) * 60))

    def staff_timeclock_alert_cooldown_seconds(self) -> int:
        return int(self.staff_timeclock().get("alert_cooldown_seconds", self.staff_timeclock().get("alert_cooldown_minutes", 10) * 60))

    def staff_timeclock_checkin_interval_in_call(self) -> int:
        return int(self.staff_timeclock().get("checkin_interval_in_call_seconds", 3600))

    def staff_timeclock_checkin_interval_external(self) -> int:
        return int(self.staff_timeclock().get("checkin_interval_external_seconds", 1800))

    def staff_timeclock_checkin_timeout(self) -> int:
        return int(self.staff_timeclock().get("checkin_timeout_seconds", 300))

    def staff_timeclock_max_session_hours(self) -> int:
        return int(self.staff_timeclock().get("max_session_hours", 12))

    def staff_timeclock_manage_role_ids(self) -> list[int]:
        return [int(rid) for rid in self.staff_timeclock().get("manage_timeclock_role_ids", [])]
