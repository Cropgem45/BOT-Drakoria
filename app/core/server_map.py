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

