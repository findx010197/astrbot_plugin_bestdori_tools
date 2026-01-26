"""
定时播报调度器
负责管理生日祝福、活动播报、热点资讯等定时任务
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Awaitable
import json
import os

try:
    from astrbot.api import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class BroadcastScheduler:
    """定时播报调度器"""

    def __init__(self, config, data_dir: str):
        """
        初始化调度器

        Args:
            config: 插件配置 (可以是 dict 或 AstrBotConfig 对象)
            data_dir: 数据存储目录
        """
        # 兼容 AstrBotConfig 对象和普通字典
        self._config_obj = config
        self.data_dir = data_dir
        self.state_file = os.path.join(data_dir, "scheduler_state.json")
        self.running = False
        self._task: Optional[asyncio.Task] = None

        # 回调函数注册
        self._callbacks: Dict[str, Callable[..., Awaitable[None]]] = {}

        # 执行锁，防止并发执行
        self._birthday_lock = asyncio.Lock()
        self._news_lock = asyncio.Lock()
        self._event_lock = asyncio.Lock()

        # 加载状态
        self.state = self._load_state()

    @property
    def config(self) -> Dict[str, Any]:
        """获取配置字典"""
        if hasattr(self._config_obj, "__iter__") and not isinstance(
            self._config_obj, str
        ):
            # 如果是可迭代对象（如 dict），直接返回
            if isinstance(self._config_obj, dict):
                return self._config_obj
        # 尝试转换为字典
        if hasattr(self._config_obj, "to_dict"):
            return self._config_obj.to_dict()
        if hasattr(self._config_obj, "__dict__"):
            return dict(self._config_obj)
        # 如果有 get 方法，包装成兼容接口
        return self._config_obj if self._config_obj else {}

    def get_config(self, key: str, default=None):
        """安全获取配置值"""
        try:
            if hasattr(self._config_obj, "get"):
                return self._config_obj.get(key, default)
            elif isinstance(self._config_obj, dict):
                return self._config_obj.get(key, default)
            else:
                return getattr(self._config_obj, key, default)
        except Exception:
            return default

    def _load_state(self) -> Dict[str, Any]:
        """加载调度器状态"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载调度器状态失败: {e}")

        return {
            "last_birthday_check": None,
            "last_news_broadcast": None,
            "notified_events": {},  # event_id -> {"pre": bool, "post": bool}
        }

    def _save_state(self):
        """保存调度器状态"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存调度器状态失败: {e}")

    def register_callback(
        self, event_type: str, callback: Callable[..., Awaitable[None]]
    ):
        """
        注册回调函数

        Args:
            event_type: 事件类型 ("birthday", "event_pre", "event_post", "news")
            callback: 异步回调函数
        """
        self._callbacks[event_type] = callback
        logger.info(f"已注册播报回调: {event_type}")

    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        self._config_obj = config
        logger.info("调度器配置已更新")

    async def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("调度器已在运行")
            return

        # 调试：输出配置对象类型和内容
        logger.info("📡 调度器配置检查:")
        logger.info(f"  - 配置对象类型: {type(self._config_obj)}")

        broadcast_enabled = self.get_config("broadcast_enabled", False)
        birthday_config = self.get_config("birthday_broadcast", {})
        news_config = self.get_config("news_broadcast", {})

        logger.info(f"  - broadcast_enabled: {broadcast_enabled}")
        logger.info(f"  - birthday_broadcast: {birthday_config}")
        logger.info(f"  - news_broadcast: {news_config}")

        if not broadcast_enabled:
            logger.info("播报功能未启用，调度器不启动")
            return

        # 输出当前状态信息
        logger.info("📡 调度器状态检查:")
        logger.info(f"  - 状态文件: {self.state_file}")
        logger.info(f"  - last_birthday_check: {self.state.get('last_birthday_check')}")
        logger.info(f"  - last_news_broadcast: {self.state.get('last_news_broadcast')}")

        # 检查是否需要重置状态（用于调试）
        if self.get_config("broadcast_reset_state", False):
            logger.info("📡 检测到 broadcast_reset_state=True，清除今日播报状态")
            self.state["last_birthday_check"] = None
            self.state["last_news_broadcast"] = None
            self._save_state()

        self.running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("📡 定时播报调度器已启动")

    async def stop(self):
        """停止调度器"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("📡 定时播报调度器已停止")

    async def _scheduler_loop(self):
        """调度器主循环"""
        logger.info("📡 调度器循环开始运行...")

        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                now = datetime.now()

                # 每10次循环（约5分钟）输出一次心跳日志，确保还活着
                if loop_count % 10 == 1:
                    logger.info(
                        f"⏰ 调度器运行中 (loop {loop_count}): {now.strftime('%H:%M:%S')}"
                    )

                # 检查生日祝福
                await self._check_birthday_broadcast(now)

                # 检查活动播报
                await self._check_event_broadcast(now)

                # 检查资讯播报
                await self._check_news_broadcast(now)

                # 每30秒检查一次
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                logger.info("📡 调度器循环被取消")
                break
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
                import traceback

                logger.error(traceback.format_exc())
                await asyncio.sleep(30)

    async def _check_birthday_broadcast(self, now: datetime):
        """检查生日祝福"""
        # 使用锁防止并发执行
        if self._birthday_lock.locked():
            logger.debug("🎂 生日播报正在执行中，跳过本次检查")
            return

        async with self._birthday_lock:
            birthday_config = self.get_config("birthday_broadcast", {})
            if not birthday_config.get("enabled", True):
                return

            broadcast_hour = birthday_config.get("broadcast_hour", 0)
            broadcast_minute = birthday_config.get("broadcast_minute", 0)

            # 调试：每分钟开始时输出配置的时间
            if now.second < 5:
                logger.debug(
                    f"🎂 生日播报配置: {broadcast_hour:02d}:{broadcast_minute:02d}, 当前: {now.strftime('%H:%M')}"
                )

            # 检查是否到了播报时间（精确到分钟）
            if now.hour != broadcast_hour or now.minute != broadcast_minute:
                return

            logger.info(f"🎂 生日播报时间匹配! 当前时间: {now.strftime('%H:%M:%S')}")

            # 再次检查今天是否已经播报过（双重检查）
            today_str = now.strftime("%Y-%m-%d")
            last_birthday = self.state.get("last_birthday_check")
            logger.info(f"🎂 状态检查: 今天={today_str}, 上次播报={last_birthday}")

            if last_birthday == today_str:
                logger.info("🎂 今天已经播报过生日祝福，跳过")
                return

            # 执行回调
            if "birthday" in self._callbacks:
                try:
                    # 先标记为已播报，防止重复触发
                    self.state["last_birthday_check"] = today_str
                    self._save_state()

                    logger.info("🎂 开始执行生日播报回调...")
                    await self._callbacks["birthday"](now, self.state)
                    logger.info(f"🎂 生日祝福播报完成: {today_str}")
                except Exception as e:
                    logger.error(f"生日祝福播报失败: {e}")
                    import traceback

                    logger.error(traceback.format_exc())
            else:
                logger.warning("🎂 未注册 birthday 回调函数")

    async def _check_event_broadcast(self, now: datetime):
        """检查活动播报"""
        event_config = self.get_config("event_broadcast", {})
        if not event_config.get("enabled", True):
            return

        # 检查子开关
        preview_enabled = event_config.get("preview_enabled", True)
        overview_enabled = event_config.get("overview_enabled", True)

        pre_hours = event_config.get("preview_hours_before", 12)
        post_hours = event_config.get("overview_hours_after", 12)

        # 执行回调（传递时间参数和开关状态让回调自己判断）
        if "event_check" in self._callbacks:
            try:
                await self._callbacks["event_check"](
                    now,
                    pre_hours,
                    post_hours,
                    preview_enabled,
                    overview_enabled,
                    self.state,
                )
                self._save_state()
            except Exception as e:
                logger.error(f"活动播报检查失败: {e}")

    async def _check_news_broadcast(self, now: datetime):
        """检查资讯播报"""
        # 使用锁防止并发执行
        if self._news_lock.locked():
            logger.debug("📰 资讯播报正在执行中，跳过本次检查")
            return

        async with self._news_lock:
            news_config = self.get_config("news_broadcast", {})
            if not news_config.get("enabled", True):
                return

            broadcast_hour = news_config.get("broadcast_hour", 9)
            broadcast_minute = news_config.get("broadcast_minute", 0)

            # 调试：每分钟开始时输出配置的时间
            if now.second < 5:
                logger.debug(
                    f"📰 资讯播报配置: {broadcast_hour:02d}:{broadcast_minute:02d}, 当前: {now.strftime('%H:%M')}"
                )

            # 检查是否到了播报时间（精确到分钟）
            if now.hour != broadcast_hour or now.minute != broadcast_minute:
                return

            logger.info(f"📰 资讯播报时间匹配! 当前时间: {now.strftime('%H:%M:%S')}")

            # 再次检查今天是否已经播报过（双重检查）
            today_str = now.strftime("%Y-%m-%d")
            last_broadcast = self.state.get("last_news_broadcast")
            logger.info(f"📰 状态检查: 今天={today_str}, 上次播报={last_broadcast}")

            if last_broadcast == today_str:
                logger.info("📰 今天已经播报过资讯，跳过")
                return

            # 执行回调
            if "news" in self._callbacks:
                try:
                    # 先标记为已播报，防止重复触发
                    self.state["last_news_broadcast"] = today_str
                    self._save_state()

                    logger.info("📰 开始执行资讯播报回调...")
                    await self._callbacks["news"](now, self.state)
                    logger.info(f"📰 资讯播报完成: {today_str}")
                except Exception as e:
                    logger.error(f"资讯播报失败: {e}")
                    import traceback

                    logger.error(traceback.format_exc())
            else:
                logger.warning("📰 未注册 news 回调函数")

    def get_next_events(self) -> Dict[str, Optional[datetime]]:
        """获取下次播报时间（用于调试）"""
        now = datetime.now()
        result = {}

        # 生日祝福
        birthday_config = self.get_config("birthday_broadcast", {})
        if birthday_config.get("enabled", True):
            hour = birthday_config.get("broadcast_hour", 0)
            minute = birthday_config.get("broadcast_minute", 0)
            next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_time <= now:
                next_time += timedelta(days=1)
            result["birthday"] = next_time

        # 资讯播报
        news_config = self.get_config("news_broadcast", {})
        if news_config.get("enabled", True):
            hour = news_config.get("broadcast_hour", 9)
            minute = news_config.get("broadcast_minute", 0)
            next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_time <= now:
                next_time += timedelta(days=1)
            result["news"] = next_time

        return result


class NewsService:
    """Bestdori资讯服务"""

    def __init__(self, client):
        self.client = client

    async def get_today_news(self) -> List[Dict[str, Any]]:
        """
        获取今天的国服资讯

        Returns:
            资讯列表
        """
        try:
            import aiohttp

            # 获取资讯列表
            url = "https://bestdori.com/api/news/all.5.json"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return []
                    news_data = await resp.json()

            today = datetime.now().date()
            today_news = []

            for news_id, news_info in news_data.items():
                # 检查国服资讯 (server index 3)
                start_at = news_info.get("startAt", [])
                if len(start_at) > 3 and start_at[3]:
                    news_time = datetime.fromtimestamp(int(start_at[3]) / 1000)
                    if news_time.date() == today:
                        # 获取标题
                        titles = news_info.get("title", [])
                        title = (
                            titles[3]
                            if len(titles) > 3 and titles[3]
                            else (titles[0] if titles else f"资讯 {news_id}")
                        )

                        today_news.append(
                            {
                                "id": news_id,
                                "title": title,
                                "time": news_time.strftime("%H:%M"),
                                "url": f"https://bestdori.com/info/news/{news_id}",
                            }
                        )

            # 按时间排序
            today_news.sort(key=lambda x: x["time"])

            return today_news

        except Exception as e:
            logger.error(f"获取资讯失败: {e}")
            return []

    def format_news_message(self, news_list: List[Dict[str, Any]]) -> str:
        """
        格式化资讯消息

        Args:
            news_list: 资讯列表

        Returns:
            格式化后的消息文本
        """
        if not news_list:
            return ""

        lines = ["📰 **今日国服资讯** 📰", ""]

        for news in news_list:
            lines.append(f"• [{news['time']}] {news['title']}")
            lines.append(f"  🔗 {news['url']}")
            lines.append("")

        lines.append(f"共 {len(news_list)} 条资讯")

        return "\n".join(lines)
