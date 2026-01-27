from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp
from .client import BestdoriClient
from .models import (
    Event,
    Card,
    Gacha,
    SERVER_JP,
    SERVER_CN,
    SERVER_CODE_MAP,
)
from .consts import (
    get_character_id_by_name,
    CHARACTER_MAP,
    CHARACTER_BAND_MAP,
    BAND_ICON_URL_MAP,
    SERVER_NAME_MAP,
    SERVER_SHORT_NAME_MAP,
    get_server_id,
    DEFAULT_SERVER_PRIORITY,
)
from .render_service import RenderService
from .birthday_service import BirthdayService
from .resource_manager import ResourceManager
from .cache_manager import CacheManager
from .dependency_manager import dependency_manager
from .color_extractor import color_extractor
from .scheduler import BroadcastScheduler, NewsService
from .subscriber_service import SubscriberService
from .menu_context import menu_context
import os
import asyncio
import base64
import aiohttp
import re
from datetime import datetime


@register(
    "bestdori_tools",
    "findx1197",
    "BanG Dream Bestdori 工具插件",
    "1.1.1",
    "https://github.com/findx1197/astrbot_plugin_bestdori_tools",
)
class BestdoriPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self._scheduler_started = False  # 防止调度器重复启动

        # 使用插件目录下的data文件夹存储数据
        plugin_dir = os.path.dirname(__file__)
        data_dir = os.path.join(plugin_dir, "data", "bestdori_tools")
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.client = BestdoriClient(cache_dir=data_dir)

        # 初始化渲染服务
        template_dir = os.path.join(plugin_dir, "templates")
        render_output_dir = os.path.join(data_dir, "renders")
        self.renderer = RenderService(template_dir, output_dir=render_output_dir)

        # 初始化生日服务
        self.birthday_service = BirthdayService(data_dir)

        # 初始化资源管理器
        self.resource_manager = ResourceManager(data_dir, self.birthday_service)

        # 初始化缓存管理器
        cache_dir = os.path.join(data_dir, "cache")
        cache_config = {
            "cache_enabled": self._get_config("cache_enabled", True),
            "cache_max_size": self._get_config("cache_max_size", 1024)
            * 1024
            * 1024,  # MB 转 bytes
            "cache_event_ttl": self._get_config("cache_event_ttl", 24)
            * 3600,  # 小时转秒
            "cache_card_ttl": self._get_config("cache_card_ttl", 7) * 86400,  # 天转秒
            "cache_birthday_ttl": self._get_config("cache_birthday_ttl", 30)
            * 86400,  # 天转秒
            "cache_cleanup_interval": self._get_config("cache_cleanup_interval", 24)
            * 3600,  # 小时转秒
        }
        self.cache_manager = CacheManager(cache_dir, cache_config)

        # 缓存清理调度器将在 on_astrbot_loaded 时启动
        self._cache_cleanup_task = None

        # 初始化资讯服务
        self.news_service = NewsService(self.client)

        # 初始化订阅用户服务
        self.subscriber_service = SubscriberService(data_dir)

        # 初始化调度器（但不立即启动）
        self.scheduler = BroadcastScheduler(self.config, data_dir)
        self._register_scheduler_callbacks()

        # 启动异步初始化任务 (替代 on_astrbot_loaded，确保一定会运行)
        asyncio.create_task(self.async_init())

    async def async_init(self):
        """异步初始化任务"""
        # 等待一小段时间确保框架就绪
        await asyncio.sleep(2)
        
        logger.info("🚀 Bestdori 插件开始异步初始化")

        # 1. 启动缓存清理调度器
        if self._cache_cleanup_task is None:
            self._cache_cleanup_task = asyncio.create_task(
                self.cache_manager.start_cleanup_scheduler()
            )

        # 2. 执行启动检查 (资源下载等)
        await self._startup_check()

        # 3. 预热数据
        try:
            await self.client.get_events()
            await self.client.get_cards()
            logger.info("✅ Bestdori 数据预热完成")
        except Exception as e:
            logger.error(f"Bestdori 数据预热失败: {e}")

        # 4. 启动定时播报调度器（确保只启动一次）
        if not self._scheduler_started:
            try:
                # 确保使用最新配置
                self.scheduler.update_config(self.config)
                await self.scheduler.start()
                self._scheduler_started = True
                logger.info("✅ Bestdori 定时播报调度器已启动")
            except Exception as e:
                logger.error(f"定时播报调度器启动失败: {e}")

    def _get_config(self, key: str, default=None):
        """
        安全地获取配置值，兼容 AstrBotConfig 和 dict 两种类型
        """
        try:
            val = default
            if hasattr(self.config, "get"):
                val = self.config.get(key, default)
            elif hasattr(self.config, key):
                val = getattr(self.config, key)
            elif isinstance(self.config, dict):
                val = self.config.get(key, default)
            else:
                # 尝试索引访问
                try:
                    val = self.config[key]
                except (KeyError, TypeError):
                    val = default

            # 调试日志：检查关键配置的读取
            if key in [
                "broadcast_enabled",
                "broadcast_empty_notify",
                "broadcast_reset_state",
            ]:
                # logger.debug(f"Config[{key}] = {val} (default={default})")
                pass
            return val
        except Exception:
            return default

    async def _startup_check(self):
        """插件启动时的自检任务"""
        try:
            # 1. 检查和安装依赖
            print("🔧 检查插件依赖...")
            missing_required, missing_optional = (
                dependency_manager.get_missing_packages()
            )

            if missing_required or missing_optional:
                print("📦 安装缺失的依赖包...")
                install_results = dependency_manager.auto_install_dependencies()

                # 检查必需依赖是否安装成功
                failed_required = [
                    pkg
                    for pkg, success in install_results.items()
                    if not success and any(pkg in spec for spec in missing_required)
                ]

                if failed_required:
                    print(f"⚠️ 关键依赖安装失败: {failed_required}")
                    print("插件可能无法正常工作，请手动安装依赖")
                else:
                    print("✅ 依赖检查完成")
            else:
                print("✅ 所有依赖已满足")

            # 2. 检查系统依赖
            system_deps = dependency_manager.check_system_dependencies()
            
            # 3. 如果中文字体安装失败，尝试下载字体到本地
            if system_deps and not system_deps.get("chinese_fonts", True):
                print("💡 尝试下载字体到本地作为备选方案...")
                await dependency_manager.download_font_to_local()

            # 4. 执行首次运行检查和资源完整性检查（传入 client 以下载卡面和服装）
            await self.resource_manager.first_run_check(client=self.client)

        except Exception as e:
            print(f"❌ 插件启动检查失败: {e}")
            import traceback

            traceback.print_exc()

    def _register_scheduler_callbacks(self):
        """注册调度器回调函数"""
        self.scheduler.register_callback("birthday", self._broadcast_birthday)
        self.scheduler.register_callback("event_check", self._check_event_broadcast)
        self.scheduler.register_callback("news", self._broadcast_news)

    async def _broadcast_birthday(self, now: datetime, state: dict):
        """生日祝福播报回调"""
        # 获取今天过生日的角色
        today_birthdays = self.birthday_service.get_today_birthdays()

        if not today_birthdays:
            # 检查是否启用了无内容通知
            if self._get_config("broadcast_empty_notify", False):
                no_birthday_msg = (
                    f"🎂 **生日祝福播报** 🎂\n\n"
                    f"📅 {now.strftime('%Y年%m月%d日')}\n\n"
                    f"今天没有角色过生日哦~\n"
                    f"播报功能运行正常 ✅"
                )
                await self._send_broadcast(
                    [{"type": "text", "content": no_birthday_msg}], "生日祝福"
                )
                logger.info("今天没有角色过生日，已发送测试通知")
            else:
                logger.info("今天没有角色过生日")
            return

        # 为每个过生日的角色发送祝福
        for char_id in today_birthdays:
            try:
                birthday_data = await self.birthday_service.get_birthday_message(
                    char_id
                )
                if birthday_data:
                    # 构建消息
                    messages = await self._build_birthday_broadcast_messages(
                        birthday_data
                    )

                    # 发送播报
                    char_name = birthday_data.get("character_name", f"角色{char_id}")
                    await self._send_broadcast(messages, f"生日祝福-{char_name}")

            except Exception as e:
                logger.error(f"发送角色 {char_id} 的生日祝福失败: {e}")

    async def _check_event_broadcast(
        self,
        now: datetime,
        pre_hours: int,
        post_hours: int,
        preview_enabled: bool,
        overview_enabled: bool,
        state: dict,
    ):
        """活动播报检查回调"""
        try:
            events_data = await self.client.get_events()
            now_ts = int(now.timestamp() * 1000)

            # 获取配置的默认服务器
            default_server_code = self._get_config("default_server", "cn")
            default_server = get_server_id(default_server_code)

            for event_id, event_data in events_data.items():
                event = Event(int(event_id), event_data)
                event_start = event.get_start_time(server=default_server)

                if not event_start:
                    continue

                # 初始化事件状态
                if event_id not in state.get("notified_events", {}):
                    state.setdefault("notified_events", {})[event_id] = {
                        "pre": False,
                        "post": False,
                    }

                event_state = state["notified_events"][event_id]

                # 检查是否需要发送活动预告（活动开始前 pre_hours 小时）
                if preview_enabled:
                    pre_notify_time = event_start - (pre_hours * 3600 * 1000)
                    if (
                        pre_notify_time <= now_ts < event_start
                        and not event_state["pre"]
                    ):
                        await self._broadcast_event_preview(event)
                        event_state["pre"] = True
                        logger.info(f"📢 已发送活动预告: {event.name}")

                # 检查是否需要发送活动一览（活动开始后 post_hours 小时）
                if overview_enabled:
                    post_notify_time = event_start + (post_hours * 3600 * 1000)
                    if (
                        event_start <= now_ts < post_notify_time
                        and not event_state["post"]
                    ):
                        # 确保在活动开始后的合理时间内发送
                        if now_ts >= event_start + (
                            post_hours * 3600 * 1000 * 0.9
                        ):  # 90%时间点后发送
                            await self._broadcast_event_overview(event)
                            event_state["post"] = True
                            logger.info(f"📢 已发送活动一览: {event.name}")

        except Exception as e:
            logger.error(f"检查活动播报失败: {e}")

    async def _broadcast_event_preview(self, event: Event):
        """发送活动预告"""
        # 获取配置的默认服务器
        default_server_code = self._get_config("default_server", "cn")
        default_server = get_server_id(default_server_code)

        # 构建预告文本消息
        start_time = event.get_formatted_time(True, server=default_server)
        message = (
            f"📣 **活动预告** 📣\n\n"
            f"🎪 {event.name}\n"
            f"⏰ 开始时间: {start_time}\n"
            f"📋 类型: {event.event_type_cn}\n\n"
            f"活动即将开始，请做好准备！"
        )

        await self._send_broadcast(
            [{"type": "text", "content": message}], f"活动预告-{event.name}"
        )

    async def _broadcast_event_overview(self, event: Event):
        """发送活动一览"""
        try:
            # 生成活动一览图片（复用现有的渲染逻辑）
            image_path = await self._generate_event_overview_image(event.event_id)

            if image_path and os.path.exists(image_path):
                await self._send_broadcast(
                    [
                        {
                            "type": "text",
                            "content": f"📣 **活动已开始** 📣\n\n🎪 {event.name}",
                        },
                        {"type": "image", "content": image_path},
                    ],
                    f"活动一览-{event.name}",
                )
            else:
                # 如果图片生成失败，发送文本消息
                await self._send_broadcast(
                    [
                        {
                            "type": "text",
                            "content": f"📣 **活动已开始** 📣\n\n🎪 {event.name}\n\n活动一览图片生成失败，请使用 /bd event {event.event_id} 查看详情",
                        }
                    ],
                    f"活动一览-{event.name}",
                )
        except Exception as e:
            logger.error(f"发送活动一览失败: {e}")

    async def _broadcast_news(self, now: datetime, state: dict):
        """资讯播报回调"""
        # 获取今日资讯
        news_list = await self.news_service.get_today_news()

        if not news_list:
            # 检查是否启用了无内容通知
            if self._get_config("broadcast_empty_notify", False):
                no_news_msg = (
                    f"📰 **每日资讯播报** 📰\n\n"
                    f"📅 {now.strftime('%Y年%m月%d日')}\n\n"
                    f"今天暂无新资讯~\n"
                    f"播报功能运行正常 ✅"
                )
                await self._send_broadcast(
                    [{"type": "text", "content": no_news_msg}], "每日资讯"
                )
                logger.info("今天没有新资讯，已发送测试通知")
            else:
                logger.info("今天没有新资讯")
            return

        # 格式化消息
        message = self.news_service.format_news_message(news_list)

        # 发送播报
        await self._send_broadcast([{"type": "text", "content": message}], "每日资讯")

    async def _build_birthday_broadcast_messages(self, birthday_data: dict) -> list:
        """构建生日播报消息列表"""
        messages = []

        # 文本祝福
        char_name = birthday_data.get("character_name", "")
        band_name = birthday_data.get("band_name", "")
        birthday = birthday_data.get("birthday", "")

        text = f"🎂 **生日快乐** 🎂\n\n祝 {char_name} ({band_name}) 生日快乐！\n📅 {birthday}"
        messages.append({"type": "text", "content": text})

        # TODO: 添加生日卡片图片和语音
        # 这里可以复用 _render_birthday_card 的逻辑

        return messages

    async def _send_broadcast(self, messages: list, broadcast_type: str = ""):
        """
        发送播报消息到所有配置的目标

        Args:
            messages: 消息列表 [{"type": "text/image/voice", "content": "..."}]
            broadcast_type: 播报类型标识，用于日志
        """
        try:
            sent_count = 0
            group_count = 0
            user_count = 0

            # 1. 发送到 AstrBot 后台（日志，不计入发送数量）
            if self._get_config("broadcast_to_console", True):
                for msg in messages:
                    if msg.get("type") == "text":
                        logger.info(
                            f"📢 [{broadcast_type}] {msg.get('content', '')[:200]}..."
                        )
                    elif msg.get("type") == "image":
                        logger.info(
                            f"📢 [{broadcast_type}] [图片] {msg.get('content', '')}"
                        )
                    elif msg.get("type") == "voice":
                        logger.info(
                            f"📢 [{broadcast_type}] [语音] {msg.get('content', '')}"
                        )

            # 2. 发送到配置的群组
            if self._get_config("broadcast_to_groups", False):
                groups = self._get_config("broadcast_groups", [])
                if groups:
                    for group_id in groups:
                        try:
                            await self._send_to_target(f"group_{group_id}", messages)
                            group_count += 1
                        except Exception as e:
                            logger.error(f"发送到群组 {group_id} 失败: {e}")
                else:
                    logger.warning(
                        "broadcast_to_groups 已启用但 broadcast_groups 列表为空"
                    )

            # 3. 发送到订阅用户（通过用户主动互动收集的列表）
            if self._get_config("broadcast_to_users", False):
                try:
                    # 获取黑名单
                    blacklist = self._get_config("broadcast_users_blacklist", [])
                    blacklist_set = set(str(uid) for uid in blacklist)

                    # 从订阅服务获取用户列表
                    subscribed_users = self.subscriber_service.get_subscribed_users(
                        blacklist_set
                    )

                    if subscribed_users:
                        logger.info(
                            f"👥 订阅用户 {len(subscribed_users)} 个，黑名单 {len(blacklist_set)} 个"
                        )

                        for user_id in subscribed_users:
                            try:
                                await self._send_to_target(f"user_{user_id}", messages)
                                user_count += 1
                            except Exception as e:
                                logger.error(f"发送到用户 {user_id} 失败: {e}")
                    else:
                        logger.info(
                            "暂无订阅用户，用户可通过与 bot 互动自动订阅，或发送 /bd subscribe 手动订阅"
                        )

                except Exception as e:
                    logger.error(f"用户播报失败: {e}")

            sent_count = group_count + user_count
            logger.info(
                f"📤 [{broadcast_type}] 播报完成，群组 {group_count} 个，用户 {user_count} 个，共 {sent_count} 个目标"
            )

        except Exception as e:
            logger.error(f"发送播报消息失败: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def _send_to_target(self, target: str, messages: list):
        """
        发送消息到指定目标

        Args:
            target: 目标ID (如 "group_123456" 或 "user_789012")
            messages: 消息列表
        """
        try:
            # 使用 AstrBot 官方 API 导入
            from astrbot.api.event import MessageChain
            import astrbot.api.message_components as Comp

            # 解析目标类型
            if target.startswith("group_"):
                target_id = target[6:]
                message_type_str = "GroupMessage"
            elif target.startswith("user_"):
                target_id = target[5:]
                message_type_str = "FriendMessage"
            else:
                logger.warning(f"未知的目标格式: {target}")
                return

            # 构建消息链
            chain = MessageChain()
            for msg in messages:
                msg_type = msg.get("type", "text")
                content = msg.get("content", "")

                if msg_type == "text":
                    chain.message(content)
                elif msg_type == "image":
                    # 图片可以是本地路径或URL
                    if content.startswith("http://") or content.startswith("https://"):
                        chain.url_image(content)
                    elif os.path.exists(content):
                        chain.file_image(content)
                    else:
                        logger.warning(f"图片路径无效: {content}")

            # 获取配置的目标平台（可选，留空自动选择）
            target_platform = self._get_config("broadcast_platform", "")

            # 获取所有运行中的平台适配器
            platforms = self.context.platform_manager.get_insts()

            if not platforms:
                logger.warning("没有可用的平台实例")
                return

            # 收集所有平台信息
            all_platforms = []
            for platform in platforms:
                try:
                    platform_id = (
                        platform.meta().id
                        if hasattr(platform, "meta")
                        else str(platform)
                    )
                    # 获取平台类型（如 aiocqhttp, gewechat 等）
                    platform_name = (
                        platform.meta().name if hasattr(platform, "meta") else ""
                    )
                    all_platforms.append(
                        {"platform": platform, "id": platform_id, "name": platform_name}
                    )
                except Exception as e:
                    logger.warning(f"获取平台信息失败: {e}")

            all_platform_ids = [p["id"] for p in all_platforms]

            # 智能选择目标平台
            target_platforms = []

            if target_platform:
                # 用户指定了平台，使用指定的
                for p in all_platforms:
                    if p["id"] == target_platform:
                        target_platforms.append((p["platform"], p["id"]))
                        break
            else:
                # 自动选择：排除 webchat，优先选择 QQ 相关平台
                qq_platforms = []
                other_platforms = []

                for p in all_platforms:
                    if p["id"] == "webchat":
                        continue  # 排除 webchat

                    # 检查是否是 QQ 相关平台（aiocqhttp 协议）
                    # platform.meta().name 通常包含协议类型
                    if (
                        "aiocqhttp" in p["name"].lower()
                        or "onebot" in p["name"].lower()
                        or "qq" in p["id"].lower()
                    ):
                        qq_platforms.append((p["platform"], p["id"]))
                    else:
                        other_platforms.append((p["platform"], p["id"]))

                # 优先使用 QQ 平台，否则使用其他非 webchat 平台
                target_platforms = qq_platforms + other_platforms

            if not target_platforms:
                logger.warning(
                    f"没有找到可用的消息平台\n已连接平台: {all_platform_ids}\n如需指定平台，请在配置中设置 broadcast_platform"
                )
                return

            # 使用第一个匹配的平台
            selected_platform, selected_id = target_platforms[0]
            logger.info(f"📡 已连接平台: {all_platform_ids}, 自动选择: {selected_id}")

            sent = False
            for platform, platform_id in target_platforms:
                try:
                    # 构建 unified_msg_origin
                    # 格式: 平台名:消息类型:会话ID
                    unified_msg_origin = f"{platform_id}:{message_type_str}:{target_id}"

                    logger.info(f"📤 尝试发送消息到: {unified_msg_origin}")

                    # 使用 context.send_message 发送主动消息
                    await self.context.send_message(unified_msg_origin, chain)

                    sent = True
                    logger.info(f"✅ 已通过 {platform_id} 发送消息到 {target}")
                    break  # 只需要通过一个平台发送成功即可

                except Exception as e:
                    logger.warning(f"通过平台 {platform_id} 发送失败: {e}")
                    import traceback

                    logger.debug(traceback.format_exc())
                    continue

            if not sent:
                logger.warning(f"所有平台发送失败，目标: {target}")

        except ImportError as e:
            logger.error(
                f"导入 AstrBot API 失败: {e}，请确保 AstrBot 版本支持主动消息发送"
            )
        except Exception as e:
            logger.error(f"发送消息到 {target} 失败: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def _generate_event_overview_image(self, event_id: int) -> str:
        """生成活动一览图片（复用渲染逻辑）"""
        # TODO: 复用 _render_event 的渲染逻辑
        # 这里返回生成的图片路径
        output_path = os.path.join(
            self.data_dir, "images", f"event_overview_{event_id}.png"
        )
        return output_path if os.path.exists(output_path) else ""

    # @filter.on_astrbot_loaded()
    # async def on_astrbot_loaded(self):
    #     """AstrBot 初始化完成时调用 - 已迁移至 async_init"""
    #     pass

    async def terminate(self):
        """插件被卸载/停用时调用 - 清理资源"""
        logger.info("🛑 Bestdori 插件正在停止...")

        # 1. 停止调度器
        try:
            if hasattr(self, "scheduler") and self.scheduler:
                await self.scheduler.stop()
                logger.info("✅ 定时播报调度器已停止")
        except Exception as e:
            logger.warning(f"停止调度器时发生异常 (但这不影响停止流程): {e}")
        finally:
            self._scheduler_started = False

        # 2. 取消缓存清理任务
        try:
            if self._cache_cleanup_task:
                self._cache_cleanup_task.cancel()
                # 等待任务取消完成，避免在这里留下悬挂任务
                try:
                    await asyncio.wait_for(self._cache_cleanup_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._cache_cleanup_task = None
        except Exception as e:
            logger.warning(f"取消缓存清理任务时发生异常: {e}")

        logger.info("✅ Bestdori 插件已完全停止")

    @filter.command("bd")
    async def bestdori(self, event: AstrMessageEvent, *args):
        """Bestdori 插件统一入口 - 三级菜单系统"""
        # 记录用户活动（自动订阅播报）
        try:
            user_id = event.get_sender_id()
            user_name = event.get_sender_name()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            platform = ""
            if hasattr(event, "unified_msg_origin"):
                platform = (
                    event.unified_msg_origin.split(":")[0]
                    if event.unified_msg_origin
                    else ""
                )

            is_new = self.subscriber_service.record_user_activity(
                user_id=user_id,
                platform=platform,
                nickname=user_name,
                from_group=group_id,
            )
            if is_new:
                logger.info(f"📥 新用户自动订阅: {user_name} ({user_id})")
        except Exception as e:
            logger.debug(f"记录用户活动失败: {e}")

        # 解析命令参数 - 优先使用框架传递的参数
        if args:
            cmd_parts = [str(a).lower() for a in args]
        else:
            # 回退到从消息文本解析
            full_text = event.message_str.strip()
            parts = full_text.split()
            # 移除触发词前缀，获取参数列表
            cmd_parts = []
            if len(parts) > 0 and parts[0].lower() in ["/bd", "bd"]:
                cmd_parts = [p.lower() for p in parts[1:]]

        # 分发到三级菜单处理
        async for result in self._dispatch_menu(event, cmd_parts):
            yield result

    # ==================== 快捷命令入口 ====================

    @filter.command("tools")
    async def shortcut_tools(self, event: AstrMessageEvent):
        """快捷命令 /tools"""
        # 从消息文本解析参数
        full_text = event.message_str.strip()
        parts = full_text.split()
        args = parts[1:] if len(parts) > 1 else []
        cmd_parts = ["tools"] + [a.lower() for a in args]
        async for result in self._dispatch_menu(event, cmd_parts):
            yield result

    @filter.command("admin")
    async def shortcut_admin(self, event: AstrMessageEvent, *args):
        """快捷命令 /admin [子命令]"""
        # 优先使用框架传递的参数，否则从消息文本解析
        if args:
            cmd_parts = ["admin"] + [str(a).lower() for a in args]
        else:
            full_text = event.message_str.strip()
            parts = full_text.split()
            args_list = parts[1:] if len(parts) > 1 else []
            cmd_parts = ["admin"] + [a.lower() for a in args_list]
        async for result in self._dispatch_menu(event, cmd_parts):
            yield result

    @filter.command("games")
    async def shortcut_games(self, event: AstrMessageEvent, *args):
        """快捷命令 /games [子命令]"""
        # 优先使用框架传递的参数，否则从消息文本解析
        if args:
            cmd_parts = ["games"] + [str(a).lower() for a in args]
        else:
            full_text = event.message_str.strip()
            parts = full_text.split()
            args_list = parts[1:] if len(parts) > 1 else []
            cmd_parts = ["games"] + [a.lower() for a in args_list]
        async for result in self._dispatch_menu(event, cmd_parts):
            yield result

    @filter.command("event")
    async def shortcut_event(self, event: AstrMessageEvent, *args):
        """快捷命令 /event [参数]"""
        # 优先使用框架传递的参数，否则从消息文本解析
        if args:
            sub_args = " ".join(str(a) for a in args).strip()
        else:
            full_text = event.message_str.strip()
            parts = full_text.split()
            args_list = parts[1:] if len(parts) > 1 else []
            sub_args = " ".join(args_list).strip()
        async for result in self._handle_event_menu(event, sub_args):
            yield result

    @filter.command("birthday")
    async def shortcut_birthday(self, event: AstrMessageEvent, *args):
        """快捷命令 /birthday [角色名]"""
        # 优先使用框架传递的参数，否则从消息文本解析
        if args:
            char_name = " ".join(str(a) for a in args).strip()
        else:
            full_text = event.message_str.strip()
            parts = full_text.split()
            args_list = parts[1:] if len(parts) > 1 else []
            char_name = " ".join(args_list).strip()
        async for result in self._handle_birthday_query(event, char_name):
            yield result

    @filter.command("subscribe")
    async def shortcut_subscribe(self, event: AstrMessageEvent):
        """快捷命令 /subscribe"""
        user_id = event.get_sender_id()
        if self.subscriber_service.subscribe(user_id):
            yield event.plain_result("订阅成功 - 你将收到每日播报推送")
        else:
            yield event.plain_result("你已经订阅过了")

    @filter.command("unsubscribe")
    async def shortcut_unsubscribe(self, event: AstrMessageEvent):
        """快捷命令 /unsubscribe"""
        user_id = event.get_sender_id()
        if self.subscriber_service.unsubscribe(user_id):
            yield event.plain_result("已取消订阅 - 你将不再收到播报推送")
        else:
            yield event.plain_result("你还没有订阅")

    # ==================== 卡面ID查询命令 ====================

    @filter.command("id")
    async def shortcut_card_id(self, event: AstrMessageEvent, *args):
        """卡面ID查询命令 /id xxxx"""
        # 优先使用框架传递的参数
        card_id_str = ""
        if args:
            for arg in args:
                if str(arg).isdigit():
                    card_id_str = str(arg)
                    break
        
        # 否则从消息文本解析
        if not card_id_str:
            message = event.message_str.strip()
            parts = message.split()
            for part in parts:
                if part.isdigit():
                    card_id_str = part
                    break

        if not card_id_str:
            yield event.plain_result("请输入卡面ID，例如: /id 1234")
            return

        card_id = int(card_id_str)

        # 获取卡片数据
        try:
            cards_data = await self.client.get_cards()
            if str(card_id) not in cards_data:
                yield event.plain_result(f"未找到ID为 {card_id} 的卡面")
                return

            card = Card(card_id, cards_data[str(card_id)])
            official_name = CHARACTER_MAP.get(card.character_id, ["未知"])[0]

            # 设置上下文，保存卡面ID
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.set_context(
                user_id, group_id, menu="card_detail", card_id=card_id
            )

            # 显示卡面信息和选项菜单
            menu = (
                f"[ 卡面查询 - ID: {card_id} ]\n"
                f"------------------------\n"
                f"角色: {official_name}\n"
                f"标题: {card.title}\n"
                f"稀有度: {card.rarity}★ | 属性: {card.attribute.capitalize()}\n"
                f"------------------------\n"
                f"请选择查询内容:\n"
                f"  /1 - 插画信息 (特训前后大图)\n"
                f"  /2 - 详细信息 (卡面详情卡片)\n"
                f"  /0 - 返回上级\n"
                f"------------------------\n"
                f"输入 /1 或 /2 继续"
            )
            yield event.plain_result(menu)

        except Exception as e:
            logger.error(f"卡面ID查询失败: {e}")
            yield event.plain_result(f"查询失败: {e}")

    # ==================== 数字快捷命令 ====================

    @filter.command("0")
    async def shortcut_num_0(self, event: AstrMessageEvent):
        """数字快捷命令 /0"""
        async for result in self._handle_number_shortcut(event, 0):
            yield result

    @filter.command("1")
    async def shortcut_num_1(self, event: AstrMessageEvent):
        """数字快捷命令 /1"""
        async for result in self._handle_number_shortcut(event, 1):
            yield result

    @filter.command("2")
    async def shortcut_num_2(self, event: AstrMessageEvent):
        """数字快捷命令 /2"""
        async for result in self._handle_number_shortcut(event, 2):
            yield result

    @filter.command("3")
    async def shortcut_num_3(self, event: AstrMessageEvent):
        """数字快捷命令 /3"""
        async for result in self._handle_number_shortcut(event, 3):
            yield result

    @filter.command("4")
    async def shortcut_num_4(self, event: AstrMessageEvent):
        """数字快捷命令 /4"""
        async for result in self._handle_number_shortcut(event, 4):
            yield result

    @filter.command("5")
    async def shortcut_num_5(self, event: AstrMessageEvent):
        """数字快捷命令 /5"""
        async for result in self._handle_number_shortcut(event, 5):
            yield result

    @filter.command("6")
    async def shortcut_num_6(self, event: AstrMessageEvent):
        """数字快捷命令 /6"""
        async for result in self._handle_number_shortcut(event, 6):
            yield result

    @filter.command("7")
    async def shortcut_num_7(self, event: AstrMessageEvent):
        """数字快捷命令 /7"""
        async for result in self._handle_number_shortcut(event, 7):
            yield result

    @filter.command("8")
    async def shortcut_num_8(self, event: AstrMessageEvent):
        """数字快捷命令 /8"""
        async for result in self._handle_number_shortcut(event, 8):
            yield result

    @filter.command("9")
    async def shortcut_num_9(self, event: AstrMessageEvent):
        """数字快捷命令 /9"""
        async for result in self._handle_number_shortcut(event, 9):
            yield result

    async def _handle_number_shortcut(self, event: AstrMessageEvent, number: int):
        """处理数字快捷命令"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        # 获取用户当前上下文
        ctx = menu_context.get_context(user_id, group_id)

        if not ctx:
            # 没有上下文，提示用户先进入菜单
            yield event.plain_result("请先输入 /bd 进入菜单")
            return

        # 如果在输入模式中，数字输入可能是用户要输入的参数
        input_mode = ctx.get("input_mode")
        if input_mode:
            # 清除输入模式并将数字作为输入处理
            input_identifier = ctx.get("input_identifier", "")
            menu_context.update_context(
                user_id, group_id, input_mode=None, input_identifier=None
            )
            # 根据 input_identifier 路由到对应处理函数
            if input_identifier == "id" and input_mode == "event_id":
                # 用户输入的是活动ID
                async for result in self._render_event_auto_server(event, number):
                    yield result
                return
            # 其他输入模式可以在这里扩展

        current_menu = ctx.get("menu", "main")

        # 获取对应的菜单项
        item = menu_context.get_item_by_number(current_menu, number)

        if not item:
            yield event.plain_result(f"无效选项: {number}")
            return

        # 处理菜单项
        async for result in self._process_menu_item(event, item, user_id, group_id):
            yield result

    async def _process_menu_item(
        self, event: AstrMessageEvent, item: tuple, user_id: str, group_id: str
    ):
        """处理菜单项选择"""
        num, identifier, desc, action = item

        # 获取当前上下文以保留当前菜单信息
        ctx = menu_context.get_context(user_id, group_id)
        current_menu = ctx.get("menu", "main") if ctx else "main"

        if action.startswith("cmd:"):
            # 执行命令
            cmd = action[4:]
            # 注意：不要在这里清除上下文，因为有些命令（如 card_illustration）需要读取上下文中的数据
            # 上下文的清理工作应由具体的命令处理函数根据需要自行处理
            async for result in self._execute_menu_command(event, cmd):
                yield result
        elif action.startswith("input:"):
            # 需要用户输入 - 保持当前菜单但设置 input_mode
            input_type = action[6:]
            # 保持在当前菜单，只是添加 input_mode 标记
            menu_context.set_context(
                user_id,
                group_id,
                menu=current_menu,
                input_mode=input_type,
                input_identifier=identifier,
            )
            yield event.plain_result(f"请输入{desc}的参数:")
        else:
            # 进入子菜单
            menu_context.set_context(user_id, group_id, menu=action)
            menu_text = menu_context.format_menu(action, self._get_menu_title(action))
            yield event.plain_result(menu_text)

    def _get_menu_title(self, menu: str) -> str:
        """获取菜单标题"""
        titles = {
            "main": "Bestdori 工具箱",
            "tools": "Tools - 工具查询",
            "admin": "Admin - 管理功能",
            "games": "Games - 趣味游戏",
            "event": "Event - 活动查询",
            "card_detail": "Card - 卡面查询",
        }
        return titles.get(menu, menu)

    async def _execute_menu_command(self, event: AstrMessageEvent, cmd: str):
        """执行菜单命令"""
        # 从消息中提取额外参数
        full_text = event.message_str.strip()
        parts = full_text.split()
        extra_args = " ".join(parts[1:]) if len(parts) > 1 else ""

        if cmd == "event":
            async for result in self._handle_event_menu(event, ""):
                yield result
        elif cmd == "event_current":
            async for result in self._render_event(event, target_id=None):
                yield result
        elif cmd == "event_cn":
            async for result in self._render_event(
                event, target_id=None, server=SERVER_CN
            ):
                yield result
        elif cmd == "event_jp":
            async for result in self._render_event(
                event, target_id=None, server=SERVER_JP
            ):
                yield result
        elif cmd == "birthday":
            async for result in self._handle_birthday_query(event, extra_args):
                yield result
        elif cmd == "card":
            async for result in self._handle_card_command(event, ""):
                yield result
        elif cmd == "card_query_char":
            # 提示输入角色名，并设置上下文
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.set_context(user_id, group_id, menu="card_search_input")
            yield event.plain_result("🔍 请输入要查询的角色名称：")
        elif cmd == "card_new":
            async for result in self._render_latest_cards(event, "cn"):
                yield result
        elif cmd == "subscribe":
            user_id = event.get_sender_id()
            if self.subscriber_service.subscribe(user_id):
                yield event.plain_result("订阅成功 - 你将收到每日播报推送")
            else:
                yield event.plain_result("你已经订阅过了")
        elif cmd == "unsubscribe":
            user_id = event.get_sender_id()
            if self.subscriber_service.unsubscribe(user_id):
                yield event.plain_result("已取消订阅")
            else:
                yield event.plain_result("你还没有订阅")
        elif cmd == "mystatus":
            user_id = event.get_sender_id()
            info = self.subscriber_service.get_subscriber_info(user_id)
            if info:
                status = "已订阅" if info.get("subscribed", True) else "未订阅"
                count = info.get("interaction_count", 0)
                yield event.plain_result(f"订阅状态: {status} / 互动次数: {count}")
            else:
                yield event.plain_result("你还没有与 bot 互动过")
        elif cmd == "download":
            yield event.plain_result("开始检查资源完整性...")
            integrity_report = await self.resource_manager.check_resource_integrity()
            total_missing = len(integrity_report["missing_basic"]) + len(
                integrity_report["missing_birthday"]
            )
            if total_missing == 0:
                yield event.plain_result("所有资源完整")
            else:
                yield event.plain_result(
                    f"发现 {total_missing} 个缺失资源，开始下载..."
                )
                asyncio.create_task(
                    self.resource_manager.download_missing_resources(integrity_report)
                )
        elif cmd == "subscribers":
            async for result in self._admin_show_subscribers(event):
                yield result
        elif cmd == "stats":
            async for result in self._admin_show_stats(event):
                yield result
        elif cmd == "clear":
            self.scheduler.state["last_birthday_check"] = None
            self.scheduler.state["last_news_broadcast"] = None
            self.scheduler._save_state()
            yield event.plain_result("已清除今日播报状态")
        elif cmd == "card_illustration":
            # 从上下文获取 card_id
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            ctx = menu_context.get_context(user_id, group_id)
            card_id = ctx.get("card_id") if ctx else None
            if card_id:
                async for result in self._send_card_illustration(event, card_id):
                    yield result
            else:
                yield event.plain_result("未找到卡面ID，请先使用 /id xxxx 查询卡面")
        elif cmd == "card_detail":
            # 从上下文获取 card_id
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            ctx = menu_context.get_context(user_id, group_id)
            card_id = ctx.get("card_id") if ctx else None
            if card_id:
                async for result in self._send_card_detail_page(event, card_id):
                    yield result
            else:
                yield event.plain_result("未找到卡面ID，请先使用 /id xxxx 查询卡面")
        elif cmd == "card_search_all":
            # 从上下文获取 char_id 和 alias
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            ctx = menu_context.get_context(user_id, group_id)
            char_id = ctx.get("char_id") if ctx else None
            char_alias = ctx.get("char_alias", "") if ctx else ""
            if char_id:
                # 重新调用 _handle_card_search，传入 all 参数
                # 注意：为了让 _handle_card_search 识别为带参数调用，我们需要模拟 event.message_str
                # 但更简单的方法是直接复用 _handle_card_search 的内部逻辑，或者直接重构
                # 这里我们稍微 hack 一下，直接构造对应的命令参数
                fake_args = f"/bd {char_alias} all"
                event.message_obj.message_str = fake_args  # 临时修改
                event.message_str = fake_args

                # 清除上下文（或者保留？根据需求，一般执行查询后上下文会结束或改变）
                menu_context.clear_context(user_id, group_id)

                async for result in self._handle_card_search(
                    event, char_id, char_alias
                ):
                    yield result
            else:
                yield event.plain_result(
                    "未找到角色信息，请重新输入 /bd [角色名] 进行查询"
                )
        elif cmd == "card_search_new":
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            ctx = menu_context.get_context(user_id, group_id)
            char_id = ctx.get("char_id") if ctx else None
            char_alias = ctx.get("char_alias", "") if ctx else ""
            if char_id:
                fake_args = f"/bd {char_alias} new"
                event.message_obj.message_str = fake_args
                event.message_str = fake_args
                menu_context.clear_context(user_id, group_id)
                async for result in self._handle_card_search(
                    event, char_id, char_alias
                ):
                    yield result
            else:
                yield event.plain_result(
                    "未找到角色信息，请重新输入 /bd [角色名] 进行查询"
                )
        elif cmd == "card_search_random":
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            ctx = menu_context.get_context(user_id, group_id)
            char_id = ctx.get("char_id") if ctx else None
            char_alias = ctx.get("char_alias", "") if ctx else ""
            if char_id:
                fake_args = f"/bd {char_alias} random"
                event.message_obj.message_str = fake_args
                event.message_str = fake_args
                menu_context.clear_context(user_id, group_id)
                async for result in self._handle_card_search(
                    event, char_id, char_alias
                ):
                    yield result
            else:
                yield event.plain_result(
                    "未找到角色信息，请重新输入 /bd [角色名] 进行查询"
                )
        # 缓存管理命令
        elif cmd == "cache_stats":
            async for result in self._admin_show_cache_stats(event):
                yield result
        elif cmd == "cache_list":
            async for result in self._admin_show_cache_list(event):
                yield result
        elif cmd == "cache_clean":
            async for result in self._admin_cache_clean(event):
                yield result
        elif cmd == "cache_clear":
            # 旧逻辑，直接执行（保留兼容性）
            async for result in self._admin_cache_clear(event):
                yield result
        elif cmd == "cache_clear_confirmed":
            # 新交互式确认后执行
            async for result in self._admin_cache_clear_confirmed(event):
                yield result
        elif cmd == "api_refresh":
            # 旧逻辑，直接执行（保留兼容性）
            async for result in self._admin_api_refresh(event):
                yield result
        elif cmd == "api_refresh_confirmed":
            # 新交互式确认后执行
            async for result in self._admin_api_refresh_confirmed(event):
                yield result
        elif cmd == "api_status":
            async for result in self._admin_api_status(event):
                yield result
        elif cmd == "show_dirs":
            async for result in self._admin_show_dirs(event):
                yield result
        else:
            yield event.plain_result(f"未知命令: {cmd}")

    # ==================== 三级菜单分发系统 ====================

    async def _dispatch_menu(self, event: AstrMessageEvent, cmd_parts: list):
        """三级菜单分发器"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        # 检查是否在等待输入角色名
        ctx = menu_context.get_context(user_id, group_id)
        if ctx and ctx.get("menu") == "card_search_input" and cmd_parts:
            # 这种情况下，用户输入 /bd [角色名] 将被视为输入角色名
            char_name = " ".join(cmd_parts)
            menu_context.clear_context(user_id, group_id)
            async for result in self._handle_card_command(event, char_name):
                yield result
            return

        if not cmd_parts:
            # 一级菜单：显示所有分类，并设置上下文
            menu_context.set_context(user_id, group_id, menu="main")
            async for result in self._show_main_menu(event):
                yield result
            return

        level1 = cmd_parts[0]
        level2 = cmd_parts[1] if len(cmd_parts) > 1 else ""
        rest_args = " ".join(cmd_parts[2:]) if len(cmd_parts) > 2 else ""

        # 二级菜单分发
        if level1 == "tools":
            async for result in self._handle_tools_menu(event, level2, rest_args):
                yield result
        elif level1 == "admin":
            async for result in self._handle_admin_menu(event, level2, rest_args):
                yield result
        elif level1 == "games":
            async for result in self._handle_games_menu(event, level2, rest_args):
                yield result
        elif level1 == "download":
            async for result in self._handle_download_menu(event, level2, rest_args):
                yield result

        # 直接指令分发 (快捷方式)
        elif level1 in ["card", "卡面", "卡"]:
            args = " ".join(cmd_parts[1:])
            async for result in self._handle_card_command(event, args):
                yield result
        elif level1 in ["event", "活动"]:
            args = " ".join(cmd_parts[1:])
            async for result in self._handle_event_menu(event, args):
                yield result
        elif level1 in ["birthday", "生日"]:
            args = " ".join(cmd_parts[1:])
            async for result in self._handle_birthday_query(event, args):
                yield result

        elif level1 in ["help", "帮助"]:
            menu_context.set_context(user_id, group_id, menu="main")
            async for result in self._show_main_menu(event):
                yield result
        else:
            # 尝试作为快捷命令处理（兼容旧指令）
            async for result in self._handle_legacy_command(event, cmd_parts):
                yield result

    async def _show_main_menu(self, event: AstrMessageEvent):
        """显示一级主菜单 - 简洁格式"""
        menu_text = (
            "[ Bestdori 工具箱 ]\n"
            "------------------------\n"
            "  /1 - tools - 工具查询\n"
            "  /2 - admin - 管理功能\n"
            "  /3 - games - 趣味游戏\n"
            "  /4 - download - 资源下载\n"
            "------------------------\n"
            "输入 /序号 或 /标识符 继续"
        )
        yield event.plain_result(menu_text)

    # ==================== Tools 菜单 ====================

    async def _handle_tools_menu(self, event: AstrMessageEvent, cmd: str, args: str):
        """处理 tools 二级菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        if not cmd or cmd == "help":
            menu_context.set_context(user_id, group_id, menu="tools")
            menu_text = (
                "[ Tools - 工具查询 ]\n"
                "------------------------\n"
                "  /1 - event - 活动查询\n"
                "  /2 - birthday - 生日查询\n"
                "  /3 - card - 卡面查询\n"
                "  /0 - back - 返回上级\n"
                "------------------------\n"
                "输入 /序号 或 /标识符 继续"
            )
            yield event.plain_result(menu_text)
            return

        # 三级命令分发
        if cmd in ["event", "活动", "ev"]:
            async for result in self._handle_event_menu(event, args):
                yield result
        elif cmd in ["birthday", "生日", "bd", "bday"]:
            async for result in self._handle_birthday_query(event, args):
                yield result
        elif cmd in ["card", "卡面", "卡"]:
            async for result in self._handle_card_command(event, args):
                yield result
        else:
            yield event.plain_result(f"未知命令: tools {cmd}")

    async def _handle_card_command(self, event: AstrMessageEvent, args: str):
        """处理卡面查询命令 - 支持二级菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        args = args.strip()

        # 情况1：无参数，显示二级菜单
        if not args:
            menu_context.set_context(user_id, group_id, menu="card_menu")
            menu = (
                "🃏 **卡面查询菜单** 🃏\n"
                "------------------------\n"
                "1. 查询指定角色卡面\n"
                "   指令: /bd card [角色名]\n\n"
                "2. 查询最新卡面\n"
                "   指令: /bd card new [服务器]\n"
                "------------------------\n"
                "请输入数字或指令继续"
            )
            yield event.plain_result(menu)
            return

        # 情况2：用户输入了菜单选项 "1" 或 "查询角色"
        if args == "1" or args == "查询角色":
            menu_context.set_context(user_id, group_id, menu="card_search_input")
            yield event.plain_result("🔍 请输入要查询的角色名称：")
            return

        # 情况3：用户输入了菜单选项 "2" 或 "new" 或 "最新"
        if args == "2" or args.lower().startswith("new") or args == "最新":
            # 解析服务器参数
            server_str = "cn"
            parts = args.split()
            if len(parts) > 1:
                server_str = parts[1]
            elif args.lower().startswith("new") and len(args) > 3:
                # 处理 "newcn" 这种连写情况
                server_str = args[3:].strip() or "cn"

            async for result in self._render_latest_cards(event, server_str):
                yield result
            return

        # 情况4：用户直接输入了参数（默认为角色名搜索），保留原有逻辑

        # 检查是否在 card_search_input 上下文中
        ctx = menu_context.get_context(user_id, group_id)
        if ctx and ctx.get("menu") == "card_search_input":
            # 清除上下文
            menu_context.clear_context(user_id, group_id)

        # 兼容处理：如果是 "jp ksm" 这种格式，虽然 _handle_card_search 目前不支持服务器筛选（它显示所有卡），
        # 但我们可以尝试提取角色名。
        # 目前 _handle_card_search 接受 char_id 和 original_name。

        # 尝试解析角色
        char_id = get_character_id_by_name(args)
        if char_id > 0:
            async for result in self._handle_card_search(event, char_id, args):
                yield result
        else:
            # 可能是 ID 查询？
            if args.isdigit():
                # 转发给 id 查询
                # 为了避免重新解析，我们直接调用逻辑，或者简单提示
                yield event.plain_result(
                    f"未找到角色: {args}。如果是查询卡面ID，请使用 /id {args}"
                )
            else:
                yield event.plain_result(f"未找到角色: {args}")

    async def _render_latest_cards(
        self, event: AstrMessageEvent, server_str: str = "cn"
    ):
        """渲染最新卡面列表（基于最近3个活动的新卡面，使用模板渲染）"""
        server = get_server_id(server_str)
        server_code = SERVER_CODE_MAP.get(server, "cn")
        server_name = SERVER_NAME_MAP.get(server, "国服")

        yield event.plain_result(f"🎨 正在获取{server_name}最近活动的新卡面数据...")

        try:
            # 获取活动和卡面数据
            events_data = await self.client.get_events()
            cards_data = await self.client.get_cards()

            # 筛选该服务器已开始的活动，按开始时间倒序排序
            now_ts = int(datetime.now().timestamp() * 1000)
            server_events = []
            for eid, edata in events_data.items():
                ev = Event(int(eid), edata)
                start_time = ev.get_start_time(server=server)
                if start_time and start_time <= now_ts:
                    server_events.append((ev, start_time))

            # 按开始时间倒序排序，取最近3个活动
            server_events.sort(key=lambda x: x[1], reverse=True)
            recent_events = [(item[0], item[1]) for item in server_events[:3]]

            if not recent_events:
                yield event.plain_result(f"❌ 未找到{server_name}的活动数据")
                return

            # 根据活动时间窗口匹配卡面
            # 活动的新卡面通常在活动开始前后2天内发布
            latest_cards = []
            TIME_WINDOW = 2 * 24 * 3600 * 1000  # 2天的毫秒数

            for ev, ev_start in recent_events:
                logger.info(f"处理活动 {ev.event_id} ({ev.name})，开始时间: {ev_start}")

                # 查找时间窗口内发布的卡面
                for cid, cdata in cards_data.items():
                    card = Card(int(cid), cdata)
                    release_time = card.get_released_at(server=server)

                    # 检查是否在活动时间窗口内
                    if release_time and abs(release_time - ev_start) < TIME_WINDOW:
                        # 避免重复添加
                        if not any(c.card_id == card.card_id for c in latest_cards):
                            latest_cards.append(card)
                            logger.info(
                                f"  找到卡面 {card.card_id} ({card.rarity}星 {card.attribute})"
                            )

            # 按稀有度和卡面ID排序（高稀有度优先，同稀有度按ID倒序）
            latest_cards.sort(key=lambda c: (-c.rarity, -c.card_id))

            if not latest_cards:
                yield event.plain_result(f"❌ 未找到{server_name}最近活动的新卡面")
                return

            logger.info(f"共找到 {len(latest_cards)} 张最近活动卡面")

            # 构建模板数据（与 event_overview_card.html 中 new_cards 格式一致）
            template_cards = []
            for card in latest_cards:
                char_name = CHARACTER_MAP.get(card.character_id, ["未知角色"])[0]

                # 获取乐队图标
                card_band_icon = None
                band_id = CHARACTER_BAND_MAP.get(card.character_id)
                if band_id:
                    band_svg = BAND_ICON_URL_MAP.get(band_id)
                    if band_svg:
                        card_band_icon = f"https://bestdori.com/res/icon/{band_svg}"

                # 获取属性图标
                card_attr_icon = None
                if card.attribute:
                    card_attr_icon = (
                        f"https://bestdori.com/res/icon/{card.attribute}.svg"
                    )

                card_info = {
                    "card_id": card.card_id,
                    "character_name": char_name,
                    "title": card.title or "无标题",
                    "rarity": card.rarity,
                    "attribute": card.attribute or "unknown",
                    "unidolized_image": card.get_card_icon_url(
                        "rip_normal", server=server_code
                    ),
                    "idolized_image": card.get_card_icon_url(
                        "rip_trained", server=server_code
                    )
                    if card.rarity >= 3
                    else None,
                    "band_icon": card_band_icon,
                    "attr_icon": card_attr_icon,
                    "frame_url": card.get_rip_frame_url(),  # rip大图使用 frame-X 系列
                }
                # 调试日志：验证外框URL
                logger.info(
                    f"最新卡面 {card.card_id} ({card.rarity}星): frame_url={card_info['frame_url']}"
                )
                template_cards.append(card_info)

            # 构建渲染数据
            render_data = {
                "server_name": server_name,
                "event_count": len(recent_events),
                "card_count": len(latest_cards),
                "cards": template_cards,
            }

            # 使用模板渲染
            output_dir = os.path.join(self.client.cache_dir, "images")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir,
                f"latest_cards_{server_code}_{int(datetime.now().timestamp())}.png",
            )

            self.renderer.render_latest_cards(render_data, output_path)

            if os.path.exists(output_path):
                yield event.image_result(output_path)
                yield event.plain_result(
                    "💡 提示：使用 /id [卡面ID] 可获取该卡面的高清插画大图"
                )
            else:
                yield event.plain_result("❌ 图片生成失败，渲染未产生输出文件")

        except RuntimeError as e:
            # 渲染相关的运行时错误（如 Chrome 不可用）
            logger.error(f"渲染最新卡面失败: {e}")
            yield event.plain_result(f"❌ 渲染失败: {e}")
        except Exception as e:
            logger.error(f"获取最新卡面失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            yield event.plain_result(f"❌ 获取失败: {e}")

    # ==================== Admin 菜单 ====================

    def _is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        admin_users = self._get_config("admin_users", [])
        # 转换为字符串列表进行比较
        admin_users_str = [str(uid) for uid in admin_users]
        return str(user_id) in admin_users_str

    async def _handle_admin_menu(self, event: AstrMessageEvent, cmd: str, args: str):
        """处理 admin 二级菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        # 检查管理员权限
        if not self._is_admin(user_id):
            yield event.plain_result(
                "⛔ 权限不足，只有管理员才能使用此功能。\n请联系管理员将你的QQ号添加到配置文件中的 admin_users 列表。"
            )
            return

        if not cmd or cmd == "help":
            menu_context.set_context(user_id, group_id, menu="admin")
            menu_text = (
                "[ Admin - 管理功能 ]\n"
                "------------------------\n"
                "  /1 - subscribe - 订阅播报\n"
                "  /2 - unsubscribe - 取消订阅\n"
                "  /3 - mystatus - 我的状态\n"
                "  /4 - subscribers - 订阅列表\n"
                "  /5 - stats - 播报统计\n"
                "  /6 - clear - 清除播报状态\n"
                "  /7 - cache - 缓存管理 →\n"
                "  /8 - settings - 目录设置 →\n"
                "  /0 - back - 返回上级\n"
                "------------------------\n"
                "输入 /序号 或 /标识符 继续"
            )
            yield event.plain_result(menu_text)
            return

        # 三级命令分发
        if cmd in ["subscribe", "订阅", "sub"]:
            target_user_id = event.get_sender_id()
            if self.subscriber_service.subscribe(target_user_id):
                yield event.plain_result("✅ 订阅成功！你将收到每日播报推送。")
            else:
                yield event.plain_result("📌 你已经订阅过了哦~")

        elif cmd in ["unsubscribe", "取消订阅", "unsub"]:
            target_user_id = event.get_sender_id()
            if self.subscriber_service.unsubscribe(target_user_id):
                yield event.plain_result("✅ 已取消订阅，你将不再收到播报推送。")
            else:
                yield event.plain_result("📌 你还没有订阅哦~")

        elif cmd in ["mystatus", "我的状态", "status", "me"]:
            target_user_id = event.get_sender_id()
            info = self.subscriber_service.get_subscriber_info(target_user_id)
            if info:
                status = "已订阅" if info.get("subscribed", True) else "未订阅"
                count = info.get("interaction_count", 0)
                yield event.plain_result(f"订阅状态: {status} / 互动次数: {count}")
            else:
                yield event.plain_result("你还没有与 bot 互动过")

        elif cmd in ["subscribers", "subs", "用户", "订阅列表"]:
            async for result in self._admin_show_subscribers(event):
                yield result

        elif cmd in ["stats", "统计", "状态"]:
            async for result in self._admin_show_stats(event):
                yield result

        elif cmd in ["clear", "清除", "重置"]:
            self.scheduler.state["last_birthday_check"] = None
            self.scheduler.state["last_news_broadcast"] = None
            self.scheduler._save_state()
            yield event.plain_result("✅ 已清除今日播报状态")

        elif cmd in ["cache", "缓存", "缓存管理"]:
            async for result in self._handle_cache_menu(event, args):
                yield result

        elif cmd in ["settings", "设置", "目录设置"]:
            async for result in self._handle_settings_menu(event, args):
                yield result

        # 向后兼容旧命令
        elif cmd in ["cache_stats", "缓存统计"]:
            async for result in self._admin_show_cache_stats(event):
                yield result

        elif cmd in ["cache_clean", "清理缓存"]:
            async for result in self._admin_cache_clean(event):
                yield result

        elif cmd in ["cache_clear", "清空缓存"]:
            async for result in self._admin_cache_clear(event):
                yield result

        elif cmd in ["cache_clear_confirm", "确认清空"]:
            async for result in self._admin_cache_clear_confirm(event):
                yield result

        else:
            yield event.plain_result(f"未知命令: admin {cmd}")

    async def _handle_cache_menu(self, event: AstrMessageEvent, cmd: str):
        """处理缓存管理子菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        if not cmd or cmd == "help":
            menu_context.set_context(user_id, group_id, menu="cache")
            menu_text = (
                "[ Cache - 缓存管理 ]\n"
                "------------------------\n"
                "  /1 - cache_stats - 查看统计\n"
                "  /2 - cache_list - 查看列表\n"
                "  /3 - cache_clean - 清理过期\n"
                "  /4 - cache_clear - 清空渲染缓存\n"
                "  /5 - api_refresh - 刷新API数据\n"
                "  /6 - api_status - API缓存状态\n"
                "  /0 - back - 返回上级\n"
                "------------------------\n"
                "输入 /序号 或 /标识符 继续"
            )
            yield event.plain_result(menu_text)
            return

        if cmd in ["1", "cache_stats", "stats", "统计"]:
            async for result in self._admin_show_cache_stats(event):
                yield result
        elif cmd in ["2", "cache_list", "list", "列表"]:
            async for result in self._admin_show_cache_list(event):
                yield result
        elif cmd in ["3", "cache_clean", "clean", "清理"]:
            async for result in self._admin_cache_clean(event):
                yield result
        elif cmd in ["4", "cache_clear", "clear", "清空"]:
            async for result in self._admin_cache_clear(event):
                yield result
        elif cmd in ["cache_clear_confirm", "确认清空"]:
            async for result in self._admin_cache_clear_confirm(event):
                yield result
        elif cmd in ["5", "api_refresh", "refresh", "刷新"]:
            async for result in self._admin_api_refresh(event):
                yield result
        elif cmd in ["6", "api_status", "api", "状态"]:
            async for result in self._admin_api_status(event):
                yield result
        else:
            yield event.plain_result(f"未知命令: cache {cmd}")

    async def _handle_settings_menu(self, event: AstrMessageEvent, cmd: str):
        """处理目录设置子菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        if not cmd or cmd == "help":
            menu_context.set_context(user_id, group_id, menu="settings")
            menu_text = (
                "[ Settings - 目录设置 ]\n"
                "------------------------\n"
                "  /1 - show_dirs - 查看目录\n"
                "  /2 - set_cache_dir - 设置缓存目录\n"
                "  /3 - set_download_dir - 设置下载目录\n"
                "  /4 - reset_dirs - 恢复默认目录\n"
                "  /0 - back - 返回上级\n"
                "------------------------\n"
                "输入 /序号 或 /标识符 继续"
            )
            yield event.plain_result(menu_text)
            return

        if cmd in ["1", "show_dirs", "show", "查看"]:
            async for result in self._admin_show_dirs(event):
                yield result
        elif cmd in ["2", "set_cache_dir", "cache_dir"]:
            yield event.plain_result(
                "⚠️ 暂不支持运行时修改目录，请在配置文件中设置 cache_dir"
            )
        elif cmd in ["3", "set_download_dir", "download_dir"]:
            yield event.plain_result(
                "⚠️ 暂不支持运行时修改目录，请在配置文件中设置 download_dir"
            )
        elif cmd in ["4", "reset_dirs", "reset", "重置"]:
            yield event.plain_result(
                "⚠️ 暂不支持运行时重置目录，请在配置文件中清空 cache_dir 和 download_dir"
            )
        else:
            yield event.plain_result(f"未知命令: settings {cmd}")

    async def _handle_download_menu(self, event: AstrMessageEvent, cmd: str, args: str):
        """处理下载功能菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        if not cmd or cmd == "help":
            menu_context.set_context(user_id, group_id, menu="download")
            menu_text = (
                "[ Download - 资源下载 ]\n"
                "------------------------\n"
                "  /1 - dl_card - 卡面下载\n"
                "  /2 - dl_voice - 语音下载\n"
                "  /3 - dl_story - 故事下载\n"
                "  /4 - dl_asset - 素材下载\n"
                "  /0 - back - 返回上级\n"
                "------------------------\n"
                "输入 /序号 或 /标识符 继续"
            )
            yield event.plain_result(menu_text)
            return

        if cmd in ["1", "dl_card", "card", "卡面"]:
            yield event.plain_result("🚧 卡面下载功能开发中...")
        elif cmd in ["2", "dl_voice", "voice", "语音"]:
            yield event.plain_result("🚧 语音下载功能开发中...")
        elif cmd in ["3", "dl_story", "story", "故事"]:
            yield event.plain_result("🚧 故事下载功能开发中...")
        elif cmd in ["4", "dl_asset", "asset", "素材"]:
            yield event.plain_result("🚧 素材下载功能开发中...")
        else:
            yield event.plain_result(f"未知命令: download {cmd}")

    async def _admin_show_subscribers(self, event: AstrMessageEvent):
        """显示订阅用户列表"""
        subscribers = self.subscriber_service.get_all_subscribers_info()
        total = len(subscribers)

        if total == 0:
            yield event.plain_result("暂无订阅用户")
            return

        lines = [f"[ 订阅用户列表 ] 共 {total} 人"]
        lines.append("-" * 24)

        shown = 0
        for user_id, info in subscribers.items():
            if shown >= 20:
                lines.append(f"... 还有 {total - 20} 个用户")
                break

            nickname = info.get("nickname", "未知")
            count = info.get("interaction_count", 0)
            status = "+" if info.get("subscribed", True) else "-"
            lines.append(f"  {status} {nickname} ({user_id}) x{count}")
            shown += 1

        blacklist = self._get_config("broadcast_users_blacklist", [])
        if blacklist:
            lines.append(f"黑名单: {len(blacklist)} 人")

        yield event.plain_result("\n".join(lines))

    async def _admin_show_stats(self, event: AstrMessageEvent):
        """显示播报统计"""
        subscriber_count = self.subscriber_service.get_subscriber_count()
        groups = self._get_config("broadcast_groups", [])
        blacklist = self._get_config("broadcast_users_blacklist", [])

        birthday_config = self._get_config("birthday_broadcast", {})
        news_config = self._get_config("news_broadcast", {})

        stats_text = (
            "[ 播报统计 ]\n"
            "------------------------\n"
            f"订阅用户: {subscriber_count} 人\n"
            f"播报群组: {len(groups)} 个\n"
            f"黑名单: {len(blacklist)} 人\n"
            "------------------------\n"
            f"生日祝福: {birthday_config.get('broadcast_hour', 0):02d}:{birthday_config.get('broadcast_minute', 0):02d}\n"
            f"每日资讯: {news_config.get('broadcast_hour', 9):02d}:{news_config.get('broadcast_minute', 0):02d}"
        )
        yield event.plain_result(stats_text)

    # ==================== Games 菜单 ====================

    async def _handle_games_menu(self, event: AstrMessageEvent, cmd: str, args: str):
        """处理 games 二级菜单"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        if not cmd or cmd == "help":
            menu_context.set_context(user_id, group_id, menu="games")
            menu_text = (
                "[ Games - 趣味游戏 ]\n"
                "------------------------\n"
                "  开发中...\n"
                "  /0 - back - 返回上级\n"
                "------------------------\n"
                "敬请期待"
            )
            yield event.plain_result(menu_text)
            return

        # TODO: 添加游戏功能
        yield event.plain_result(f"games/{cmd} 功能开发中")

    # ==================== 兼容旧命令 ====================

    async def _handle_legacy_command(self, event: AstrMessageEvent, cmd_parts: list):
        """处理兼容旧版的快捷命令"""
        cmd = cmd_parts[0] if cmd_parts else ""
        args = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""

        # 活动快捷命令
        if cmd.startswith("event"):
            sub_args = cmd[5:].strip() + " " + args
            async for result in self._handle_event_menu(event, sub_args.strip()):
                yield result
            return

        # 生日快捷命令
        if cmd.startswith("birthday"):
            char_name = cmd[8:].strip() + " " + args
            async for result in self._handle_birthday_query(event, char_name.strip()):
                yield result
            return

        # 订阅命令
        if cmd in ["subscribe", "订阅", "sub"]:
            user_id = event.get_sender_id()
            if self.subscriber_service.subscribe(user_id):
                yield event.plain_result("订阅成功")
            else:
                yield event.plain_result("你已经订阅过了")
            return

        if cmd in ["unsubscribe", "取消订阅", "unsub"]:
            user_id = event.get_sender_id()
            if self.subscriber_service.unsubscribe(user_id):
                yield event.plain_result("已取消订阅")
            else:
                yield event.plain_result("你还没有订阅")
            return

        if cmd in ["mystatus", "我的状态", "status"]:
            user_id = event.get_sender_id()
            info = self.subscriber_service.get_subscriber_info(user_id)
            if info:
                status = "已订阅" if info.get("subscribed", True) else "未订阅"
                count = info.get("interaction_count", 0)
                yield event.plain_result(f"订阅状态: {status} / 互动次数: {count}")
            else:
                yield event.plain_result("你还没有与 bot 互动过")
            return

        # 资源下载
        if cmd == "all":
            yield event.plain_result("开始检查资源完整性...")
            integrity_report = await self.resource_manager.check_resource_integrity()
            total_missing = len(integrity_report["missing_basic"]) + len(
                integrity_report["missing_birthday"]
            )

            if total_missing == 0:
                yield event.plain_result("所有资源完整")
            else:
                yield event.plain_result(
                    f"发现 {total_missing} 个缺失资源，开始下载..."
                )
                asyncio.create_task(
                    self.resource_manager.download_missing_resources(integrity_report)
                )
            return

        # 尝试作为角色名查询卡面
        char_id = get_character_id_by_name(cmd)
        if char_id > 0:
            async for result in self._handle_card_search(event, char_id, cmd):
                yield result
            return

        # 未知命令
        yield event.plain_result(f"未知指令: {cmd} - 输入 /bd 查看菜单")

    async def _handle_event_menu(self, event: AstrMessageEvent, sub_cmd: str):
        """处理活动查询逻辑"""
        user_id = event.get_sender_id()
        group_id = (
            event.message_obj.group_id if hasattr(event.message_obj, "group_id") else ""
        )

        if not sub_cmd:
            menu_context.set_context(user_id, group_id, menu="event")
            # 使用 menu_context 生成菜单文本确保一致性
            menu_text = menu_context.format_menu("event", "Event - 活动查询")
            menu_text += "\n或直接输入: /event 297\n💡 日服活动进度领先国服约1年"
            yield event.plain_result(menu_text)
            return

        # 处理生日查询
        if sub_cmd.startswith("0"):
            # 提取角色名（如果有）
            char_name = sub_cmd[1:].strip()
            # 如果有角色名，直接查询该角色；否则查询今日生日
            if char_name:
                # 查询指定角色的生日
                async for result in self._handle_birthday_query(event, char_name):
                    yield result
            else:
                # 查询今日生日
                async for result in self._handle_birthday_query(event, ""):
                    yield result
            return

        # 处理当期活动查询（国服）
        if sub_cmd in ["1", "current", "当期", "now", "cn", "国服"]:
            async for result in self._render_event(
                event, target_id=None, server=SERVER_CN
            ):
                yield result
        # 处理当期活动查询（日服）
        elif sub_cmd in ["2", "jp", "日服"]:
            async for result in self._render_event(
                event, target_id=None, server=SERVER_JP
            ):
                yield result
        # 处理指定ID查询
        elif sub_cmd.isdigit():
            event_id = int(sub_cmd)
            # 对于指定ID查询，自动判断活动在哪个服务器可用
            async for result in self._render_event_auto_server(event, event_id):
                yield result
        # 处理带服务器前缀的查询，如 "jp 350" 或 "cn 298"
        elif " " in sub_cmd:
            parts = sub_cmd.split(maxsplit=1)
            server_str = parts[0].lower()
            id_str = parts[1] if len(parts) > 1 else ""

            server = get_server_id(server_str)
            if id_str.isdigit():
                async for result in self._render_event(
                    event, target_id=int(id_str), server=server
                ):
                    yield result
            else:
                yield event.plain_result(f"无效的活动ID: {id_str}")
        else:
            yield event.plain_result("无效指令 - 输入 /event 查看帮助")

    async def _render_event_auto_server(self, event: AstrMessageEvent, event_id: int):
        """自动判断服务器并渲染活动

        优先级：国服 > 日服 > 其他
        """
        try:
            events_data = await self.client.get_events()
            event_data = events_data.get(str(event_id))

            if not event_data:
                yield event.plain_result(f"❌ 未找到活动ID {event_id}")
                return

            ev = Event(event_id, event_data)
            available_servers = ev.get_available_servers()

            if not available_servers:
                yield event.plain_result(f"❌ 活动 {event_id} 暂无任何服务器数据")
                return

            # 按优先级选择服务器
            selected_server = SERVER_CN
            for s in DEFAULT_SERVER_PRIORITY:
                if s in available_servers:
                    selected_server = s
                    break

            # 如果不是国服，提示用户
            if selected_server != SERVER_CN:
                server_name = SERVER_NAME_MAP.get(selected_server, "未知")
                yield event.plain_result(
                    f"📌 活动 {event_id} 国服暂未上线，使用{server_name}数据"
                )

            async for result in self._render_event(
                event, target_id=event_id, server=selected_server
            ):
                yield result

        except Exception as e:
            logger.error(f"自动服务器选择失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {e}")

    async def _render_event(
        self, event: AstrMessageEvent, target_id: int = None, server: int = SERVER_CN
    ):
        """渲染指定活动的详情图（使用新的活动一览模板）

        Args:
            event: 消息事件
            target_id: 活动ID，None表示查询当期最新活动
            server: 服务器ID (0=JP, 1=EN, 2=TW, 3=CN, 4=KR)
        """
        import random

        # 确保基础素材存在
        await self.resource_manager.ensure_basic_assets()

        server_name = SERVER_NAME_MAP.get(server, "未知")
        server_code = SERVER_CODE_MAP.get(server, "cn")

        # 首先获取活动数据以确定实际的活动ID
        try:
            events_data = await self.client.get_events()
            events = [Event(int(eid), data) for eid, data in events_data.items()]
            server_events = [
                e for e in events if e.get_start_time(server=server) is not None
            ]

            if not server_events:
                yield event.plain_result(f"⚠️ 未找到{server_name}活动数据。")
                return

            # 选择目标活动
            if target_id is None:
                # 查询当期最新活动
                server_events.sort(
                    key=lambda x: x.get_start_time(server=server), reverse=True
                )
                latest = server_events[0]
            else:
                # 查询指定ID的活动
                latest = next(
                    (e for e in server_events if e.event_id == target_id), None
                )
                if latest is None:
                    yield event.plain_result(
                        f"❌ 未找到活动ID {target_id} 的{server_name}数据。"
                    )
                    return

            # 检查缓存（缓存键包含服务器信息）
            cached_image = await self.cache_manager.get_cache(
                "event", event_id=latest.event_id, server=server
            )
            if cached_image:
                logger.info(f"命中活动缓存: event_{latest.event_id}_{server_code}")
                yield event.image_result(cached_image)
                return

            yield event.plain_result(f"🎨 正在生成{server_name}活动情报图...")
        except Exception as e:
            logger.error(f"获取活动数据失败: {e}")
            yield event.plain_result(f"❌ 获取活动数据失败: {e}")
            return

        try:
            # --- 准备新模板的渲染数据 ---
            event_start = latest.get_start_time(server=server)

            # 格式化日期 - 保持完整的日期时间格式
            start_time = latest.get_formatted_time(True, server=server)
            end_time = latest.get_formatted_time(False, server=server)

            # 获取活动加成属性和参会角色图标
            attr_icon = None
            char_icons = []

            # 获取第一个加成属性的图标
            if latest.bonus_attributes:
                attr_icon = (
                    f"https://bestdori.com/res/icon/{latest.bonus_attributes[0]}.svg"
                )

            # 获取参会角色图标（最多5个）
            for char_id in latest.bonus_characters[:5]:
                char_icons.append(
                    f"https://bestdori.com/res/icon/chara_icon_{char_id}.png"
                )

            # 标题徽章图片路径
            title_badge_path = os.path.join(
                self.client.cache_dir, "event_aeests", "title.png"
            )
            title_badge_url = None
            if os.path.exists(title_badge_path):
                # 将本地路径转换为 file:// URL
                title_badge_url = f"file:///{title_badge_path.replace(os.sep, '/')}"

            # 新成员图片路径
            newmember_path = os.path.join(
                self.client.cache_dir, "event_aeests", "newmember.png"
            )
            newmember_url = None
            if os.path.exists(newmember_path):
                newmember_url = f"file:///{newmember_path.replace(os.sep, '/')}"

            # 服务器标识（非国服时显示）
            server_badge = None
            if server != SERVER_CN:
                server_badge = SERVER_SHORT_NAME_MAP.get(server, "")

            render_data = {
                "event_name": latest.get_name(server=server),
                "start_time": start_time,
                "end_time": end_time,
                "event_type": latest.event_type_cn or "活动",
                "event_type_icon": latest.event_type_icon,
                "event_logo": latest.get_logo_url(server=server),
                "cover_image": None,  # 5星卡面特训前大图
                "title_badge_image": title_badge_url,
                "newmember_image": newmember_url,
                "band_icon": None,  # 第一张新卡面成员所属乐队图标
                "attr_icon": attr_icon,
                "char_icons": char_icons,
                "new_cards": [],
                "reward_cards": [],  # 所有★3报酬卡面列表
                "bonus_songs": [],  # 支持多首追加歌曲
                "stamp_reward": None,
                "gacha_list": [],
                "server_badge": server_badge,  # 服务器标识
                "server_code": server_code,  # 用于资源URL
            }

            # --- 获取活动详情（追加歌曲、表情包、报酬卡面）---
            try:
                event_detail = await self.client.get_event_detail(latest.event_id)

                # 获取活动时间范围（使用指定服务器）
                event_start_at = event_detail.get("startAt", [])
                event_end_at = event_detail.get("endAt", [])
                server_event_start = None
                server_event_end = None

                if (
                    isinstance(event_start_at, list)
                    and server < len(event_start_at)
                    and event_start_at[server]
                ):
                    server_event_start = int(event_start_at[server])
                if (
                    isinstance(event_end_at, list)
                    and server < len(event_end_at)
                    and event_end_at[server]
                ):
                    server_event_end = int(event_end_at[server])

                # 获取追加歌曲
                songs_data = await self.client.get_songs()
                bonus_songs = []
                for song_id, song_info in songs_data.items():
                    pub_at = song_info.get("publishedAt", [])
                    song_pub_ts = None
                    if (
                        pub_at
                        and isinstance(pub_at, list)
                        and server < len(pub_at)
                        and pub_at[server]
                    ):
                        song_pub_ts = (
                            int(pub_at[server])
                            if isinstance(pub_at[server], str)
                            else pub_at[server]
                        )

                    if song_pub_ts and server_event_start and server_event_end:
                        if server_event_start <= song_pub_ts <= server_event_end:
                            titles = song_info.get("musicTitle", [])
                            # 优先使用指定服务器的标题
                            title = None
                            if (
                                isinstance(titles, list)
                                and server < len(titles)
                                and titles[server]
                            ):
                                title = titles[server]
                            if not title and titles:
                                title = next(
                                    (t for t in titles if t), f"歌曲 {song_id}"
                                )

                            band_id = song_info.get("bandId", 0)

                            # 构建歌曲封面URL（使用指定服务器）
                            sid = int(song_id)
                            jacket_group = (sid // 10) * 10 + 10
                            jacket_url = None

                            try:
                                song_detail = await self.client.get_song_detail(sid)
                                if song_detail:
                                    bgm_file = song_detail.get("bgmFile", "")
                                    if bgm_file:
                                        jacket_url = f"https://bestdori.com/assets/{server_code}/musicjacket/musicjacket{jacket_group}_rip/assets-star-forassetbundle-startapp-musicjacket-musicjacket{jacket_group}-{bgm_file}-jacket.png"
                            except:
                                pass

                            if not jacket_url:
                                jacket_url = (
                                    f"https://bestdori.com/res/icon/band_{band_id}.svg"
                                    if band_id
                                    else "https://bestdori.com/res/icon/song_jacket.png"
                                )

                            bonus_songs.append(
                                {
                                    "title": title,
                                    "jacket": jacket_url,
                                    "song_id": sid,
                                    "band_id": band_id,
                                }
                            )

                bonus_songs.sort(key=lambda x: x["song_id"])
                render_data["bonus_songs"] = bonus_songs

                # 获取表情包奖励
                if event_detail and "pointRewards" in event_detail:
                    point_rewards = event_detail.get("pointRewards", [])
                    server_rewards = None
                    if isinstance(point_rewards, list) and server < len(point_rewards):
                        server_rewards = point_rewards[server]
                    # 如果指定服务器没有数据，尝试回退
                    if not server_rewards and isinstance(point_rewards, list):
                        for s in DEFAULT_SERVER_PRIORITY:
                            if s < len(point_rewards) and point_rewards[s]:
                                server_rewards = point_rewards[s]
                                break

                    if server_rewards:
                        # 只获取表情包奖励（报酬卡面从新卡面列表中获取）
                        for reward in server_rewards:
                            if isinstance(reward, dict):
                                reward_type = reward.get("rewardType")
                                if (
                                    reward_type == "stamp"
                                    and not render_data["stamp_reward"]
                                ):
                                    stamp_id = reward.get("rewardId")
                                    if stamp_id:
                                        try:
                                            stamps_data = await self.client.get_stamps()
                                            stamp_info = stamps_data.get(
                                                str(stamp_id), {}
                                            )
                                            image_name = stamp_info.get("imageName", "")
                                            if image_name:
                                                stamp_url = f"https://bestdori.com/assets/{server_code}/stamp/01_rip/{image_name}.png"
                                                render_data["stamp_reward"] = {
                                                    "image": stamp_url
                                                }
                                        except:
                                            pass
            except Exception as e:
                logger.warning(f"获取活动详情失败: {e}")

            # --- 获取卡面和招募数据 ---
            if event_start:
                cards_data = await self.client.get_cards()
                gachas_data = await self.client.get_gachas()
                costumes_data = (
                    await self.client.get_costumes()
                )  # 提前获取，避免循环中重复调用

                # 获取新卡面信息
                temp_cards = []
                five_star_cards = []  # 收集5星卡面用于随机选取封面

                for cid, cdata in cards_data.items():
                    card = Card(int(cid), cdata)
                    release_time = card.get_released_at(server=server)
                    # 使用时间窗口匹配
                    if release_time and abs(release_time - event_start) < 172800000:
                        # 获取角色名
                        resource_id = card.character_id
                        if card.resource_set_name and len(card.resource_set_name) >= 6:
                            try:
                                resource_id = int(card.resource_set_name[3:6])
                            except:
                                pass

                        char_name = CHARACTER_MAP.get(resource_id, ["未知"])[0]

                        # 获取卡面图片URL（使用指定服务器）
                        normal_url = card.get_card_icon_url(
                            "rip_normal", server=server_code
                        )
                        trained_url = card.get_card_icon_url(
                            "rip_trained", server=server_code
                        )

                        # 获取特训前大图URL（用于封面）- 使用 rip_normal 大图
                        normal_rip_url = card.get_card_icon_url(
                            "rip_normal", server=server_code
                        )

                        # 获取卡面的乐队图标和属性图标
                        card_band_icon = None
                        card_attr_icon = None
                        if card.character_id:
                            band_id = CHARACTER_BAND_MAP.get(card.character_id)
                            if band_id:
                                band_svg = BAND_ICON_URL_MAP.get(band_id)
                                if band_svg:
                                    card_band_icon = (
                                        f"https://bestdori.com/res/icon/{band_svg}"
                                    )
                        if card.attribute:
                            card_attr_icon = (
                                f"https://bestdori.com/res/icon/{card.attribute}.svg"
                            )

                        card_info = {
                            "character_name": char_name,
                            "title": card.title or "限定卡面",
                            "rarity": card.rarity,
                            "attribute": card.attribute or "unknown",
                            "unidolized_image": normal_url,
                            "idolized_image": trained_url,
                            "normal_rip_url": normal_rip_url,  # 大图URL
                            "character_id": card.character_id,  # 用于获取乐队信息
                            "band_icon": card_band_icon,  # 乐队图标
                            "attr_icon": card_attr_icon,  # 属性图标
                            "frame_url": card.get_rip_frame_url(),  # 外框URL (rip大图用 frame-X)
                        }
                        # 调试日志：验证外框URL
                        logger.info(
                            f"新卡面 {card.card_id} ({card.rarity}星): frame_url={card_info['frame_url']}"
                        )
                        temp_cards.append(card_info)

                        # 收集5星卡面
                        if card.rarity == 5 and normal_rip_url:
                            five_star_cards.append(normal_rip_url)

                        # 收集★3报酬卡面（活动期间发布的3星卡就是报酬卡）
                        if card.rarity == 3:
                            # 获取卡面图片URL - 使用特训后大图
                            card_image_url = card.get_card_icon_url(
                                "rip_trained", server=server_code
                            )

                            # 获取乐队图标和属性图标
                            reward_band_icon = None
                            reward_attr_icon = None
                            if card.character_id:
                                band_id = CHARACTER_BAND_MAP.get(card.character_id)
                                if band_id:
                                    band_svg = BAND_ICON_URL_MAP.get(band_id)
                                    if band_svg:
                                        reward_band_icon = (
                                            f"https://bestdori.com/res/icon/{band_svg}"
                                        )
                            if card.attribute:
                                reward_attr_icon = f"https://bestdori.com/res/icon/{card.attribute}.svg"

                            # 查找 Live2D Costume
                            costume_url = None
                            # 1. 尝试直接通过 costumeId
                            cid = cdata.get("costumeId")
                            if cid and str(cid) in costumes_data:
                                abn = costumes_data[str(cid)].get("assetBundleName")
                                costume_url = self.client.get_costume_icon_url(
                                    cid, abn, server=server_code
                                )

                            # 2. 如果没有，尝试通过 matching 查找 (live_event_{id})
                            if not costume_url:
                                target_abn_part = f"live_event_{latest.event_id}"
                                for c_id_str, c_data in costumes_data.items():
                                    if c_data.get("characterId") == card.character_id:
                                        abn = c_data.get("assetBundleName", "")
                                        if target_abn_part in abn:
                                            costume_url = (
                                                self.client.get_costume_icon_url(
                                                    int(c_id_str),
                                                    abn,
                                                    server=server_code,
                                                )
                                            )
                                            break

                            # 报酬卡使用4星外框展示（虽然实际是3星）
                            render_data["reward_cards"].append(
                                {
                                    "image": card_image_url,
                                    "character_name": char_name,
                                    "rarity": card.rarity,
                                    "costume_image": costume_url,
                                    "frame_url": "https://bestdori.com/res/image/frame-4.png",  # 使用4星外框
                                    "band_icon": reward_band_icon,
                                    "attr_icon": reward_attr_icon,
                                }
                            )
                            logger.info(
                                f"报酬卡 {card.card_id} ({card.rarity}星): 使用4星外框, band={reward_band_icon}, attr={reward_attr_icon}"
                            )
                            logger.info(
                                f"找到★3报酬卡: {char_name}, 图片URL: {card_image_url}"
                            )

                # 按稀有度排序（高到低）- temp_cards 是字典列表
                temp_cards.sort(key=lambda x: x["rarity"], reverse=True)
                render_data["new_cards"] = temp_cards

                # 报酬卡按星级排序
                render_data["reward_cards"].sort(
                    key=lambda x: x["rarity"], reverse=True
                )

                # 获取第一张新卡面成员所属乐队图标
                if temp_cards:
                    first_char_id = temp_cards[0].get("character_id")
                    if first_char_id:
                        band_id = CHARACTER_BAND_MAP.get(first_char_id)
                        if band_id:
                            band_svg = BAND_ICON_URL_MAP.get(band_id)
                            if band_svg:
                                render_data["band_icon"] = (
                                    f"https://bestdori.com/res/icon/{band_svg}"
                                )

                # 随机选取一张5星卡面的特训前大图作为封面
                if five_star_cards:
                    render_data["cover_image"] = random.choice(five_star_cards)
                elif temp_cards:
                    # 如果没有5星，用最高稀有度的卡面
                    for c in temp_cards:
                        if c.get("normal_rip_url"):
                            render_data["cover_image"] = c["normal_rip_url"]
                            break

                # 获取招募卡池信息（使用活动时间范围筛选）
                event_end = (
                    latest.get_end_time(server=server)
                    if hasattr(latest, "get_end_time")
                    else None
                )
                for gid, gdata in gachas_data.items():
                    gacha = Gacha(int(gid), gdata)
                    gacha_start = gacha.get_start_time(server=server)
                    gacha_end = (
                        gacha.get_end_time(server=server)
                        if hasattr(gacha, "get_end_time")
                        else None
                    )

                    # 使用活动时间范围筛选（招募开始时间在活动时间范围内）
                    if gacha_start and event_start and event_end:
                        if event_start <= gacha_start <= event_end:
                            # 格式化卡池时间
                            gacha_start_str = gacha.get_formatted_time(
                                True, server=server
                            )
                            gacha_end_str = gacha.get_formatted_time(
                                False, server=server
                            )

                            # 简化日期格式
                            try:
                                # 尝试匹配 "X月X日" 格式
                                start_match = re.search(
                                    r"(\d+)月(\d+)日", gacha_start_str
                                )
                                end_match = re.search(r"(\d+)月(\d+)日", gacha_end_str)
                                if start_match:
                                    gacha_start_str = (
                                        f"{start_match.group(1)}/{start_match.group(2)}"
                                    )
                                if end_match:
                                    gacha_end_str = (
                                        f"{end_match.group(1)}/{end_match.group(2)}"
                                    )

                                # 如果是 "YYYY-MM-DD HH:MM" 格式
                                if not start_match:
                                    start_match = re.search(
                                        r"\d{4}-(\d{2})-(\d{2})", gacha_start_str
                                    )
                                    if start_match:
                                        gacha_start_str = f"{int(start_match.group(1))}/{int(start_match.group(2))}"
                                if not end_match:
                                    end_match = re.search(
                                        r"\d{4}-(\d{2})-(\d{2})", gacha_end_str
                                    )
                                    if end_match:
                                        gacha_end_str = f"{int(end_match.group(1))}/{int(end_match.group(2))}"
                            except:
                                pass

                            # 获取招募封面，验证有效性，无效则使用备用封面
                            gacha_banner = gacha.banner_url
                            cover_img_url = render_data.get("cover_image") or ""

                            # 验证招募封面是否有效
                            banner_valid = (
                                await self._verify_image_url(gacha_banner)
                                if gacha_banner
                                else False
                            )

                            if not banner_valid:
                                # 封面无效，使用裁剪后的新卡面作为备用
                                if cover_img_url:
                                    try:
                                        cropped_path = await self._crop_image_to_banner(
                                            cover_img_url,
                                            latest.event_id,
                                            gacha.gacha_id,
                                        )
                                        if cropped_path:
                                            gacha_banner = cropped_path
                                            logger.info(
                                                f"招募 {gacha.name} 封面无效，已裁剪新卡面作为备用"
                                            )
                                        else:
                                            gacha_banner = cover_img_url
                                            logger.info(
                                                f"招募 {gacha.name} 封面无效，使用原始新卡面作为备用"
                                            )
                                    except Exception as e:
                                        logger.warning(f"裁剪备用封面失败: {e}")
                                        gacha_banner = cover_img_url
                                else:
                                    gacha_banner = ""
                                    logger.warning(
                                        f"招募 {gacha.name} 封面无效且无备用封面可用"
                                    )

                            render_data["gacha_list"].append(
                                {
                                    "name": gacha.name,
                                    "start_date": gacha_start_str,
                                    "end_date": gacha_end_str,
                                    "banner_image": gacha_banner,
                                    "description": None,
                                }
                            )

            # --- 执行渲染 ---
            output_dir = os.path.join(self.client.cache_dir, "images")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir, f"event_overview_{latest.event_id}.png"
            )

            self.renderer.render_event_overview_card(render_data, output_path)

            if os.path.exists(output_path):
                # 保存到缓存（包含服务器信息）
                await self.cache_manager.set_cache(
                    "event", output_path, event_id=latest.event_id, server=server
                )
                yield event.image_result(output_path)
            else:
                yield event.plain_result("❌ 图片生成失败，渲染未产生输出文件。")

        except RuntimeError as e:
            # 渲染相关的运行时错误（如 Chrome 不可用）
            logger.error(f"渲染失败: {e}")
            yield event.plain_result(f"❌ 渲染失败: {e}")
        except Exception as e:
            logger.error(f"渲染失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            yield event.plain_result(f"❌ 渲染失败: {e}")

    async def _verify_image_url(self, url: str) -> bool:
        """
        验证图片URL是否有效（存在且非空）

        Args:
            url: 图片URL

        Returns:
            True 如果图片有效，False 否则
        """
        if not url:
            return False

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        return False

                    # 检查 Content-Length，如果太小可能是空图片
                    content_length = resp.headers.get("Content-Length")
                    if (
                        content_length and int(content_length) < 1000
                    ):  # 小于1KB认为是无效图片
                        return False

                    # 检查 Content-Type
                    content_type = resp.headers.get("Content-Type", "")
                    if not content_type.startswith("image/"):
                        return False

                    return True
        except Exception as e:
            logger.debug(f"验证图片URL失败 {url}: {e}")
            return False

    async def _crop_image_to_banner(
        self, image_url: str, event_id: int, gacha_id: int
    ) -> str:
        """
        将卡面图片裁剪为招募横幅比例 (约 2.3:1)
        裁剪方式：从图像中线向上下裁剪

        Args:
            image_url: 原始图片URL
            event_id: 活动ID（用于缓存命名）
            gacha_id: 招募ID（用于缓存命名）

        Returns:
            裁剪后图片的本地路径，失败返回空字符串
        """
        try:
            from PIL import Image
            import aiohttp
            from io import BytesIO

            # 目标宽高比 (招募横幅约 1380x600)
            TARGET_RATIO = 2.3

            # 缓存路径
            cache_dir = os.path.join(self.client.cache_dir, "images", "gacha_banners")
            os.makedirs(cache_dir, exist_ok=True)
            output_path = os.path.join(cache_dir, f"banner_{event_id}_{gacha_id}.png")

            # 如果已有缓存，直接返回
            if os.path.exists(output_path):
                return output_path

            # 下载图片
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return ""
                    image_data = await resp.read()

            # 打开图片
            img = Image.open(BytesIO(image_data))
            width, height = img.size

            # 计算裁剪区域（从中心向上下裁剪）
            current_ratio = width / height

            if current_ratio < TARGET_RATIO:
                # 图片太高，需要裁剪高度
                new_height = int(width / TARGET_RATIO)
                top = (height - new_height) // 2
                bottom = top + new_height
                crop_box = (0, top, width, bottom)
            else:
                # 图片太宽或已经是正确比例，裁剪宽度
                new_width = int(height * TARGET_RATIO)
                left = (width - new_width) // 2
                right = left + new_width
                crop_box = (left, 0, right, height)

            # 执行裁剪
            cropped_img = img.crop(crop_box)

            # 保存裁剪后的图片
            cropped_img.save(output_path, "PNG")

            logger.info(
                f"裁剪成功: {width}x{height} -> {cropped_img.size[0]}x{cropped_img.size[1]}"
            )

            return output_path

        except Exception as e:
            logger.warning(f"裁剪图片失败: {e}")
            return ""

    async def _handle_card_search(
        self, event: AstrMessageEvent, char_id: int, original_name: str
    ):
        """
        处理卡面查询逻辑 (支持多级菜单)
        """
        official_name = CHARACTER_MAP[char_id][0]

        # 1. 尝试解析参数 (例如: /bd ksm 4星)
        # 重新获取完整指令文本
        full_text = event.message_str.strip().lower()
        parts = full_text.split()

        # 过滤掉指令前缀 /bd 和 card
        args = [p for p in parts if p not in ["/bd", "bd", "card", "bestdori"]]

        # 移除掉角色名本身 (例如 ksm)
        # 简单粗暴点：args 的第一个肯定是角色名，后面的才是参数
        params = args[1:] if len(args) > 1 else []

        # 2. 获取所有卡片
        yield event.plain_result(f"🔍 正在检索 {official_name} 的数据...")
        try:
            cards_data = await self.client.get_cards()
            all_cards = []
            for cid, data in cards_data.items():
                card = Card(int(cid), data)
                if card.character_id == char_id:
                    all_cards.append(card)

            if not all_cards:
                yield event.plain_result(f"未找到 {official_name} 的卡面。")
                return

            # 按 ID 倒序 (最新的在前)
            all_cards.sort(key=lambda x: x.card_id, reverse=True)

            # 3. 如果没有参数 -> 显示菜单
            if not params:
                char_alias = args[0] if args else original_name.lower()

                # 设置上下文
                user_id = event.get_sender_id()
                group_id = (
                    event.message_obj.group_id
                    if hasattr(event.message_obj, "group_id")
                    else ""
                )
                menu_context.set_context(
                    user_id,
                    group_id,
                    menu="card_search",
                    char_id=char_id,
                    char_alias=char_alias,
                )

                menu = (
                    f"[ {official_name} - 卡面查询 ]\n"
                    f"------------------------\n"
                    f"共找到 {len(all_cards)} 张卡片\n"
                    f"------------------------\n"
                    f"  /1 - all    - 全部卡面\n"
                    f"  /2 - new    - 最新卡面\n"
                    f"  /3 - random - 随机抽取\n"
                    f"  /0 - back   - 返回上级\n"
                    f"------------------------\n"
                    f"示例: /bd {char_alias} random 4星 happy"
                )
                yield event.plain_result(menu)
                return

            # 4. 解析参数并筛选
            filter_star = 0
            filter_attr = ""
            mode = "list"  # list, all, new, random

            p1 = params[0]

            # 解析第一个参数
            if p1 in ["1", "all", "全部", "a"]:
                mode = "all"
            elif p1 in ["2", "new", "最新", "n"]:
                mode = "new"
            elif p1 in ["3", "random", "r", "随机"]:
                mode = "random"
            elif "星" in p1 or (p1.isdigit() and int(p1) <= 5):
                # 尝试解析星级 (4, 4星)
                try:
                    star_num = int(p1.replace("星", ""))
                    if 1 <= star_num <= 5:
                        filter_star = star_num
                except:
                    pass
            elif p1 in ["happy", "cool", "pure", "powerful", "power"]:
                filter_attr = p1 if p1 != "power" else "powerful"
            else:
                yield event.plain_result(f"未知参数: {p1} - 输入角色名查看帮助")
                return

            # 解析额外参数（用于 random 模式的条件限定）
            for extra_p in params[1:]:
                if "星" in extra_p or extra_p.isdigit():
                    try:
                        star_num = int(extra_p.replace("星", ""))
                        if 1 <= star_num <= 5:
                            filter_star = star_num
                    except:
                        pass
                elif extra_p in ["happy", "cool", "pure", "powerful", "power"]:
                    filter_attr = extra_p if extra_p != "power" else "powerful"

            # --- 执行筛选 ---
            filtered = all_cards
            if filter_star > 0:
                filtered = [c for c in filtered if c.rarity == filter_star]
            if filter_attr:
                filtered = [c for c in filtered if c.attribute == filter_attr]

            if not filtered:
                yield event.plain_result(
                    f"没有符合条件的卡片 (星级:{filter_star or '不限'}, 属性:{filter_attr or '不限'})"
                )
                return

            # --- 执行展示 ---
            if mode == "all":
                # 渲染全部卡面列表
                yield event.plain_result(f"正在生成 {official_name} 的卡面列表...")
                async for result in self._render_card_list(event, char_id, all_cards):
                    yield result
            elif mode == "new":
                # 显示最新的一张
                async for result in self._send_card_detail(event, filtered[0]):
                    yield result
            elif mode == "random":
                import random

                target = random.choice(filtered)
                async for result in self._send_card_detail(event, target):
                    yield result
            else:
                # 列表模式（默认行为，通常不会进入）
                if len(filtered) == 1:
                    async for result in self._send_card_detail(event, filtered[0]):
                        yield result
                else:
                    # 渲染全部卡面列表
                    yield event.plain_result(
                        f"正在生成卡面列表 ({len(filtered)} 张)..."
                    )
                    async for result in self._render_card_list(
                        event, char_id, filtered
                    ):
                        yield result

        except Exception as e:
            logger.error(f"搜卡失败: {e}")
            yield event.plain_result(f"搜卡失败: {e}")

    async def _render_card_list(
        self, event: AstrMessageEvent, char_id: int, cards: list
    ):
        """
        渲染卡面列表为图片
        按属性分组，每组按星级从高到低排序
        使用 base64 预加载所有图片以确保 headless Chrome 能正确渲染
        """
        # 确保基础素材存在
        await self.resource_manager.ensure_basic_assets()

        official_name = CHARACTER_MAP[char_id][0]
        band_id = CHARACTER_BAND_MAP.get(char_id, 1)

        # 生成缓存键（基于角色ID和卡片ID列表）
        card_ids = sorted([c.card_id for c in cards])
        cache_key_params = {"char_id": char_id, "card_ids": card_ids}

        # 检查缓存
        cached_image = await self.cache_manager.get_cache("card", **cache_key_params)
        if cached_image:
            logger.info(f"命中卡面列表缓存: char_{char_id}")
            yield event.image_result(cached_image)
            return

        # 角色图标 URL
        char_icon_url = f"https://bestdori.com/res/icon/chara_icon_{char_id}.png"

        # 按属性分组
        attr_groups = {"happy": [], "cool": [], "pure": [], "powerful": []}

        for card in cards:
            attr = card.attribute.lower()
            if attr in attr_groups:
                attr_groups[attr].append(card)

        # 每组按星级从高到低排序
        for attr in attr_groups:
            attr_groups[attr].sort(key=lambda c: (-c.rarity, -c.card_id))

        # 收集所有需要预加载的图片URL
        all_image_urls = set()
        for card in cards:
            all_image_urls.add(card.get_thumb_url(trained=True))
            all_image_urls.add(card.get_thumb_frame_url())  # 缩略图用 card-X 边框
            all_image_urls.add(card.get_star_icon_url())
            card_band_id = CHARACTER_BAND_MAP.get(card.character_id, 1)
            band_icon = BAND_ICON_URL_MAP.get(card_band_id, "band_1.svg")
            all_image_urls.add(f"https://bestdori.com/res/icon/{band_icon}")

        # 添加属性图标和角色图标
        all_image_urls.add(char_icon_url)
        for attr in ["happy", "cool", "pure", "powerful"]:
            all_image_urls.add(f"https://bestdori.com/res/icon/{attr}.svg")

        # 预加载所有图片为 base64
        image_cache = await self._preload_images_as_base64(list(all_image_urls))

        # 构建同星级缩略图替换映射：当某张卡的缩略图下载失败时，使用同星级其他卡的缩略图替换
        # 按星级收集成功加载的缩略图 data URI
        rarity_to_valid_thumbs = {1: [], 2: [], 3: [], 4: [], 5: []}
        for card in cards:
            thumb_url = card.get_thumb_url(trained=True)
            cached = image_cache.get(thumb_url)
            # 只收集成功下载的缩略图（以 data: 开头）
            if cached and cached.startswith("data:"):
                rarity_to_valid_thumbs[card.rarity].append(cached)

        # 构建模板数据（使用 base64 缓存）
        def build_card_data(card):
            """构建单张卡片的模板数据"""
            card_band_id = CHARACTER_BAND_MAP.get(card.character_id, 1)
            band_icon = BAND_ICON_URL_MAP.get(card_band_id, "band_1.svg")

            thumb_url = card.get_thumb_url(trained=True)
            frame_url = card.get_thumb_frame_url()  # 缩略图用 card-X 边框
            star_icon_url = card.get_star_icon_url()
            band_icon_url = f"https://bestdori.com/res/icon/{band_icon}"

            # 获取缩略图，如果下载失败则使用同星级替换
            cached_thumb = image_cache.get(thumb_url)
            if cached_thumb is None or not cached_thumb.startswith("data:"):
                # 下载失败，查找同星级替换
                valid_thumbs = rarity_to_valid_thumbs.get(card.rarity, [])
                if valid_thumbs:
                    # 使用第一个可用的同星级缩略图
                    cached_thumb = valid_thumbs[0]
                    logger.info(f"卡片 {card.card_id} 缩略图下载失败，使用同星级替换")
                else:
                    # 没有同星级可用，保持原URL（会显示为空白）
                    cached_thumb = thumb_url
                    logger.warning(
                        f"卡片 {card.card_id} 缩略图下载失败，且无同星级替换可用"
                    )

            return {
                "card_id": card.card_id,
                "thumb_url": cached_thumb,
                "frame_url": image_cache.get(frame_url) or frame_url,
                "band_icon_url": image_cache.get(band_icon_url) or band_icon_url,
                "stars": [
                    {"star_icon_url": image_cache.get(star_icon_url) or star_icon_url}
                    for _ in range(card.rarity)
                ],
            }

        # 属性图标URL（使用缓存）
        def get_attr_icon(attr):
            url = f"https://bestdori.com/res/icon/{attr}.svg"
            return image_cache.get(url) or url

        template_data = {
            "char_name": official_name,
            "char_icon_url": image_cache.get(char_icon_url) or char_icon_url,
            "total_count": len(cards),
            "happy_cards": [build_card_data(c) for c in attr_groups["happy"]],
            "cool_cards": [build_card_data(c) for c in attr_groups["cool"]],
            "pure_cards": [build_card_data(c) for c in attr_groups["pure"]],
            "powerful_cards": [build_card_data(c) for c in attr_groups["powerful"]],
            "happy_icon_url": get_attr_icon("happy"),
            "cool_icon_url": get_attr_icon("cool"),
            "pure_icon_url": get_attr_icon("pure"),
            "powerful_icon_url": get_attr_icon("powerful"),
            "example_id": cards[0].card_id if cards else 1,
        }

        # 计算最大卡面数量，动态确定宽度
        max_cards_in_row = max(
            len(attr_groups["happy"]),
            len(attr_groups["cool"]),
            len(attr_groups["pure"]),
            len(attr_groups["powerful"]),
        )
        # 每张卡片宽度约 95px (85px缩略图 + 10px间距)，加上左侧角色区域 130px，属性图标 50px，边距 60px
        # 增加显著的右侧余量 (+250) 以确保 html2image 渲染出完整的背景区域，避免右侧截断
        calculated_width = 130 + 50 + max_cards_in_row * 95 + 250
        render_width = max(calculated_width, 800)
        template_data["container_width"] = render_width

        # 渲染 HTML
        html_content = self.renderer.render_template("card_list.html", **template_data)

        # 转换为图片（横向布局，使用动态计算的宽度）
        image_path = await self.renderer.html_to_image(
            html_content, prefix="card_list", width=render_width
        )

        if image_path and os.path.exists(image_path):
            # 保存到缓存
            await self.cache_manager.set_cache("card", image_path, **cache_key_params)
            yield event.image_result(image_path)
        else:
            yield event.plain_result("渲染卡面列表失败")

    async def _preload_images_as_base64(self, urls: list) -> dict:
        """
        批量预加载图片并转为 base64 data URI
        支持多服务器回退机制 (CN -> JP -> EN -> TW -> KR)
        用于解决 headless Chrome 不等待远程图片加载的问题

        返回: dict，键为 URL，值为 data URI 或 None (表示下载失败)
        """
        image_cache = {}

        async def fetch_image_as_base64(
            session: aiohttp.ClientSession, original_url: str
        ) -> tuple:
            """下载单张图片并转为 base64 data URI，失败时尝试其他服务器"""

            # 如果已经是 data URI，直接返回
            if original_url.startswith("data:"):
                return (original_url, original_url)

            # 确定尝试的 URL 列表
            try_urls = [original_url]

            # 如果是 Bestdori 资源且包含 /assets/cn/，则添加回退 URL
            if "bestdori.com/assets/cn/" in original_url:
                for server in ["jp", "en", "tw", "kr"]:
                    try_urls.append(
                        original_url.replace("/assets/cn/", f"/assets/{server}/")
                    )

            for url in try_urls:
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            content = await resp.read()

                            # 验证内容是否为有效图片 (Bestdori 可能会返回 200 OK 的 HTML)
                            if (
                                len(content) < 100
                                or content.startswith(b"<!DOCTYPE")
                                or content.startswith(b"<html")
                            ):
                                continue

                            content_type = resp.headers.get("Content-Type", "image/png")
                            if "svg" in content_type or url.endswith(".svg"):
                                content_type = "image/svg+xml"
                            elif url.endswith(".png"):
                                content_type = "image/png"

                            b64 = base64.b64encode(content).decode("utf-8")
                            data_uri = f"data:{content_type};base64,{b64}"
                            return (original_url, data_uri)
                except Exception:
                    pass

            # 所有尝试都失败，返回 None 表示失败
            logger.warning(
                f"预加载图片失败（尝试了 {len(try_urls)} 个服务器）: {original_url}"
            )
            return (original_url, None)

        connector = aiohttp.TCPConnector(limit=30)
        async with aiohttp.ClientSession(connector=connector) as session:
            semaphore = asyncio.Semaphore(20)

            async def fetch_with_semaphore(url):
                async with semaphore:
                    return await fetch_image_as_base64(session, url)

            tasks = [fetch_with_semaphore(url) for url in urls]
            results = await asyncio.gather(*tasks)

            for url, data in results:
                image_cache[url] = data

        return image_cache

    async def _send_card_detail(self, event: AstrMessageEvent, card: Card):
        """发送单张卡片的详细信息和图片"""
        official_name = CHARACTER_MAP[card.character_id][0]
        msg = (
            f"角色: {official_name}\n"
            f"ID: {card.card_id}\n"
            f"标题: {card.title}\n"
            f"{card.rarity}★ | {card.attribute.capitalize()}"
        )
        yield event.plain_result(msg)

        # 1. 特训前
        url_normal = card.get_card_icon_url("rip_normal")
        if url_normal:
            path = await self.client.download_image(url_normal)
            if path:
                yield event.image_result(path)

        # 2. 特训后
        if card.rarity >= 3:
            url_trained = card.get_card_icon_url("rip_trained")
            if url_trained:
                path = await self.client.download_image(url_trained)
                if path:
                    yield event.image_result(path)

    async def _send_card_illustration(self, event: AstrMessageEvent, card_id: int):
        """发送卡面的插画信息（特训前后两张rip大图）"""
        try:
            cards_data = await self.client.get_cards()
            if str(card_id) not in cards_data:
                yield event.plain_result(f"未找到ID为 {card_id} 的卡面")
                return

            card = Card(card_id, cards_data[str(card_id)])
            official_name = CHARACTER_MAP.get(card.character_id, ["未知"])[0]

            yield event.plain_result(
                f"🎨 正在获取 [{official_name}] ID:{card_id} 的插画..."
            )

            # 获取特训前大图
            url_normal = card.get_card_icon_url("rip_normal")
            if url_normal:
                yield event.plain_result("📷 特训前插画:")
                path = await self.client.download_image(url_normal)
                if path:
                    yield event.image_result(path)
                else:
                    yield event.plain_result("(图片获取失败)")

            # 获取特训后大图（仅3星及以上）
            if card.rarity >= 3:
                url_trained = card.get_card_icon_url("rip_trained")
                if url_trained:
                    yield event.plain_result("📷 特训后插画:")
                    path = await self.client.download_image(url_trained)
                    if path:
                        yield event.image_result(path)
                    else:
                        yield event.plain_result("(图片获取失败)")
            else:
                yield event.plain_result(f"ℹ️ {card.rarity}星卡面无特训后插画")

            # 清除上下文
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.clear_context(user_id, group_id)

        except Exception as e:
            logger.error(f"获取卡面插画失败: {e}")
            yield event.plain_result(f"获取失败: {e}")

    async def _send_card_detail_page(self, event: AstrMessageEvent, card_id: int):
        """发送卡面的详细信息卡片（HTML渲染）"""
        try:
            cards_data = await self.client.get_cards()
            if str(card_id) not in cards_data:
                yield event.plain_result(f"未找到ID为 {card_id} 的卡面")
                return

            card = Card(card_id, cards_data[str(card_id)])
            official_name = CHARACTER_MAP.get(card.character_id, ["未知"])[0]

            # TODO: 实现详细信息卡片的HTML渲染
            # 目前先使用文字版本
            msg = (
                f"[ 卡面详细信息 ]\n"
                f"------------------------\n"
                f"ID: {card.card_id}\n"
                f"角色: {official_name}\n"
                f"标题: {card.title}\n"
                f"稀有度: {card.rarity}★\n"
                f"属性: {card.attribute.capitalize()}\n"
                f"资源名: {card.resource_set_name}\n"
                f"发布时间: {card.released_at.get('0', '未知')}\n"
                f"------------------------\n"
                f"📌 详细信息卡片功能开发中..."
            )
            yield event.plain_result(msg)

            # 清除上下文
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.clear_context(user_id, group_id)

        except Exception as e:
            logger.error(f"获取卡面详情失败: {e}")
            yield event.plain_result(f"获取失败: {e}")

    async def _handle_birthday_query(
        self, event: AstrMessageEvent, char_name: str = ""
    ):
        """
        处理生日查询

        Args:
            event: 消息事件
            char_name: 角色名称（可选）
        """
        try:
            # 如果没有指定角色名，返回今日生日列表
            if not char_name:
                today_birthdays = self.birthday_service.get_today_birthdays()

                if not today_birthdays:
                    yield event.plain_result("🎂 今天没有角色过生日哦~")
                    return

                # 获取今日过生日角色的信息
                birthday_msgs = []
                for char_id in today_birthdays:
                    char_name = self.birthday_service.get_character_name(char_id)
                    band_name = self.birthday_service.get_character_band_name(char_id)
                    birthday = self.birthday_service.get_character_birthday(char_id)
                    birthday_msgs.append(
                        f"🎉 {char_name} ({band_name}) - {birthday[0]}月{birthday[1]}日"
                    )

                result_text = "🎂 **今日生日** 🎂\n" + "\n".join(birthday_msgs)
                yield event.plain_result(result_text)

                # 如果有生日角色，生成第一个角色的生日卡片
                if today_birthdays:
                    yield event.plain_result("正在生成生日卡片...")
                    birthday_data = await self.birthday_service.get_birthday_message(
                        today_birthdays[0]
                    )

                    if birthday_data and birthday_data.get("selected_card"):
                        async for result in self._render_birthday_card(
                            event, birthday_data
                        ):
                            yield result
                    else:
                        yield event.plain_result(
                            f"⚠️ {birthday_data.get('character_name', '该角色')} 暂无生日卡片数据"
                        )

                return

            # 指定了角色名，查询该角色的生日
            char_id = get_character_id_by_name(char_name)

            if char_id == 0:
                yield event.plain_result(f"❌ 未找到角色: {char_name}")
                return

            birthday = self.birthday_service.get_character_birthday(char_id)

            if not birthday:
                yield event.plain_result("⚠️ 未找到该角色的生日数据")
                return

            # 获取生日信息
            yield event.plain_result(
                f"正在查询 {self.birthday_service.get_character_name(char_id)} 的生日信息..."
            )
            birthday_data = await self.birthday_service.get_birthday_message(char_id)

            # 生成生日信息文本
            info_text = (
                f"🎂 **{birthday_data['character_name']}** 生日信息 🎂\n"
                f"乐队：{birthday_data['band_name']}\n"
                f"生日：{birthday_data['birthday']}"
            )

            yield event.plain_result(info_text)

            # 渲染生日卡片和发送语音
            if birthday_data.get("selected_card"):
                async for result in self._render_birthday_card(event, birthday_data):
                    yield result

        except Exception as e:
            logger.error(f"生日查询失败: {e}")
            yield event.plain_result(f"⚠️ 生日查询失败：{e}")

    async def _render_birthday_card(self, event: AstrMessageEvent, birthday_data: dict):
        """
        渲染生日卡片图片并发送语音

        Args:
            event: 消息事件
            birthday_data: 生日数据字典
        """
        try:
            # 确保基础素材存在
            await self.resource_manager.ensure_basic_assets()

            char_id = birthday_data.get("character_id")

            # 检查缓存
            cached_image = await self.cache_manager.get_cache(
                "birthday", char_id=char_id
            )
            if cached_image:
                logger.info(f"命中生日卡片缓存: birthday_char_{char_id}")
                yield event.image_result(cached_image)

                # 继续发送语音等其他内容
                selected_card = birthday_data.get("selected_card")
                if selected_card:
                    card_id = selected_card.get("card_id")
                    if card_id:
                        try:
                            card_data = await self.client.get_card_detail(card_id)
                            if card_data:
                                costume_id = card_data.get("costumeId")
                                costume_url = None

                                if costume_id:
                                    costumes_data = await self.client.get_costumes()
                                    if str(costume_id) in costumes_data:
                                        abn = costumes_data[str(costume_id)].get(
                                            "assetBundleName"
                                        )
                                        costume_url = self.client.get_costume_icon_url(
                                            costume_id, abn
                                        )

                                if costume_url:
                                    yield event.image_result(costume_url)
                        except Exception as e:
                            logger.warning(f"获取生日Live2D小人失败: {e}")

                    voice_path = selected_card.get("local_voice_path")
                    if voice_path and os.path.exists(voice_path):
                        try:
                            yield event.voice_result(voice_path)
                        except Exception as e:
                            logger.warning(f"发送语音失败: {e}")
                return

            selected_card = birthday_data.get("selected_card")
            if not selected_card:
                yield event.plain_result("⚠️ 没有可用的生日卡片")
                return

            char_id = birthday_data.get("character_id")

            # 收集需要预加载的图片 URL
            urls_to_preload = []
            
            # 卡面图片 URL
            card_url = selected_card.get("card_image_url", "")
            local_card_path = selected_card.get("local_card_path")
            
            # 如果有本地卡面，转换为 base64
            if local_card_path and os.path.isabs(local_card_path) and os.path.exists(local_card_path):
                import base64
                try:
                    with open(local_card_path, "rb") as f:
                        card_data_b64 = base64.b64encode(f.read()).decode("utf-8")
                    card_url = f"data:image/png;base64,{card_data_b64}"
                    logger.info(f"✅ 已将本地卡面转换为 base64")
                except Exception as e:
                    logger.warning(f"转换本地卡面为 base64 失败: {e}，使用远程 URL")
                    if card_url:
                        urls_to_preload.append(card_url)
            elif card_url:
                urls_to_preload.append(card_url)
            
            # Chibi 图标 - 优先使用 ResourceManager 获取本地资源
            chibi_url = self.resource_manager.get_local_chibi(char_id)
            
            if chibi_url:
                logger.info(f"✅ 已使用本地 Chibi 图标: chibi_{char_id}.png")
            else:
                # 本地不存在，从远程下载并转为 base64
                remote_chibi_url = f"https://bestdori.com/res/icon/chara_icon_{char_id}.png"
                urls_to_preload.append(remote_chibi_url)
            
            logger.info(f"🔄 预加载图片: {urls_to_preload}")
            
            # 预加载所有远程图片
            image_cache = {}
            if urls_to_preload:
                image_cache = await self._preload_images_as_base64(urls_to_preload)
            
            # 获取预加载后的卡面图片
            if not card_url.startswith("data:"):
                cached_card = image_cache.get(card_url)
                if cached_card:
                    card_url = cached_card
                    logger.info(f"✅ 卡面图片预加载成功")
                else:
                    logger.warning(f"❌ 卡面图片预加载失败: {card_url}")
            
            # 如果 chibi 还没有设置（本地不存在），从预加载结果获取
            if not chibi_url:
                remote_chibi_url = f"https://bestdori.com/res/icon/chara_icon_{char_id}.png"
                cached_chibi = image_cache.get(remote_chibi_url)
                if cached_chibi:
                    chibi_url = cached_chibi
                    logger.info(f"✅ Chibi 图标远程预加载成功")
                else:
                    logger.warning(f"❌ Chibi 图标预加载失败，使用透明占位符")
                    # 使用透明占位图（1x1透明PNG的base64）
                    chibi_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

            # 从角色数据库或卡面图像中获取主题色
            text_color = color_extractor.extract_character_color(str(char_id), card_url)

            render_data = {
                "character_name": birthday_data["character_name"],
                "band_name": birthday_data["band_name"],
                "birthday": birthday_data["birthday"],
                "card_prefix": selected_card.get("prefix", "生日纪念"),
                "card_image_url": card_url,
                "birthday_text": selected_card.get("birthday_text", ""),
                "chibi_url": chibi_url,
                "text_color": text_color,
            }

            # 渲染HTML模板
            html = self.renderer.render_template("birthday_card.html", **render_data)

            # 转换为图片
            image_path = await self.renderer.html_to_image(html, "birthday")

            if image_path and os.path.exists(image_path):
                # 保存到缓存
                await self.cache_manager.set_cache(
                    "birthday", image_path, char_id=char_id
                )
                yield event.image_result(image_path)
            else:
                yield event.plain_result("⚠️ 生日卡片生成失败")

            # 发送 Live2D 小人 (三段式消息优化)
            card_id = selected_card.get("card_id")
            if card_id:
                try:
                    # 获取卡片详情以查找 Costume
                    card_data = await self.client.get_card_detail(card_id)
                    if card_data:
                        costume_id = card_data.get("costumeId")
                        costume_url = None

                        if costume_id:
                            costumes_data = await self.client.get_costumes()
                            if str(costume_id) in costumes_data:
                                abn = costumes_data[str(costume_id)].get(
                                    "assetBundleName"
                                )
                                costume_url = self.client.get_costume_icon_url(
                                    costume_id, abn
                                )

                        if costume_url:
                            yield event.image_result(costume_url)
                except Exception as e:
                    logger.warning(f"获取生日Live2D小人失败: {e}")

            # 发送语音文件
            voice_path = selected_card.get("local_voice_path")
            if voice_path and os.path.exists(voice_path):
                try:
                    logger.info(f"准备发送语音文件: {voice_path}")

                    # 将MP3转换为WAV格式（AstrBot只支持WAV）
                    wav_path = voice_path.replace(".mp3", ".wav")

                    # 检查是否已经转换过
                    if not os.path.exists(wav_path):
                        conversion_success = False

                        # 尝试1: 使用pydub
                        try:
                            from pydub import AudioSegment

                            logger.info("使用pydub转换MP3到WAV...")
                            audio = AudioSegment.from_mp3(voice_path)
                            audio.export(wav_path, format="wav")
                            conversion_success = True
                            logger.info(f"pydub转换成功: {wav_path}")
                        except ImportError:
                            logger.warning("未安装pydub库")
                        except Exception as e:
                            logger.error(f"pydub转换失败: {e}")

                        # 尝试2: 使用ffmpeg
                        if not conversion_success:
                            try:
                                import subprocess

                                logger.info("尝试使用ffmpeg转换...")
                                result = subprocess.run(
                                    [
                                        "ffmpeg",
                                        "-i",
                                        voice_path,
                                        "-ar",
                                        "44100",
                                        "-ac",
                                        "2",
                                        "-y",
                                        wav_path,
                                    ],
                                    check=True,
                                    capture_output=True,
                                    text=True,
                                )
                                conversion_success = True
                                logger.info(f"ffmpeg转换成功: {wav_path}")
                            except FileNotFoundError:
                                logger.error("系统未安装ffmpeg")
                            except Exception as e:
                                logger.error(f"ffmpeg转换失败: {e}")

                        # 如果都失败了，提示用户
                        if not conversion_success:
                            size_kb = os.path.getsize(voice_path) / 1024
                            yield event.plain_result(
                                f"🔊 生日语音已下载，但需要转换格式\n"
                                f"📁 MP3文件: {voice_path}\n"
                                f"📊 文件大小: {size_kb:.2f} KB\n\n"
                                f"💡 安装方法（任选其一）：\n"
                                f"• pip install pydub\n"
                                f"• 安装ffmpeg到系统PATH"
                            )
                            return
                    else:
                        logger.info(f"WAV文件已存在: {wav_path}")

                    # 确认WAV文件存在后再发送
                    if os.path.exists(wav_path):
                        voice_chain = [Comp.Record(file=wav_path, url=wav_path)]
                        yield event.chain_result(voice_chain)
                        logger.info("语音消息发送成功")
                    else:
                        logger.error(f"WAV文件不存在: {wav_path}")
                        yield event.plain_result(
                            "⚠️ 语音文件转换失败，请检查pydub或ffmpeg安装"
                        )

                except Exception as e:
                    logger.warning(f"语音发送失败: {e}")
                    import traceback

                    logger.error(traceback.format_exc())
                    # 提供详细的错误信息和解决方案
                    size_kb = os.path.getsize(voice_path) / 1024
                    yield event.plain_result(
                        f"⚠️ 语音发送失败：{e}\n"
                        f"📁 MP3文件: {voice_path}\n"
                        f"📊 文件大小: {size_kb:.2f} KB\n\n"
                        f"🔧 可能的解决方案：\n"
                        f"1. 安装pydub: pip install pydub\n"
                        f"2. 安装ffmpeg并添加到PATH"
                    )
            else:
                logger.info("该卡片暂无语音文件")

        except Exception as e:
            logger.error(f"生日卡片渲染失败: {e}")
            yield event.plain_result(f"⚠️ 生日卡片渲染失败：{e}")

    async def _admin_show_cache_stats(self, event: AstrMessageEvent):
        """显示缓存统计信息"""
        try:
            stats = self.cache_manager.get_cache_stats()
            cache_list = self.cache_manager.get_cache_list(limit=100)

            # 计算过期缓存数量
            expired_count = sum(1 for c in cache_list if c["is_expired"])

            # 计算各类别的详细统计
            events_stats = stats["categories"].get("events", {"count": 0, "size": 0})
            cards_stats = stats["categories"].get("cards", {"count": 0, "size": 0})
            birthdays_stats = stats["categories"].get(
                "birthdays", {"count": 0, "size": 0}
            )

            msg = (
                "[ 📊 缓存统计信息 ]\n"
                "========================\n"
                f"缓存状态: {'✅ 已启用' if stats['cache_enabled'] else '❌ 已禁用'}\n"
                "\n"
                "💾 存储空间:\n"
                f"  当前占用: {stats['total_size_mb']:.2f} MB\n"
                f"  最大限制: {stats['max_size_mb']:.2f} MB\n"
                f"  使用率: {stats['usage_percent']:.1f}%\n"
                f"  {'⚠️ 接近上限！' if stats['usage_percent'] > 80 else ''}\n"
                "\n"
                "📁 缓存分类:\n"
                f"  📅 活动: {events_stats['count']} 个 ({events_stats['size'] / 1024 / 1024:.2f} MB)\n"
                f"  🎴 卡面: {cards_stats['count']} 个 ({cards_stats['size'] / 1024 / 1024:.2f} MB)\n"
                f"  🎂 生日: {birthdays_stats['count']} 个 ({birthdays_stats['size'] / 1024 / 1024:.2f} MB)\n"
                "\n"
                "⏰ 缓存健康:\n"
                f"  有效缓存: {len(cache_list) - expired_count} 个\n"
                f"  过期缓存: {expired_count} 个 {'⚠️ 建议清理' if expired_count > 0 else '✅'}\n"
                f"  最后清理: {datetime.fromtimestamp(stats['last_cleanup']).strftime('%Y-%m-%d %H:%M')}\n"
                "========================\n"
                "💡 提示: 活动缓存24h过期, 卡面7天, 生日30天\n"
            )

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            yield event.plain_result(f"❌ 获取缓存统计失败: {e}")

    async def _admin_show_cache_list(self, event: AstrMessageEvent):
        """显示缓存文件列表（带详细信息）"""
        try:
            # 获取详细的缓存列表
            cache_list = self.cache_manager.get_cache_list(limit=30)
            stats = self.cache_manager.get_cache_stats()

            msg = "[ 缓存文件列表 ]\n"
            msg += "------------------------\n"

            if not cache_list:
                msg += "暂无缓存文件\n"
            else:
                # 按类别分组显示
                events_cache = [c for c in cache_list if c["category"] == "events"]
                cards_cache = [c for c in cache_list if c["category"] == "cards"]
                birthdays_cache = [
                    c for c in cache_list if c["category"] == "birthdays"
                ]

                # 显示活动缓存
                if events_cache:
                    msg += f"\n📅 活动缓存 ({len(events_cache)} 个):\n"
                    for item in events_cache[:10]:
                        params = item.get("params", {})
                        event_id = params.get("event_id", "未知")
                        size_kb = item["size"] / 1024
                        accessed = datetime.fromtimestamp(item["accessed_at"]).strftime(
                            "%m-%d %H:%M"
                        )
                        expired_mark = " ⚠️过期" if item["is_expired"] else ""
                        msg += f"  • 活动#{event_id} ({size_kb:.1f}KB) 访问:{accessed}{expired_mark}\n"
                    if len(events_cache) > 10:
                        msg += f"  ... 还有 {len(events_cache) - 10} 个\n"

                # 显示卡面缓存
                if cards_cache:
                    msg += f"\n🎴 卡面缓存 ({len(cards_cache)} 个):\n"
                    for item in cards_cache[:10]:
                        params = item.get("params", {})
                        char_id = params.get("char_id", 0)
                        char_name = (
                            self.birthday_service.get_character_name(char_id)
                            if char_id
                            else "未知角色"
                        )
                        size_kb = item["size"] / 1024
                        accessed = datetime.fromtimestamp(item["accessed_at"]).strftime(
                            "%m-%d %H:%M"
                        )
                        expired_mark = " ⚠️过期" if item["is_expired"] else ""
                        msg += f"  • {char_name} ({size_kb:.1f}KB) 访问:{accessed}{expired_mark}\n"
                    if len(cards_cache) > 10:
                        msg += f"  ... 还有 {len(cards_cache) - 10} 个\n"

                # 显示生日缓存
                if birthdays_cache:
                    msg += f"\n🎂 生日缓存 ({len(birthdays_cache)} 个):\n"
                    for item in birthdays_cache[:10]:
                        params = item.get("params", {})
                        char_id = params.get("char_id", 0)
                        char_name = (
                            self.birthday_service.get_character_name(char_id)
                            if char_id
                            else "未知角色"
                        )
                        size_kb = item["size"] / 1024
                        accessed = datetime.fromtimestamp(item["accessed_at"]).strftime(
                            "%m-%d %H:%M"
                        )
                        expired_mark = " ⚠️过期" if item["is_expired"] else ""
                        msg += f"  • {char_name} ({size_kb:.1f}KB) 访问:{accessed}{expired_mark}\n"
                    if len(birthdays_cache) > 10:
                        msg += f"  ... 还有 {len(birthdays_cache) - 10} 个\n"

            msg += "------------------------\n"
            total_count = sum(cat["count"] for cat in stats["categories"].values())
            msg += f"总计: {total_count} 个文件, {stats['total_size_mb']:.2f} MB\n"
            msg += f"使用率: {stats['usage_percent']:.1f}% (上限 {stats['max_size_mb']:.0f} MB)\n"

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"获取缓存列表失败: {e}")
            yield event.plain_result(f"❌ 获取缓存列表失败: {e}")

    async def _admin_show_dirs(self, event: AstrMessageEvent):
        """显示当前目录配置"""
        try:
            # 获取配置的目录
            cache_dir = self._get_config("cache_dir", "")
            download_dir = self._get_config("download_dir", "")

            # 获取实际使用的目录
            actual_cache_dir = (
                self.cache_manager.cache_base_dir
                if hasattr(self, "cache_manager")
                else "未初始化"
            )
            default_cache_dir = os.path.join(
                self.plugin_dir, "data", "bestdori_tools", "cache"
            )
            default_download_dir = os.path.join(
                self.plugin_dir, "data", "bestdori_tools", "downloads"
            )

            msg = (
                "[ 目录配置 ]\n"
                "------------------------\n"
                "📂 缓存目录:\n"
                f"  配置值: {cache_dir if cache_dir else '(使用默认)'}\n"
                f"  默认值: {default_cache_dir}\n"
                f"  实际路径: {actual_cache_dir}\n"
                "\n"
                "📂 下载目录:\n"
                f"  配置值: {download_dir if download_dir else '(使用默认)'}\n"
                f"  默认值: {default_download_dir}\n"
                "------------------------\n"
                "💡 提示: 在配置文件中设置 cache_dir 和 download_dir 可自定义目录位置\n"
            )

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"获取目录配置失败: {e}")
            yield event.plain_result(f"❌ 获取目录配置失败: {e}")

    async def _admin_cache_clean(self, event: AstrMessageEvent):
        """清理过期缓存"""
        try:
            # 先获取清理前的统计
            stats_before = self.cache_manager.get_cache_stats()
            cache_list_before = self.cache_manager.get_cache_list(limit=1000)
            expired_before = sum(1 for c in cache_list_before if c["is_expired"])

            yield event.plain_result(
                f"🧹 开始清理缓存...\n发现 {expired_before} 个过期缓存"
            )

            # 清理过期缓存
            expired_result = await self.cache_manager.cleanup_expired()

            # 清理超大缓存
            size_result = await self.cache_manager.cleanup_by_size()

            total_deleted = expired_result.get("deleted_count", 0) + size_result.get(
                "deleted_count", 0
            )
            total_freed = expired_result.get("freed_size", 0) + size_result.get(
                "freed_size", 0
            )

            # 获取清理后的统计
            stats_after = self.cache_manager.get_cache_stats()

            msg = "✅ 缓存清理完成\n"
            msg += "========================\n"

            if total_deleted == 0:
                msg += "🎉 缓存状态良好，无需清理\n"
            else:
                msg += f"🗑️ 删除文件: {total_deleted} 个\n"
                msg += f"💾 释放空间: {total_freed / 1024 / 1024:.2f} MB\n"
                msg += "\n"

                if expired_result.get("deleted_count", 0) > 0:
                    msg += f"  • 过期缓存: {expired_result['deleted_count']} 个\n"

                if (
                    size_result.get("status") == "success"
                    and size_result.get("deleted_count", 0) > 0
                ):
                    msg += f"  • LRU清理: {size_result['deleted_count']} 个\n"

            msg += "========================\n"
            msg += f"清理前: {stats_before['total_size_mb']:.2f} MB\n"
            msg += f"清理后: {stats_after['total_size_mb']:.2f} MB\n"
            msg += f"使用率: {stats_after['usage_percent']:.1f}%\n"

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            yield event.plain_result(f"❌ 清理缓存失败: {e}")

    async def _admin_cache_clear(self, event: AstrMessageEvent):
        """清空所有缓存 - 显示确认提示"""
        try:
            # 先获取统计信息
            stats = self.cache_manager.get_cache_stats()
            total_count = sum(cat["count"] for cat in stats["categories"].values())

            if total_count == 0:
                yield event.plain_result("📭 缓存已为空，无需清理")
                return

            # 设置上下文到确认菜单
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.set_context(user_id, group_id, menu="cache_clear_confirm")

            msg = (
                "⚠️ 确认清空所有缓存？\n"
                "========================\n"
                f"将删除 {total_count} 个缓存文件\n"
                f"释放约 {stats['total_size_mb']:.2f} MB 空间\n"
                "========================\n"
                "/1 确认清空\n"
                "/2 取消操作"
            )
            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            yield event.plain_result(f"❌ 清空缓存失败: {e}")

    async def _admin_cache_clear_confirmed(self, event: AstrMessageEvent):
        """确认后执行清空所有缓存"""
        try:
            # 获取清空前的统计
            stats_before = self.cache_manager.get_cache_stats()
            events_count = stats_before["categories"].get("events", {}).get("count", 0)
            cards_count = stats_before["categories"].get("cards", {}).get("count", 0)
            birthdays_count = (
                stats_before["categories"].get("birthdays", {}).get("count", 0)
            )

            yield event.plain_result("🗑️ 正在清空所有缓存...")

            result = await self.cache_manager.clear_all_cache()

            msg = (
                "✅ 缓存已完全清空\n"
                "========================\n"
                f"删除文件: {result['deleted_count']} 个\n"
                f"释放空间: {result['freed_size'] / 1024 / 1024:.2f} MB\n"
                "========================\n"
                "📝 清理详情:\n"
                f"  • 活动缓存: {events_count} 个 → 0\n"
                f"  • 卡面缓存: {cards_count} 个 → 0\n"
                f"  • 生日缓存: {birthdays_count} 个 → 0\n"
                "\n"
                "💡 下次查询时将重新生成缓存"
            )

            yield event.plain_result(msg)

            # 清除上下文
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.clear_context(user_id, group_id)

        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            yield event.plain_result(f"❌ 清空缓存失败: {e}")

    async def _admin_cache_clear_confirm(self, event: AstrMessageEvent):
        """旧版确认方法 - 保留兼容性，直接执行"""
        async for result in self._admin_cache_clear_confirmed(event):
            yield result

    async def _admin_api_status(self, event: AstrMessageEvent):
        """显示 API 数据缓存状态"""
        try:
            cache_dir = self.client.cache_dir

            api_files = {
                "events.json": "活动数据",
                "cards.json": "卡面数据",
                "gachas.json": "招募数据",
                "songs.json": "歌曲数据",
            }

            msg = "[ 📡 API 数据缓存状态 ]\n"
            msg += "========================\n"

            total_size = 0
            for filename, desc in api_files.items():
                file_path = os.path.join(cache_dir, filename)
                if os.path.exists(file_path):
                    stat = os.stat(file_path)
                    size_kb = stat.st_size / 1024
                    total_size += stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    age_hours = (datetime.now() - mtime).total_seconds() / 3600

                    # 6小时内为有效缓存
                    status = "✅" if age_hours < 6 else "⚠️过期"
                    msg += f"{status} {desc}:\n"
                    msg += f"   大小: {size_kb:.1f} KB\n"
                    msg += f"   更新: {mtime.strftime('%m-%d %H:%M')} ({age_hours:.1f}小时前)\n"
                else:
                    msg += f"❌ {desc}: 未缓存\n"

            msg += "========================\n"
            msg += f"总大小: {total_size / 1024:.1f} KB\n"
            msg += f"缓存目录: {cache_dir}\n"
            msg += "\n💡 API缓存有效期为6小时，过期后会自动刷新"

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"获取API缓存状态失败: {e}")
            yield event.plain_result(f"❌ 获取API缓存状态失败: {e}")

    async def _admin_api_refresh(self, event: AstrMessageEvent):
        """强制刷新 API 数据缓存 - 显示确认提示"""
        try:
            # 设置上下文到确认菜单
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.set_context(user_id, group_id, menu="api_refresh_confirm")

            msg = (
                "⚠️ 确认刷新 API 数据缓存？\n"
                "========================\n"
                "将从 Bestdori 重新获取以下数据:\n"
                "  • 活动数据 (events.json)\n"
                "  • 卡面数据 (cards.json)\n"
                "  • 招募数据 (gachas.json)\n"
                "  • 歌曲数据 (songs.json)\n"
                "========================\n"
                "/1 确认刷新\n"
                "/2 取消操作"
            )
            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"刷新API缓存失败: {e}")
            yield event.plain_result(f"❌ 刷新API缓存失败: {e}")

    async def _admin_api_refresh_confirmed(self, event: AstrMessageEvent):
        """确认后执行刷新 API 数据缓存"""
        try:
            yield event.plain_result("🔄 正在刷新 API 数据缓存...")

            results = []

            # 刷新活动数据
            try:
                await self.client.get_events(force_refresh=True)
                results.append("✅ 活动数据")
            except Exception as e:
                results.append(f"❌ 活动数据: {e}")

            # 刷新卡面数据
            try:
                await self.client.get_cards(force_refresh=True)
                results.append("✅ 卡面数据")
            except Exception as e:
                results.append(f"❌ 卡面数据: {e}")

            # 刷新招募数据
            try:
                await self.client.get_gachas(force_refresh=True)
                results.append("✅ 招募数据")
            except Exception as e:
                results.append(f"❌ 招募数据: {e}")

            # 刷新歌曲数据
            try:
                await self.client.get_songs(force_refresh=True)
                results.append("✅ 歌曲数据")
            except Exception as e:
                results.append(f"❌ 歌曲数据: {e}")

            msg = "[ API 数据刷新结果 ]\n"
            msg += "========================\n"
            for r in results:
                msg += f"  {r}\n"
            msg += "========================\n"
            msg += "💡 数据已从 Bestdori 重新获取"

            yield event.plain_result(msg)

            # 清除上下文
            user_id = event.get_sender_id()
            group_id = (
                event.message_obj.group_id
                if hasattr(event.message_obj, "group_id")
                else ""
            )
            menu_context.clear_context(user_id, group_id)

        except Exception as e:
            logger.error(f"刷新API缓存失败: {e}")
            yield event.plain_result(f"❌ 刷新API缓存失败: {e}")
