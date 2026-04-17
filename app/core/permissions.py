from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands


class PermissionService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    def has(self, member: discord.Member, permission_key: str) -> bool:
        allowed_roles = set(self.bot.server_map.permission_roles(permission_key))
        if not allowed_roles:
            return member.guild_permissions.administrator
        return any(role.id in allowed_roles for role in member.roles) or member.guild_permissions.administrator

    def require(self, permission_key: str) -> Callable[[discord.Interaction], bool]:
        async def predicate(interaction: discord.Interaction) -> bool:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                raise app_commands.CheckFailure("Este comando só pode ser usado dentro do servidor.")
            if not self.has(interaction.user, permission_key):
                raise app_commands.CheckFailure("Você não possui a permissão exigida para esta ação.")
            return True

        return app_commands.check(predicate)

    def has_any_role_id(self, member: discord.Member, role_ids: list[int]) -> bool:
        allowed = set(int(role_id) for role_id in role_ids)
        if not allowed:
            return False
        return any(role.id in allowed for role in member.roles)

    def denial_embed(self, permission_key: str) -> discord.Embed:
        return self.bot.embeds.error(
            "Acesso Negado",
            (
                "Você não é staff, mas pode virar um se quiser, aí você vai poder clicar nesse botão! 🤭\n"
                "Se quiser saber mais sobre como virar staff, fale com um dos nossos suporte! 😉"
            ),
        )



