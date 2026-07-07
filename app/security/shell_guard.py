import os
import re
from typing import Optional

from app.utils.exceptions import SecurityError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ================= 1. 安全与隔离配置 =================

# 物理隔离环境下的安全工作区根目录（假设宿主机目录挂载到了这里）
WORKSPACE_DIR = os.getcwd()  # 默认使用当前目录作为工作区

# 绝对禁止的命令/模式（系统级破坏）
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",  # 删除根目录
    r":$$\{\s*:\|:&\s*\}",  # Fork 炸弹
    r"mkfs",  # 格式化磁盘
    r"dd\s+if=",  # 磁盘擦写
    r"chmod\s+(-R\s+)?777\s+/",  # 危险的全局权限开放
    r">\s*/dev/sd",  # 直接写入磁盘设备
]

# 危险命令，建议使用专用工具（软性拦截/重定向）
DESTRUCTIVE_CMDS = {
    r"\brm\b": "请使用专用的 delete_file 工具，它更安全且有确认机制。",
    r"\brmdir\b": "请使用专用的 delete_dir 工具。",
    r"\bmv\b": "请使用专用的 move_file 工具，防止意外覆盖。",
    r"\bcp\b": "请使用专用的 copy_file 工具。",
}

# 交互式命令（会阻塞 subprocess）
INTERACTIVE_COMMANDS = ["vim", "vi", "nano", "less", "more", "top", "htop", "ssh"]

# 禁止访问的系统绝对路径前缀（物理隔离的底线）
PROTECTED_PREFIXES = [
    "/etc",
    "/root",
    "/var",
    "/usr",
    "/bin",
    "/sbin",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
]


# ================= 2. 核心校验逻辑 =================


def validate_command(command: str) -> Optional[str]:
    """
    校验命令安全性。
    返回 None 表示安全；返回字符串表示拦截原因（相当于报错信息）。
    """
    # 1. 硬性拦截：极其危险的系统级操作
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return f"🚨 极度危险操作被拦截：匹配到危险模式 '{pattern}'。此操作不可逆，已被系统禁止。"

    # 2. 软性拦截/重定向：建议使用专用工具
    for pattern, reason in DESTRUCTIVE_CMDS.items():
        if re.search(pattern, command):
            return (
                f"⚠️ 危险命令重定向：检测到 '{pattern.split(r'\\b')[0]}' 命令。{reason}"
            )

    # 3. 拦截 Shell 重定向写文件 (引导使用 write_file / edit_file)
    # python -c 命令中的 > 通常是 Python 比较运算符，跳过检测
    is_python_eval = bool(re.match(r"\s*python\d*\s+-c\s", command))
    if not is_python_eval:
        if re.search(r">\s*[^&>=\s]", command) or re.search(r">>\s*", command):
            return "⚠️ 写入拦截：请勿使用 Shell 重定向 (`>` 或 `>>`) 写入文件。请使用专用的 write_file 或 edit_file 工具，它们能更好地处理编码和转义字符。"

    # 4. 交互式命令拦截
    cmd_base = command.split()[0] if command.split() else ""
    if cmd_base in INTERACTIVE_COMMANDS:
        return f"🚫 交互式命令拦截：'{cmd_base}' 会占用终端。请使用非交互式替代方案（如用 cat 查看文件，而不是 vim）。"

    # 5. 网络安全拦截（防止数据外泄或下载执行未知脚本）
    if re.search(r"curl\s+.*\|\s*(ba)?sh", command):
        return "🚫 网络安全拦截：禁止将远程脚本直接通过管道传递给 Shell 执行（curl | sh），这存在极大的供应链攻击风险。"

    # 6. 物理隔离边界拦截：禁止访问工作区之外的系统核心目录
    # 提取命令中所有的绝对路径并进行检查
    tokens = command.split()
    for token in tokens:
        # 简单识别以 / 开头的路径
        if token.startswith("/"):
            # 清理可能附带的参数符号 (如 --prefix=/usr)
            clean_path = token.split("=")[-1] if "=" in token else token

            # 允许访问工作区
            if clean_path.startswith(WORKSPACE_DIR):
                continue

            # 拦截访问受保护的系统目录
            for prot in PROTECTED_PREFIXES:
                if clean_path.startswith(prot):
                    return f"🚫 沙盒边界拦截：禁止访问系统核心目录 '{clean_path}'。智能体只能在 '{WORKSPACE_DIR}' 目录下工作。"

    return None
