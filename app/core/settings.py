from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(slots=True)
class RuntimeSettings:
    token: str
    config_path: Path
    database_path: Path
    log_level: str


class ConfigError(RuntimeError):
    """Erro de configuracao do reino."""


REQUIRED_CHANNELS = ("welcome",)
REQUIRED_CATEGORIES = ("tickets",)
REQUIRED_ROLES = ("visitor", "support")
REQUIRED_LOG_CHANNELS = ("tickets", "points", "announcements")
REQUIRED_PERMISSION_KEYS = (
    "publish_panel",
    "manage_tickets",
    "manage_points",
    "manage_beta_program",
    "publish_announcements",
    "view_server_map",
)
VOICE_POINT_GROUPS = ("attendance_channels", "meeting_channels", "leadership_channels", "development_channels")
REQUIRED_TICKET_TYPE_KEYS = ("key", "label", "description", "emoji")
VALID_TICKET_CLOSE_BEHAVIORS = {"delete", "archive"}
VALID_TICKET_STATUS_KEYS = {"open", "in_progress", "waiting_user", "closed"}
REQUIRED_REGISTRATION_PANEL_KEYS = (
    "enabled",
    "panel_channel_id",
    "registered_role_id",
    "visitor_role_id",
    "log_channel_id",
    "rules_channel_ids",
    "remove_visitor_role_on_register",
)
REQUIRED_MEMBER_REGISTRATION_KEYS = (
    "enabled",
    "panel_channel_id",
    "member_role_id",
    "log_channel_id",
    "minimum_age",
    "rename_member_on_success",
    "auto_reject_under_minimum_age",
)
REQUIRED_ANNOUNCEMENT_KEYS = (
    "enabled",
    "log_channel_id",
    "allowed_role_ids",
    "embed_color",
    "logo_url",
    "default_footer",
)
REQUIRED_MANAGEMENT_DASHBOARD_KEYS = (
    "enabled",
    "dashboard_channel_id",
    "allowed_role_ids",
    "show_weekly_metrics",
    "show_monthly_metrics",
    "show_alerts",
)
REQUIRED_BETA_PROGRAM_KEYS = (
    "enabled",
    "panel_channel_id",
    "application_channel_id",
    "card_channel_id",
    "log_channel_id",
    "beta_role_id",
    "allow_reapply_after_rejection",
    "send_dm_on_approval",
    "send_dm_on_rejection",
    "generate_tester_card",
)


def _is_positive_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _validate_hex_color(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if not text.startswith("0x"):
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True


def _validate_id_list(path: str, value: Any, issues: list[str], *, allow_empty: bool = False) -> list[int]:
    if not isinstance(value, list):
        issues.append(f"Campo invalido: {path} deve ser uma lista de IDs")
        return []
    if not value and not allow_empty:
        issues.append(f"Campo obrigatorio invalido: {path} deve conter ao menos um ID")
        return []
    ids: list[int] = []
    for index, item in enumerate(value, start=1):
        if not _is_positive_int(item):
            issues.append(f"Campo invalido: {path}[{index}] deve conter um ID numerico valido")
            continue
        ids.append(int(item))
    return ids


def validate_config(data: dict[str, Any]) -> None:
    issues: list[str] = []

    guild = data.get("guild")
    if not isinstance(guild, dict):
        issues.append("Secao obrigatoria ausente ou invalida: guild")
    elif not _is_positive_int(guild.get("id")):
        issues.append("Campo obrigatorio invalido: guild.id deve ser um ID numerico maior que zero")

    style = data.get("style", {})
    if not isinstance(style, dict):
        issues.append("Secao invalida: style deve ser um objeto JSON")
    else:
        for color_key in ("primary_color", "success_color", "warning_color", "error_color"):
            if color_key in style and not _validate_hex_color(style[color_key]):
                issues.append(f"Campo invalido: style.{color_key} deve estar no formato 0xRRGGBB")
        footer_text = style.get("footer_text")
        if footer_text is not None and (not isinstance(footer_text, str) or not footer_text.strip()):
            issues.append("Campo invalido: style.footer_text nao pode ser vazio")

    channels = data.get("channels")
    if not isinstance(channels, dict):
        issues.append("Secao obrigatoria ausente ou invalida: channels")
    else:
        for key in REQUIRED_CHANNELS:
            if not _is_positive_int(channels.get(key)):
                issues.append(f"Campo obrigatorio invalido: channels.{key} deve conter um ID valido")

    categories = data.get("categories")
    if not isinstance(categories, dict):
        issues.append("Secao obrigatoria ausente ou invalida: categories")
    else:
        for key in REQUIRED_CATEGORIES:
            if not _is_positive_int(categories.get(key)):
                issues.append(f"Campo obrigatorio invalido: categories.{key} deve conter um ID valido")

    roles = data.get("roles")
    if not isinstance(roles, dict):
        issues.append("Secao obrigatoria ausente ou invalida: roles")
    else:
        for key in REQUIRED_ROLES:
            if not _is_positive_int(roles.get(key)):
                issues.append(f"Campo obrigatorio invalido: roles.{key} deve conter um ID valido")

    logs = data.get("logs")
    log_channels = logs.get("channels") if isinstance(logs, dict) else None
    if not isinstance(log_channels, dict):
        issues.append("Secao obrigatoria ausente ou invalida: logs.channels")
    else:
        for key in REQUIRED_LOG_CHANNELS:
            if not _is_positive_int(log_channels.get(key)):
                issues.append(f"Campo obrigatorio invalido: logs.channels.{key} deve conter um ID valido")

    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        issues.append("Secao obrigatoria ausente ou invalida: permissions")
    else:
        for key in REQUIRED_PERMISSION_KEYS:
            _validate_id_list(f"permissions.{key}", permissions.get(key), issues)

    onboarding = data.get("onboarding")
    if onboarding is not None:
        if not isinstance(onboarding, dict):
            issues.append("Secao invalida: onboarding deve ser um objeto quando informada")
        else:
            if not isinstance(onboarding.get("open", True), bool):
                issues.append("Campo invalido: onboarding.open deve ser true ou false")
            questions = onboarding.get("questions")
            if questions is not None:
                if not isinstance(questions, list) or not questions:
                    issues.append("Campo invalido: onboarding.questions deve conter entre 1 e 5 perguntas quando informado")
                else:
                    if len(questions) > 5:
                        issues.append("Campo invalido: onboarding.questions aceita no maximo 5 perguntas por modal")
                    for index, question in enumerate(questions, start=1):
                        prefix = f"onboarding.questions[{index}]"
                        if not isinstance(question, dict):
                            issues.append(f"Campo invalido: {prefix} deve ser um objeto")
                            continue
                        label = question.get("label")
                        if not isinstance(label, str) or not label.strip():
                            issues.append(f"Campo obrigatorio invalido: {prefix}.label nao pode ser vazio")
                        max_length = question.get("max_length", 500)
                        if not isinstance(max_length, int) or max_length <= 0 or max_length > 4000:
                            issues.append(f"Campo invalido: {prefix}.max_length deve ser um inteiro entre 1 e 4000")
                        for bool_key in ("required", "paragraph"):
                            if bool_key in question and not isinstance(question[bool_key], bool):
                                issues.append(f"Campo invalido: {prefix}.{bool_key} deve ser true ou false")

    points = data.get("points", {})
    if not isinstance(points, dict):
        issues.append("Secao invalida: points deve ser um objeto JSON")
    else:
        reward_roles = points.get("reward_roles", {})
        if not isinstance(reward_roles, dict):
            issues.append("Campo invalido: points.reward_roles deve ser um objeto de marcos para cargos")
        else:
            for threshold, role_id in reward_roles.items():
                try:
                    threshold_value = int(threshold)
                except (TypeError, ValueError):
                    issues.append(f"Campo invalido: points.reward_roles possui marco nao numerico ({threshold})")
                    continue
                if threshold_value <= 0:
                    issues.append(f"Campo invalido: points.reward_roles possui marco nao positivo ({threshold})")
                if not _is_positive_int(role_id):
                    issues.append(f"Campo invalido: points.reward_roles[{threshold}] deve conter um ID de cargo valido")

    voice_points = data.get("voice_points")
    if not isinstance(voice_points, dict):
        issues.append("Secao obrigatoria ausente ou invalida: voice_points")
    else:
        enabled = voice_points.get("enabled")
        if not isinstance(enabled, bool):
            issues.append("Campo invalido: voice_points.enabled deve ser true ou false")
        for field_name in ("panel_channel_id", "report_channel_id", "log_channel_id"):
            if not _is_positive_int(voice_points.get(field_name)):
                issues.append(f"Campo obrigatorio invalido: voice_points.{field_name} deve conter um ID valido")

        allowed_role_ids = _validate_id_list("voice_points.allowed_role_ids", voice_points.get("allowed_role_ids"), issues)
        valid_voice_channel_ids = _validate_id_list(
            "voice_points.valid_voice_channel_ids",
            voice_points.get("valid_voice_channel_ids"),
            issues,
        )

        grace_period_seconds = voice_points.get("grace_period_seconds")
        if not isinstance(grace_period_seconds, int) or grace_period_seconds < 30:
            issues.append("Campo invalido: voice_points.grace_period_seconds deve ser inteiro e no minimo 30")

        channel_groups = voice_points.get("channel_groups")
        if not isinstance(channel_groups, dict):
            issues.append("Secao obrigatoria ausente ou invalida: voice_points.channel_groups")
        else:
            grouped_ids: set[int] = set()
            for key in VOICE_POINT_GROUPS:
                ids = _validate_id_list(f"voice_points.channel_groups.{key}", channel_groups.get(key), issues, allow_empty=True)
                duplicates = grouped_ids.intersection(ids)
                if duplicates:
                    issues.append(
                        f"Campo invalido: voice_points.channel_groups.{key} reutiliza IDs ja classificados ({sorted(duplicates)})"
                    )
                grouped_ids.update(ids)

            missing_from_groups = set(valid_voice_channel_ids) - grouped_ids
            unknown_in_groups = grouped_ids - set(valid_voice_channel_ids)
            if missing_from_groups:
                issues.append(
                    "Campo invalido: voice_points.valid_voice_channel_ids possui canais sem classificacao em channel_groups "
                    f"({sorted(missing_from_groups)})"
                )
            if unknown_in_groups:
                issues.append(
                    "Campo invalido: voice_points.channel_groups referencia canais fora de valid_voice_channel_ids "
                    f"({sorted(unknown_in_groups)})"
                )

        group_override = voice_points.get("group_override_by_channel_id", {})
        if group_override and not isinstance(group_override, dict):
            issues.append("Campo invalido: voice_points.group_override_by_channel_id deve ser um objeto {channel_id: group_name}")
        elif isinstance(group_override, dict):
            valid_groups = set(VOICE_POINT_GROUPS)
            for raw_channel_id, raw_group_name in group_override.items():
                if not _is_positive_int(raw_channel_id):
                    issues.append(
                        "Campo invalido: voice_points.group_override_by_channel_id possui chave de canal invalida "
                        f"({raw_channel_id})"
                    )
                    continue
                channel_id = int(raw_channel_id)
                if channel_id not in set(valid_voice_channel_ids):
                    issues.append(
                        "Campo invalido: voice_points.group_override_by_channel_id referencia canal fora de "
                        f"valid_voice_channel_ids ({channel_id})"
                    )
                if str(raw_group_name) not in valid_groups:
                    issues.append(
                        "Campo invalido: voice_points.group_override_by_channel_id possui grupo invalido "
                        f"({raw_group_name}) para canal {channel_id}"
                    )

        duplicate_roles = len(set(allowed_role_ids)) != len(allowed_role_ids)
        duplicate_channels = len(set(valid_voice_channel_ids)) != len(valid_voice_channel_ids)
        if duplicate_roles:
            issues.append("Campo invalido: voice_points.allowed_role_ids contem IDs duplicados")
        if duplicate_channels:
            issues.append("Campo invalido: voice_points.valid_voice_channel_ids contem IDs duplicados")

    tickets = data.get("tickets")
    if not isinstance(tickets, dict):
        issues.append("Secao obrigatoria ausente ou invalida: tickets")
    else:
        for field_name in ("panel_channel_id", "category_id", "log_channel_id", "transcript_channel_id"):
            if not _is_positive_int(tickets.get(field_name)):
                issues.append(f"Campo obrigatorio invalido: tickets.{field_name} deve conter um ID valido")

        support_role_ids = _validate_id_list("tickets.support_role_ids", tickets.get("support_role_ids"), issues)
        if len(set(support_role_ids)) != len(support_role_ids):
            issues.append("Campo invalido: tickets.support_role_ids contem IDs duplicados")

        allow_one_open = tickets.get("allow_one_open_ticket_per_user")
        if not isinstance(allow_one_open, bool):
            issues.append("Campo invalido: tickets.allow_one_open_ticket_per_user deve ser true ou false")

        close_behavior = str(tickets.get("close_behavior", "")).strip().lower()
        if close_behavior not in VALID_TICKET_CLOSE_BEHAVIORS:
            issues.append(
                "Campo invalido: tickets.close_behavior deve ser um destes valores: "
                + ", ".join(sorted(VALID_TICKET_CLOSE_BEHAVIORS))
            )

        ticket_types = tickets.get("ticket_types")
        if not isinstance(ticket_types, list) or len(ticket_types) != 5:
            issues.append("Campo obrigatorio invalido: tickets.ticket_types deve conter exatamente 5 categorias de suporte")
        else:
            seen_type_keys: set[str] = set()
            for index, ticket_type in enumerate(ticket_types, start=1):
                prefix = f"tickets.ticket_types[{index}]"
                if not isinstance(ticket_type, dict):
                    issues.append(f"Campo invalido: {prefix} deve ser um objeto")
                    continue
                for key in REQUIRED_TICKET_TYPE_KEYS:
                    value = ticket_type.get(key)
                    if not isinstance(value, str) or not value.strip():
                        issues.append(f"Campo obrigatorio invalido: {prefix}.{key} nao pode ser vazio")
                raw_key = str(ticket_type.get("key", "")).strip().lower()
                if raw_key:
                    if raw_key in seen_type_keys:
                        issues.append(f"Campo invalido: tickets.ticket_types possui chave duplicada ({raw_key})")
                    seen_type_keys.add(raw_key)

        status_labels = tickets.get("status_labels", {})
        if status_labels and not isinstance(status_labels, dict):
            issues.append("Campo invalido: tickets.status_labels deve ser um objeto com os nomes dos estados")
        elif isinstance(status_labels, dict):
            unknown_status_keys = sorted(set(status_labels) - VALID_TICKET_STATUS_KEYS)
            if unknown_status_keys:
                issues.append(
                    "Campo invalido: tickets.status_labels possui estados desconhecidos "
                    f"({', '.join(unknown_status_keys)})"
                )
            for status_key, status_label in status_labels.items():
                if not isinstance(status_label, str) or not status_label.strip():
                    issues.append(f"Campo invalido: tickets.status_labels.{status_key} nao pode ser vazio")

    member_registration = data.get("member_registration")
    if not isinstance(member_registration, dict):
        issues.append("Secao obrigatoria ausente ou invalida: member_registration")
    else:
        for key in REQUIRED_MEMBER_REGISTRATION_KEYS:
            if key not in member_registration:
                issues.append(f"Campo obrigatorio ausente: member_registration.{key}")
        if not isinstance(member_registration.get("enabled"), bool):
            issues.append("Campo invalido: member_registration.enabled deve ser true ou false")
        for field_name in ("panel_channel_id", "member_role_id", "log_channel_id"):
            if not _is_positive_int(member_registration.get(field_name)):
                issues.append(f"Campo obrigatorio invalido: member_registration.{field_name} deve conter um ID valido")
        completed_channel_id = member_registration.get("completed_channel_id")
        if completed_channel_id is not None and not _is_positive_int(completed_channel_id):
            issues.append("Campo invalido: member_registration.completed_channel_id deve conter um ID valido")
        minimum_age = member_registration.get("minimum_age")
        if not isinstance(minimum_age, int) or minimum_age < 13:
            issues.append("Campo invalido: member_registration.minimum_age deve ser inteiro e no minimo 13")
        for bool_key in ("rename_member_on_success", "auto_reject_under_minimum_age"):
            if not isinstance(member_registration.get(bool_key), bool):
                issues.append(f"Campo invalido: member_registration.{bool_key} deve ser true ou false")

    registration_panel = data.get("registration_panel")
    if not isinstance(registration_panel, dict):
        issues.append("Secao obrigatoria ausente ou invalida: registration_panel")
    else:
        for key in REQUIRED_REGISTRATION_PANEL_KEYS:
            if key not in registration_panel:
                issues.append(f"Campo obrigatorio ausente: registration_panel.{key}")
        enabled = registration_panel.get("enabled")
        if not isinstance(enabled, bool):
            issues.append("Campo invalido: registration_panel.enabled deve ser true ou false")

        for field_name in ("panel_channel_id", "registered_role_id", "visitor_role_id", "log_channel_id"):
            if not _is_positive_int(registration_panel.get(field_name)):
                issues.append(f"Campo obrigatorio invalido: registration_panel.{field_name} deve conter um ID valido")

        rules_ids = _validate_id_list(
            "registration_panel.rules_channel_ids",
            registration_panel.get("rules_channel_ids"),
            issues,
        )
        if len(set(rules_ids)) != len(rules_ids):
            issues.append("Campo invalido: registration_panel.rules_channel_ids contem IDs duplicados")

        remove_visitor = registration_panel.get("remove_visitor_role_on_register")
        if not isinstance(remove_visitor, bool):
            issues.append("Campo invalido: registration_panel.remove_visitor_role_on_register deve ser true ou false")

    announcements = data.get("announcements")
    if not isinstance(announcements, dict):
        issues.append("Secao obrigatoria ausente ou invalida: announcements")
    else:
        for key in REQUIRED_ANNOUNCEMENT_KEYS:
            if key not in announcements:
                issues.append(f"Campo obrigatorio ausente: announcements.{key}")

        enabled = announcements.get("enabled")
        if not isinstance(enabled, bool):
            issues.append("Campo invalido: announcements.enabled deve ser true ou false")

        if not _is_positive_int(announcements.get("log_channel_id")):
            issues.append("Campo obrigatorio invalido: announcements.log_channel_id deve conter um ID valido")

        allowed_role_ids = _validate_id_list("announcements.allowed_role_ids", announcements.get("allowed_role_ids"), issues)
        if len(set(allowed_role_ids)) != len(allowed_role_ids):
            issues.append("Campo invalido: announcements.allowed_role_ids contem IDs duplicados")

        embed_color = announcements.get("embed_color")
        if not isinstance(embed_color, int) or embed_color <= 0:
            issues.append("Campo invalido: announcements.embed_color deve ser inteiro positivo")

        logo_url = announcements.get("logo_url")
        if not isinstance(logo_url, str) or not logo_url.strip():
            issues.append("Campo obrigatorio invalido: announcements.logo_url nao pode ser vazio")

        large_logo_url = announcements.get("large_logo_url")
        if large_logo_url is not None and (not isinstance(large_logo_url, str) or not large_logo_url.strip()):
            issues.append("Campo invalido: announcements.large_logo_url deve ser string nao vazia quando informado")

        default_footer = announcements.get("default_footer")
        if not isinstance(default_footer, str) or not default_footer.strip():
            issues.append("Campo obrigatorio invalido: announcements.default_footer nao pode ser vazio")

    management_dashboard = data.get("management_dashboard")
    if not isinstance(management_dashboard, dict):
        issues.append("Secao obrigatoria ausente ou invalida: management_dashboard")
    else:
        for key in REQUIRED_MANAGEMENT_DASHBOARD_KEYS:
            if key not in management_dashboard:
                issues.append(f"Campo obrigatorio ausente: management_dashboard.{key}")
        if not isinstance(management_dashboard.get("enabled"), bool):
            issues.append("Campo invalido: management_dashboard.enabled deve ser true ou false")
        if not _is_positive_int(management_dashboard.get("dashboard_channel_id")):
            issues.append("Campo obrigatorio invalido: management_dashboard.dashboard_channel_id deve conter um ID valido")
        allowed_role_ids = _validate_id_list(
            "management_dashboard.allowed_role_ids",
            management_dashboard.get("allowed_role_ids"),
            issues,
        )
        if len(set(allowed_role_ids)) != len(allowed_role_ids):
            issues.append("Campo invalido: management_dashboard.allowed_role_ids contem IDs duplicados")
        for key in ("show_weekly_metrics", "show_monthly_metrics", "show_alerts"):
            if not isinstance(management_dashboard.get(key), bool):
                issues.append(f"Campo invalido: management_dashboard.{key} deve ser true ou false")

    beta_program = data.get("beta_program")
    if not isinstance(beta_program, dict):
        issues.append("Secao obrigatoria ausente ou invalida: beta_program")
    else:
        for key in REQUIRED_BETA_PROGRAM_KEYS:
            if key not in beta_program:
                issues.append(f"Campo obrigatorio ausente: beta_program.{key}")
        if not isinstance(beta_program.get("enabled"), bool):
            issues.append("Campo invalido: beta_program.enabled deve ser true ou false")
        for field_name in (
            "panel_channel_id",
            "application_channel_id",
            "card_channel_id",
            "log_channel_id",
            "beta_role_id",
        ):
            if not _is_positive_int(beta_program.get(field_name)):
                issues.append(f"Campo obrigatorio invalido: beta_program.{field_name} deve conter um ID valido")
        for bool_key in (
            "allow_reapply_after_rejection",
            "send_dm_on_approval",
            "send_dm_on_rejection",
            "generate_tester_card",
        ):
            if not isinstance(beta_program.get(bool_key), bool):
                issues.append(f"Campo invalido: beta_program.{bool_key} deve ser true ou false")

    if issues:
        formatted = "\n".join(f"- {issue}" for issue in issues)
        raise ConfigError(
            "A configuracao do reino contem problemas que impedem uma inicializacao segura:\n"
            f"{formatted}"
        )


class ConfigManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._cache: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise ConfigError(f"Arquivo de configuracao nao encontrado: {self.path}")
        try:
            with self.path.open("r", encoding="utf-8") as file:
                self._cache = json.load(file)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                "Falha ao interpretar o JSON de configuracao "
                f"{self.path} na linha {exc.lineno}, coluna {exc.colno}: {exc.msg}"
            ) from exc
        validate_config(self._cache)
        return self._cache

    @property
    def data(self) -> dict[str, Any]:
        if not self._cache:
            return self.load()
        return self._cache


def load_runtime_settings() -> RuntimeSettings:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    config_path = Path(os.getenv("CONFIG_PATH", "config/example_config.json")).resolve()
    database_path = Path(os.getenv("DATABASE_PATH", "data/drakoria.sqlite3")).resolve()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    if not token:
        raise ConfigError("A variavel DISCORD_TOKEN nao foi definida.")
    if not config_path.exists():
        raise ConfigError(f"O arquivo CONFIG_PATH apontado nao existe: {config_path}")

    database_path.parent.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        token=token,
        config_path=config_path,
        database_path=database_path,
        log_level=log_level,
    )

