"""
菜单上下文管理器
用于记录用户当前所在的菜单层级，支持数字快捷选择
"""

from typing import Dict, List, Optional, Tuple
import time


class MenuContext:
    """用户菜单上下文管理器"""

    # 菜单定义：层级 -> [(序号, 标识符, 描述, 下一层级或命令)]
    MENUS = {
        "main": [
            (1, "tools", "工具查询", "tools"),
            (2, "admin", "管理功能", "admin"),
            (3, "games", "趣味游戏", "games"),
        ],
        "tools": [
            (1, "event", "活动查询", "cmd:event"),
            (2, "birthday", "生日查询", "cmd:birthday"),
            (3, "card", "卡面查询", "cmd:card"),
            (0, "back", "返回上级", "main"),
        ],
        "admin": [
            (1, "subscribe", "订阅播报", "cmd:subscribe"),
            (2, "unsubscribe", "取消订阅", "cmd:unsubscribe"),
            (3, "mystatus", "我的状态", "cmd:mystatus"),
            (4, "subscribers", "订阅列表", "cmd:subscribers"),
            (5, "stats", "播报统计", "cmd:stats"),
            (6, "clear", "清除播报状态", "cmd:clear"),
            (7, "cache", "缓存管理", "cache"),
            (0, "back", "返回上级", "main"),
        ],
        "cache": [
            (1, "cache_stats", "查看缓存统计", "cmd:cache_stats"),
            (2, "cache_list", "查看缓存列表", "cmd:cache_list"),
            (3, "cache_clean", "清理过期缓存", "cmd:cache_clean"),
            (4, "cache_clear", "清空渲染缓存", "cache_clear_confirm"),
            (5, "api_refresh", "刷新API数据", "api_refresh_confirm"),
            (6, "api_status", "API缓存状态", "cmd:api_status"),
            (0, "back", "返回上级", "admin"),
        ],
        "cache_clear_confirm": [
            (1, "confirm_clear", "确认清空", "cmd:cache_clear_confirmed"),
            (2, "cancel", "取消操作", "cache"),
        ],
        "api_refresh_confirm": [
            (1, "confirm_refresh", "确认刷新", "cmd:api_refresh_confirmed"),
            (2, "cancel", "取消操作", "cache"),
        ],
        "games": [
            (0, "back", "返回上级", "main"),
        ],
        "event": [
            (1, "current_cn", "当期活动(国服)", "cmd:event_cn"),
            (2, "current_jp", "当期活动(日服)", "cmd:event_jp"),
            (3, "id", "指定ID查询", "input:event_id"),
            (0, "back", "返回上级", "tools"),
        ],
        "card_menu": [
            (1, "search", "角色查询", "cmd:card_query_char"),
            (0, "back", "返回上级", "tools"),
        ],
        "card_search": [
            (1, "all", "全部卡面", "cmd:card_search_all"),
            (2, "random", "随机抽取", "cmd:card_search_random"),
            (0, "back", "返回上级", "tools"),
        ],
        "card_list_view": [
            # 卡面列表查看模式 - 用户可以通过 /id xxxx 或 /xxxx 查询卡面详情
            # 此菜单不显示选项，仅用于上下文识别
            (0, "back", "返回上级", "tools"),
        ],
        "card_detail": [
            (1, "illustration", "插画信息", "cmd:card_illustration"),
            (0, "back", "返回上级", "card_list_view"),
        ],
    }

    # 上下文超时时间（秒）
    CONTEXT_TIMEOUT = 300  # 5分钟

    def __init__(self):
        # 用户上下文: {user_id: {"menu": "main", "timestamp": time, "input_mode": None}}
        self._contexts: Dict[str, dict] = {}

    def _get_user_key(self, user_id: str, group_id: str = "") -> str:
        """生成用户唯一标识（同一用户在不同群的上下文独立）"""
        if group_id:
            return f"{user_id}@{group_id}"
        return user_id

    def get_context(self, user_id: str, group_id: str = "") -> Optional[dict]:
        """获取用户当前上下文"""
        key = self._get_user_key(user_id, group_id)
        ctx = self._contexts.get(key)

        if ctx:
            # 检查是否超时
            if time.time() - ctx["timestamp"] > self.CONTEXT_TIMEOUT:
                del self._contexts[key]
                return None
            return ctx
        return None

    def set_context(
        self,
        user_id: str,
        group_id: str = "",
        menu: str = "main",
        input_mode: str = None,
        **extra_data,
    ):
        """设置用户上下文

        Args:
            user_id: 用户ID
            group_id: 群组ID（可选）
            menu: 当前菜单
            input_mode: 输入模式（用于等待用户输入特定内容）
            **extra_data: 额外数据（如 card_id, char_id 等）
        """
        key = self._get_user_key(user_id, group_id)
        self._contexts[key] = {
            "menu": menu,
            "timestamp": time.time(),
            "input_mode": input_mode,  # 用于等待用户输入特定内容
            **extra_data,  # 存储额外数据
        }

    def update_context(self, user_id: str, group_id: str = "", **updates):
        """更新用户上下文的部分字段"""
        key = self._get_user_key(user_id, group_id)
        if key in self._contexts:
            self._contexts[key].update(updates)
            self._contexts[key]["timestamp"] = time.time()

    def clear_context(self, user_id: str, group_id: str = ""):
        """清除用户上下文"""
        key = self._get_user_key(user_id, group_id)
        if key in self._contexts:
            del self._contexts[key]

    def get_menu_items(self, menu: str) -> List[Tuple[int, str, str, str]]:
        """获取菜单项列表"""
        return self.MENUS.get(menu, [])

    def get_item_by_number(
        self, menu: str, number: int
    ) -> Optional[Tuple[int, str, str, str]]:
        """根据序号获取菜单项"""
        items = self.get_menu_items(menu)
        for item in items:
            if item[0] == number:
                return item
        return None

    def get_item_by_name(
        self, menu: str, name: str
    ) -> Optional[Tuple[int, str, str, str]]:
        """根据标识符获取菜单项"""
        items = self.get_menu_items(menu)
        name_lower = name.lower()
        for item in items:
            if item[1].lower() == name_lower:
                return item
        return None

    def format_menu(self, menu: str, title: str = "") -> str:
        """格式化菜单显示"""
        items = self.get_menu_items(menu)
        if not items:
            return "菜单不存在"

        lines = []
        if title:
            lines.append(f"[ {title} ]")
            lines.append("-" * 24)

        for num, identifier, desc, _ in items:
            if num == 0:
                lines.append(f"  /0 - {identifier} - {desc}")
            else:
                lines.append(f"  /{num} - {identifier} - {desc}")

        lines.append("-" * 24)
        lines.append("输入 /序号 或 /标识符 继续")

        return "\n".join(lines)

    def cleanup_expired(self):
        """清理过期的上下文"""
        now = time.time()
        expired_keys = [
            key
            for key, ctx in self._contexts.items()
            if now - ctx["timestamp"] > self.CONTEXT_TIMEOUT
        ]
        for key in expired_keys:
            del self._contexts[key]


# 全局单例
menu_context = MenuContext()
