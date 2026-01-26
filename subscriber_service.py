"""
订阅用户管理服务

通过用户与 bot 的互动自动收集和管理订阅用户列表
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Set, Optional
from pathlib import Path

try:
    from astrbot.api import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class SubscriberService:
    """订阅用户管理服务"""

    def __init__(self, data_dir: str):
        """
        初始化订阅服务

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.subscribers_file = self.data_dir / "subscribers.json"
        self.subscribers: Dict[str, dict] = {}
        self._load_subscribers()

    def _load_subscribers(self):
        """加载订阅用户数据"""
        if self.subscribers_file.exists():
            try:
                with open(self.subscribers_file, "r", encoding="utf-8") as f:
                    self.subscribers = json.load(f)
                logger.info(f"📋 已加载 {len(self.subscribers)} 个订阅用户")
            except Exception as e:
                logger.warning(f"加载订阅用户数据失败: {e}")
                self.subscribers = {}
        else:
            self.subscribers = {}

    def _save_subscribers(self):
        """保存订阅用户数据"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.subscribers_file, "w", encoding="utf-8") as f:
                json.dump(self.subscribers, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存订阅用户数据失败: {e}")

    def record_user_activity(
        self, user_id: str, platform: str = "", nickname: str = "", from_group: str = ""
    ) -> bool:
        """
        记录用户活动（自动订阅）

        当用户私聊 bot 或在群里 @bot 时调用此方法

        Args:
            user_id: 用户ID（QQ号）
            platform: 平台标识
            nickname: 用户昵称
            from_group: 来源群组（如果是群聊触发）

        Returns:
            True 如果是新用户，False 如果是已有用户
        """
        user_id = str(user_id)
        now = datetime.now().isoformat()

        is_new = user_id not in self.subscribers

        if is_new:
            # 新用户，添加订阅
            self.subscribers[user_id] = {
                "user_id": user_id,
                "platform": platform,
                "nickname": nickname,
                "subscribed": True,
                "first_seen": now,
                "last_active": now,
                "interaction_count": 1,
                "from_groups": [from_group] if from_group else [],
            }
            logger.info(f"📥 新用户订阅: {nickname or user_id}")
        else:
            # 已有用户，更新活动时间
            self.subscribers[user_id]["last_active"] = now
            self.subscribers[user_id]["interaction_count"] = (
                self.subscribers[user_id].get("interaction_count", 0) + 1
            )

            # 更新昵称（如果有）
            if nickname:
                self.subscribers[user_id]["nickname"] = nickname

            # 更新来源群组
            if from_group:
                groups = self.subscribers[user_id].get("from_groups", [])
                if from_group not in groups:
                    groups.append(from_group)
                    self.subscribers[user_id]["from_groups"] = groups

        self._save_subscribers()
        return is_new

    def subscribe(self, user_id: str) -> bool:
        """
        用户订阅播报

        Args:
            user_id: 用户ID

        Returns:
            True 如果订阅成功，False 如果已经订阅
        """
        user_id = str(user_id)

        if user_id in self.subscribers:
            if self.subscribers[user_id].get("subscribed", True):
                return False  # 已经订阅
            self.subscribers[user_id]["subscribed"] = True
        else:
            self.subscribers[user_id] = {
                "user_id": user_id,
                "subscribed": True,
                "first_seen": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "interaction_count": 1,
            }

        self._save_subscribers()
        return True

    def unsubscribe(self, user_id: str) -> bool:
        """
        用户取消订阅

        Args:
            user_id: 用户ID

        Returns:
            True 如果取消成功，False 如果未订阅
        """
        user_id = str(user_id)

        if user_id not in self.subscribers:
            return False

        if not self.subscribers[user_id].get("subscribed", True):
            return False  # 已经取消订阅

        self.subscribers[user_id]["subscribed"] = False
        self._save_subscribers()
        return True

    def is_subscribed(self, user_id: str) -> bool:
        """检查用户是否已订阅"""
        user_id = str(user_id)
        if user_id not in self.subscribers:
            return False
        return self.subscribers[user_id].get("subscribed", True)

    def get_subscribed_users(self, blacklist: Set[str] = None) -> List[str]:
        """
        获取所有已订阅的用户列表

        Args:
            blacklist: 黑名单用户集合

        Returns:
            订阅用户ID列表
        """
        blacklist = blacklist or set()

        users = []
        for user_id, data in self.subscribers.items():
            # 检查是否订阅
            if not data.get("subscribed", True):
                continue
            # 检查黑名单
            if user_id in blacklist:
                continue
            users.append(user_id)

        return users

    def get_subscriber_count(self) -> int:
        """获取订阅用户数量"""
        return sum(
            1 for data in self.subscribers.values() if data.get("subscribed", True)
        )

    def get_subscriber_info(self, user_id: str) -> Optional[dict]:
        """获取订阅用户信息"""
        return self.subscribers.get(str(user_id))

    def get_all_subscribers_info(self) -> Dict[str, dict]:
        """获取所有订阅用户信息"""
        return {
            uid: data
            for uid, data in self.subscribers.items()
            if data.get("subscribed", True)
        }
