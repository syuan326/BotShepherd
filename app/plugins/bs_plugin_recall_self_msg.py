"""
自动撤回机器人自己发送消息的插件。

用法：
- 发送 `bs开启自动撤回` 开启（默认仅对超级用户可用）
- 发送 `bs关闭自动撤回` 关闭
- 发送 `bs自动撤回状态` 查看当前状态

说明：
- 该插件会监听 NapCat/Lagrange 常见的 `message_sent` 事件（机器人自己发送的消息），
  在随机延时后调用 OneBot `delete_msg` 撤回对应 message_id。
- 为避免影响正常功能，默认仅超级用户可操作开关。
"""

import asyncio
import random
from typing import Dict, Any, List

from app.onebotv11.models import Event, PostType
from app.commands.permission_manager import PermissionLevel
from app.commands.base_command import BaseCommand, CommandResponse, command_registry
from app.onebotv11.api_handler import ApiHandler


# 随机等待区间（秒）
RECALL_DELAY = {"min": 40, "max": 50}
# 内存开关（进程级，重启后恢复默认）
AUTO_RECALL_ENABLED = True


class AutoRecallToggleCommand(BaseCommand):
    """自动撤回开关指令"""

    def __init__(self):
        super().__init__()
        self.name = "开启自动撤回"
        self.description = "开启自动撤回机器人自己发送的消息"
        self.usage = "开启自动撤回"
        self.aliases = ["关闭自动撤回", "自动撤回状态"]
        self.required_permission = PermissionLevel.SUPERUSER

    def _setup_parser(self):
        super()._setup_parser()

    async def execute(self, event: Event, args: List[str], context: Dict[str, Any]) -> CommandResponse:
        global AUTO_RECALL_ENABLED

        raw_text = ""
        for seg in event.message:
            if seg.type.value == "text":
                raw_text += seg.data.get("text", "")

        # 兼容命令别名路由后，按实际触发词判断动作
        if "关闭自动撤回" in raw_text:
            AUTO_RECALL_ENABLED = False
            return self.format_success("已关闭自动撤回")

        if "自动撤回状态" in raw_text:
            status = "开启" if AUTO_RECALL_ENABLED else "关闭"
            return self.format_info(f"自动撤回当前状态：{status}")

        AUTO_RECALL_ENABLED = True
        return self.format_success("已开启自动撤回")


async def try_handle_auto_recall(event: Event, logger) -> Dict[str, Any] | None:
    """供 monkey patch 后的 handle_message 调用。"""
    if not AUTO_RECALL_ENABLED:
        return None

    # 仅处理机器人自己发出的 message_sent 事件
    if getattr(event, "post_type", None) != PostType.MESSAGE_SENT:
        return None

    message_id = getattr(event, "message_id", None)
    if not message_id:
        return None

    delay = random.randint(RECALL_DELAY["min"], RECALL_DELAY["max"])
    logger.command.info(f"自动撤回插件：{delay}s 后撤回 message_id={message_id}")
    await asyncio.sleep(delay)

    return ApiHandler.create_delete_msg_request(message_id)


# ---- 通过 monkey patch 集成到当前框架 ----
from app.commands import command_handler as _ch_module  # noqa: E402

if not hasattr(_ch_module.CommandHandler, "_auto_recall_patched"):
    _orig_handle_message = _ch_module.CommandHandler.handle_message

    async def _patched_handle_message(self, event: Event):
        # 先尝试自动撤回监听（非指令事件）
        recall_req = await try_handle_auto_recall(event, self.logger)
        if recall_req:
            return recall_req

        # 再执行原有指令逻辑
        return await _orig_handle_message(self, event)

    _ch_module.CommandHandler.handle_message = _patched_handle_message
    _ch_module.CommandHandler._auto_recall_patched = True


# 注册控制指令
command_registry.register(AutoRecallToggleCommand())
