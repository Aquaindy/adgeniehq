from enum import StrEnum

from app.core.exceptions import AdVantaError


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MARKETER = "marketer"
    ANALYST = "analyst"
    VIEWER = "viewer"


class MemberStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    DISABLED = "disabled"


class PermissionDeniedError(AdVantaError):
    status_code = 403
    code = "permission_denied"


# Hierarchy used for "at-least" checks. Higher index = more privilege.
ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.ANALYST: 1,
    Role.MARKETER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


def role_at_least(role: Role, minimum: Role) -> bool:
    return ROLE_RANK[role] >= ROLE_RANK[minimum]


def require_role_at_least(role: Role, minimum: Role) -> None:
    if not role_at_least(role, minimum):
        raise PermissionDeniedError(
            f"Requires {minimum.value} or higher; current role is {role.value}.",
        )
