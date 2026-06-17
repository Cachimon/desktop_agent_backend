import re

from app.utils.exceptions import SecurityError
from app.utils.logging import get_logger

logger = get_logger(__name__)


COMMAND_BLACKLIST_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"mkfs",
    r"\bdd\b",
    r">\s*:",
    r"curl\s+.*\|\s*bash",
    r"wget\s+.*\|\s*sh",
    r"\bsudo\b",
    r"\bsu\b",
    r"\brunas\b",
    r"\bnc\b",
    r"\btelnet\b",
    r"\bssh\b.*-R\b",
    r"powershell\s+-enc",
    r"cmd\s+/c\b",
]

COMMAND_WHITELIST_PATTERNS = [
    r"^(ls|dir)\b",
    r"^find\b",
    r"^grep\b",
    r"^mkdir\b",
    r"^cp\b",
    r"^mv\b",
    r"^(zip|unzip)\b",
    r"^tar\b",
]


def validate_command(command: str) -> bool:
    stripped = command.strip()

    for pattern in COMMAND_BLACKLIST_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            logger.warning("command_blacklisted", command=stripped[:50])
            raise SecurityError(
                message=f"Command is forbidden for security reasons: {stripped[:50]}",
                error_code="COMMAND_FORBIDDEN",
            )

    for pattern in COMMAND_WHITELIST_PATTERNS:
        if re.match(pattern, stripped, re.IGNORECASE):
            return True

    raise SecurityError(
        message=f"Command not in whitelist: {stripped[:50]}",
        error_code="COMMAND_NOT_WHITELISTED",
    )
