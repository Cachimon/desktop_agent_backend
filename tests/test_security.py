import pytest
from app.security.path_validator import check_path_security, PathSecurityLevel
from app.security.shell_guard import validate_command
from app.utils.exceptions import SecurityError


@pytest.mark.asyncio
async def test_blacklisted_path_windows():
    level, reason = await check_path_security("C:\\Windows\\System32")
    assert level == PathSecurityLevel.FORBIDDEN


@pytest.mark.asyncio
async def test_blacklisted_path_linux():
    level, reason = await check_path_security("/etc/passwd")
    assert level == PathSecurityLevel.FORBIDDEN


@pytest.mark.asyncio
async def test_path_traversal():
    level, reason = await check_path_security("/home/user/../../../etc/passwd")
    assert level == PathSecurityLevel.FORBIDDEN


@pytest.mark.asyncio
async def test_sensitive_hidden_dir():
    level, reason = await check_path_security("/home/user/.ssh/id_rsa")
    assert level == PathSecurityLevel.FORBIDDEN


@pytest.mark.asyncio
async def test_shell_blacklist_rm_rf():
    with pytest.raises(SecurityError):
        validate_command("rm -rf /")


@pytest.mark.asyncio
async def test_shell_blacklist_sudo():
    with pytest.raises(SecurityError):
        validate_command("sudo apt install something")


@pytest.mark.asyncio
async def test_shell_whitelist_ls():
    assert validate_command("ls -la") is True


@pytest.mark.asyncio
async def test_shell_whitelist_grep():
    assert validate_command("grep -r pattern /path") is True
