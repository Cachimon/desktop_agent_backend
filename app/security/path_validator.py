import os
from pathlib import Path
from typing import Literal

from app.utils.exceptions import SecurityError, HITLRequiredError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PathSecurityLevel:
    ALLOW = "allow"
    CONFIRM_LOW = "confirm_low"
    CONFIRM_MEDIUM = "confirm_medium"
    CONFIRM_HIGH = "confirm_high"
    FORBIDDEN = "forbidden"


SYSTEM_BLACKLIST = [
    "/System", "/Library", "/usr/bin", "/usr/sbin", "/sbin", "/bin", "/etc",
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    "C:\\ProgramData", "C:\\Users\\All Users",
    "/boot", "/dev", "/proc", "/sys", "/root",
]

SENSITIVE_HIDDEN = [".ssh", ".gnupg", ".aws", ".kube", ".docker"]

LOW_CONFIRM_WHITELIST = ["Desktop", "Documents", "Downloads"]


async def check_path_security(
    path: str,
    user_workspaces: list[dict] | None = None,
) -> tuple[str, str]:
    resolved = Path(path).resolve()

    for black in SYSTEM_BLACKLIST:
        black_path = Path(black).resolve()
        try:
            if resolved == black_path or resolved.is_relative_to(black_path):
                return PathSecurityLevel.FORBIDDEN, f"Access to system directory is forbidden: {path}"
        except (OSError, ValueError):
            continue

    for part in resolved.parts:
        if any(part.startswith(".") and hidden in part for hidden in SENSITIVE_HIDDEN):
            return PathSecurityLevel.FORBIDDEN, f"Access to sensitive directory is forbidden: {path}"

    if ".." in str(path):
        return PathSecurityLevel.FORBIDDEN, "Path traversal is forbidden"

    try:
        if resolved.is_symlink():
            real = resolved.readlink().resolve()
            real_level, real_reason = await check_path_security(str(real), user_workspaces)
            if real_level == PathSecurityLevel.FORBIDDEN:
                return PathSecurityLevel.FORBIDDEN, f"Symlink points to forbidden path: {real_reason}"
    except (OSError, ValueError):
        return PathSecurityLevel.CONFIRM_HIGH, "Unresolved symlink target"

    if user_workspaces:
        for ws in user_workspaces:
            ws_path = Path(ws["path"]).resolve()
            try:
                if resolved == ws_path or resolved.is_relative_to(ws_path):
                    return ws.get("confirm_level", PathSecurityLevel.CONFIRM_LOW), f"User workspace: {ws.get('alias', path)}"
            except (OSError, ValueError):
                continue

    home = Path.home().resolve()
    try:
        if resolved.is_relative_to(home):
            relative = resolved.relative_to(home)
            first_part = relative.parts[0] if relative.parts else ""
            if first_part in LOW_CONFIRM_WHITELIST:
                return PathSecurityLevel.CONFIRM_LOW, "Standard user directory"
            return PathSecurityLevel.CONFIRM_MEDIUM, "Non-standard user directory"
    except (OSError, ValueError):
        pass

    return PathSecurityLevel.CONFIRM_HIGH, "Non-user directory path"


async def validate_path(
    path: str,
    user_confirmed: bool = False,
    user_workspaces: list[dict] | None = None,
    operation: str = "read",
) -> Path:
    level, reason = await check_path_security(path, user_workspaces)

    if level == PathSecurityLevel.FORBIDDEN:
        logger.warning("path_forbidden", path=path, reason=reason)
        raise SecurityError(message=reason, error_code="PATH_FORBIDDEN")

    if operation == "delete" and level != PathSecurityLevel.FORBIDDEN:
        level = PathSecurityLevel.CONFIRM_HIGH
        reason = "Delete operation requires high confirmation"

    if operation == "batch":
        level = PathSecurityLevel.CONFIRM_HIGH
        reason = "Batch operation requires high confirmation"

    if level in (PathSecurityLevel.CONFIRM_LOW, PathSecurityLevel.CONFIRM_MEDIUM, PathSecurityLevel.CONFIRM_HIGH):
        if not user_confirmed:
            logger.info("hitl_required", path=path, level=level, operation=operation)
            raise HITLRequiredError(
                action="path_access",
                message=f"Accessing path: {path}\nReason: {reason}\nOperation: {operation}\nContinue?",
                context={"path": path, "level": level, "operation": operation, "reason": reason},
            )

    return Path(path).resolve()
