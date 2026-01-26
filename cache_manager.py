import json
import hashlib
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger("astrbot_plugin_bestdori_tools")


class CacheManager:
    """
    缓存管理器 - 负责管理所有缓存文件的生命周期

    功能：
    1. 缓存读写操作
    2. 缓存键生成（基于查询参数的哈希）
    3. 缓存过期检查
    4. 空间管理和自动清理
    5. 缓存统计
    """

    def __init__(self, cache_dir: str, config: Dict = None):
        """
        初始化缓存管理器

        Args:
            cache_dir: 缓存目录路径
            config: 配置字典，包含：
                - cache_enabled: 是否启用缓存（默认 True）
                - cache_max_size: 最大缓存大小（字节，默认 1GB）
                - cache_event_ttl: 活动缓存 TTL（秒，默认 24小时）
                - cache_card_ttl: 卡面缓存 TTL（秒，默认 7天）
                - cache_birthday_ttl: 生日缓存 TTL（秒，默认 30天）
                - cache_cleanup_interval: 清理间隔（秒，默认 24小时）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        self.events_dir = self.cache_dir / "events"
        self.cards_dir = self.cache_dir / "cards"
        self.birthdays_dir = self.cache_dir / "birthdays"

        for subdir in [self.events_dir, self.cards_dir, self.birthdays_dir]:
            subdir.mkdir(parents=True, exist_ok=True)

        # 配置参数
        self.config = config or {}
        self.cache_enabled = self.config.get("cache_enabled", True)
        self.cache_max_size = self.config.get("cache_max_size", 1073741824)  # 1GB
        self.cache_event_ttl = self.config.get("cache_event_ttl", 86400)  # 24小时
        self.cache_card_ttl = self.config.get("cache_card_ttl", 604800)  # 7天
        self.cache_birthday_ttl = self.config.get("cache_birthday_ttl", 2592000)  # 30天
        self.cache_cleanup_interval = self.config.get(
            "cache_cleanup_interval", 86400
        )  # 24小时

        # 索引文件路径
        self.index_file = self.cache_dir / "cache_index.json"

        # 加载或初始化索引
        self.index = self._load_index()

        # 最后清理时间
        self.last_cleanup_time = self.index.get("stats", {}).get("last_cleanup", 0)

    def _load_index(self) -> Dict:
        """加载缓存索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载缓存索引失败: {e}，将创建新索引")

        # 初始化新索引
        return {
            "cache_index": {"events": {}, "cards": {}, "birthdays": {}},
            "stats": {
                "total_size": 0,
                "max_size": self.cache_max_size,
                "last_cleanup": int(datetime.now().timestamp()),
                "cleanup_interval": self.cache_cleanup_interval,
            },
        }

    def _save_index(self) -> None:
        """保存缓存索引"""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存缓存索引失败: {e}")

    def generate_cache_key(self, category: str, **params) -> str:
        """
        生成缓存键（基于参数的哈希）

        Args:
            category: 缓存类别 (event, card, birthday)
            **params: 查询参数

        Returns:
            缓存键
        """
        # 将参数排序后转换为字符串
        param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:16]
        return f"{category}_{param_hash}"

    async def get_cache(self, category: str, **params) -> Optional[str]:
        """
        获取缓存文件路径

        Args:
            category: 缓存类别 (event, card, birthday)
            **params: 查询参数

        Returns:
            缓存文件路径，如果不存在或已过期则返回 None
        """
        if not self.cache_enabled:
            return None

        # 规范化类别名称
        category_map = {"event": "events", "card": "cards", "birthday": "birthdays"}
        normalized_category = category_map.get(category, category)

        cache_key = self.generate_cache_key(category, **params)

        # 从索引中查找
        cache_data = (
            self.index.get("cache_index", {})
            .get(normalized_category, {})
            .get(cache_key)
        )

        if not cache_data:
            return None

        # 检查文件是否存在
        cache_file = self.cache_dir / cache_data.get("file", "")
        if not cache_file.exists():
            logger.warning(f"缓存文件不存在: {cache_file}，将删除索引")
            await self.delete_cache(category, **params)
            return None

        # 检查是否过期
        created_at = cache_data.get("created_at", 0)
        ttl = cache_data.get("ttl", 0)
        current_time = int(datetime.now().timestamp())

        if current_time - created_at > ttl:
            logger.info(f"缓存已过期: {cache_key}")
            await self.delete_cache(category, **params)
            return None

        # 更新访问时间
        cache_data["accessed_at"] = current_time
        self._save_index()

        return str(cache_file)

    async def set_cache(
        self, category: str, file_path: str, ttl: int = None, **params
    ) -> bool:
        """
        保存缓存文件

        Args:
            category: 缓存类别 (event, card, birthday)
            file_path: 源文件路径
            ttl: 缓存过期时间（秒），如果为 None 则使用默认值
            **params: 查询参数

        Returns:
            是否保存成功
        """
        if not self.cache_enabled:
            return False

        try:
            source_file = Path(file_path)
            if not source_file.exists():
                logger.error(f"源文件不存在: {file_path}")
                return False

            # 规范化类别名称（event -> events, card -> cards, birthday -> birthdays）
            category_map = {"event": "events", "card": "cards", "birthday": "birthdays"}
            normalized_category = category_map.get(category, category)

            # 确定 TTL
            if ttl is None:
                if category == "event":
                    ttl = self.cache_event_ttl
                elif category == "card":
                    ttl = self.cache_card_ttl
                elif category == "birthday":
                    ttl = self.cache_birthday_ttl
                else:
                    ttl = 86400  # 默认 24 小时

            # 生成缓存键和文件名
            cache_key = self.generate_cache_key(category, **params)
            cache_filename = f"{category}_{cache_key}.png"

            # 确定目标目录
            if normalized_category == "events":
                target_dir = self.events_dir
            elif normalized_category == "cards":
                target_dir = self.cards_dir
            elif normalized_category == "birthdays":
                target_dir = self.birthdays_dir
            else:
                target_dir = self.cache_dir

            target_file = target_dir / cache_filename

            # 复制文件到缓存目录
            with open(source_file, "rb") as src:
                with open(target_file, "wb") as dst:
                    dst.write(src.read())

            # 获取文件大小
            file_size = target_file.stat().st_size
            current_time = int(datetime.now().timestamp())

            # 更新索引
            if normalized_category not in self.index["cache_index"]:
                self.index["cache_index"][normalized_category] = {}

            self.index["cache_index"][normalized_category][cache_key] = {
                "file": str(target_file.relative_to(self.cache_dir)),
                "created_at": current_time,
                "accessed_at": current_time,
                "size": file_size,
                "query_hash": cache_key,
                "ttl": ttl,
                "params": params,  # 保存原始查询参数，用于显示友好信息
            }

            # 更新统计信息
            self.index["stats"]["total_size"] = self._calculate_total_size()
            self._save_index()

            logger.info(f"缓存已保存: {category}/{cache_key} ({file_size} bytes)")

            # 检查是否需要清理
            await self._check_and_cleanup()

            return True

        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            return False

    async def delete_cache(self, category: str, **params) -> bool:
        """
        删除缓存文件

        Args:
            category: 缓存类别
            **params: 查询参数

        Returns:
            是否删除成功
        """
        try:
            # 规范化类别名称
            category_map = {"event": "events", "card": "cards", "birthday": "birthdays"}
            normalized_category = category_map.get(category, category)

            cache_key = self.generate_cache_key(category, **params)
            cache_data = (
                self.index.get("cache_index", {})
                .get(normalized_category, {})
                .get(cache_key)
            )

            if not cache_data:
                return False

            # 删除文件
            cache_file = self.cache_dir / cache_data.get("file", "")
            if cache_file.exists():
                cache_file.unlink()

            # 从索引中删除
            del self.index["cache_index"][normalized_category][cache_key]

            # 更新统计信息
            self.index["stats"]["total_size"] = self._calculate_total_size()
            self._save_index()

            logger.info(f"缓存已删除: {category}/{cache_key}")
            return True

        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            return False

    def _calculate_total_size(self) -> int:
        """计算缓存总大小"""
        total = 0
        for category_data in self.index.get("cache_index", {}).values():
            for cache_data in category_data.values():
                total += cache_data.get("size", 0)
        return total

    async def _check_and_cleanup(self) -> None:
        """检查是否需要清理缓存"""
        current_time = int(datetime.now().timestamp())

        # 检查是否到达清理间隔
        if current_time - self.last_cleanup_time >= self.cache_cleanup_interval:
            logger.info("触发定时缓存清理")
            await self.cleanup_expired()
            await self.cleanup_by_size()
            self.last_cleanup_time = current_time

    async def cleanup_expired(self) -> Dict:
        """
        清理过期缓存

        Returns:
            清理统计信息
        """
        logger.info("开始清理过期缓存...")
        current_time = int(datetime.now().timestamp())
        deleted_count = 0
        freed_size = 0

        try:
            for category in ["events", "cards", "birthdays"]:
                cache_items = list(
                    self.index.get("cache_index", {}).get(category, {}).items()
                )

                for cache_key, cache_data in cache_items:
                    created_at = cache_data.get("created_at", 0)
                    ttl = cache_data.get("ttl", 0)

                    # 检查是否过期
                    if current_time - created_at > ttl:
                        cache_file = self.cache_dir / cache_data.get("file", "")

                        # 删除文件
                        if cache_file.exists():
                            freed_size += cache_file.stat().st_size
                            cache_file.unlink()

                        # 从索引中删除
                        del self.index["cache_index"][category][cache_key]
                        deleted_count += 1
                        logger.debug(f"删除过期缓存: {category}/{cache_key}")

            # 更新统计信息
            self.index["stats"]["total_size"] = self._calculate_total_size()
            self.index["stats"]["last_cleanup"] = current_time
            self._save_index()

            logger.info(
                f"过期缓存清理完成: 删除 {deleted_count} 个文件，释放 {freed_size / 1024 / 1024:.2f} MB"
            )

            return {
                "deleted_count": deleted_count,
                "freed_size": freed_size,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")
            return {
                "deleted_count": deleted_count,
                "freed_size": freed_size,
                "status": "error",
                "error": str(e),
            }

    async def cleanup_by_size(self) -> Dict:
        """
        按大小清理缓存（LRU 策略）

        当缓存总大小超过上限时，删除最久未访问的文件
        直到总大小降低到上限的 80%

        Returns:
            清理统计信息
        """
        total_size = self.index["stats"]["total_size"]

        if total_size <= self.cache_max_size:
            return {
                "deleted_count": 0,
                "freed_size": 0,
                "status": "no_need",
                "current_size": total_size,
                "max_size": self.cache_max_size,
            }

        logger.info(
            f"缓存大小超限 ({total_size / 1024 / 1024:.2f} MB > {self.cache_max_size / 1024 / 1024:.2f} MB)，开始 LRU 清理..."
        )

        try:
            # 收集所有缓存项
            all_items = []
            for category in ["events", "cards", "birthdays"]:
                for cache_key, cache_data in (
                    self.index.get("cache_index", {}).get(category, {}).items()
                ):
                    all_items.append(
                        {
                            "category": category,
                            "cache_key": cache_key,
                            "accessed_at": cache_data.get("accessed_at", 0),
                            "size": cache_data.get("size", 0),
                            "file": cache_data.get("file", ""),
                        }
                    )

            # 按访问时间排序（最久未访问的在前）
            all_items.sort(key=lambda x: x["accessed_at"])

            # 计算目标大小（上限的 80%）
            target_size = int(self.cache_max_size * 0.8)
            deleted_count = 0
            freed_size = 0

            # 删除最久未访问的文件
            for item in all_items:
                if total_size <= target_size:
                    break

                cache_file = self.cache_dir / item["file"]
                if cache_file.exists():
                    file_size = cache_file.stat().st_size
                    cache_file.unlink()
                    freed_size += file_size
                    total_size -= file_size

                # 从索引中删除
                del self.index["cache_index"][item["category"]][item["cache_key"]]
                deleted_count += 1
                logger.debug(f"LRU 删除缓存: {item['category']}/{item['cache_key']}")

            # 更新统计信息
            self.index["stats"]["total_size"] = total_size
            self._save_index()

            logger.info(
                f"LRU 清理完成: 删除 {deleted_count} 个文件，释放 {freed_size / 1024 / 1024:.2f} MB，当前大小 {total_size / 1024 / 1024:.2f} MB"
            )

            return {
                "deleted_count": deleted_count,
                "freed_size": freed_size,
                "status": "success",
                "current_size": total_size,
                "target_size": target_size,
            }

        except Exception as e:
            logger.error(f"LRU 清理失败: {e}")
            return {
                "deleted_count": 0,
                "freed_size": 0,
                "status": "error",
                "error": str(e),
            }

    async def clear_all_cache(self) -> Dict:
        """
        清空所有缓存

        Returns:
            清理统计信息
        """
        logger.info("开始清空所有缓存...")
        deleted_count = 0
        freed_size = 0

        try:
            for category in ["events", "cards", "birthdays"]:
                cache_items = list(
                    self.index.get("cache_index", {}).get(category, {}).items()
                )

                for cache_key, cache_data in cache_items:
                    cache_file = self.cache_dir / cache_data.get("file", "")

                    if cache_file.exists():
                        freed_size += cache_file.stat().st_size
                        cache_file.unlink()

                    deleted_count += 1

                # 清空该类别的索引
                self.index["cache_index"][category] = {}

            # 更新统计信息
            self.index["stats"]["total_size"] = 0
            self._save_index()

            logger.info(
                f"缓存清空完成: 删除 {deleted_count} 个文件，释放 {freed_size / 1024 / 1024:.2f} MB"
            )

            return {
                "deleted_count": deleted_count,
                "freed_size": freed_size,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            return {
                "deleted_count": deleted_count,
                "freed_size": freed_size,
                "status": "error",
                "error": str(e),
            }

    def get_cache_stats(self) -> Dict:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        stats = self.index.get("stats", {})
        total_size = stats.get("total_size", 0)
        max_size = stats.get("max_size", self.cache_max_size)

        # 统计各类别的缓存数量
        category_stats = {}
        for category in ["events", "cards", "birthdays"]:
            items = self.index.get("cache_index", {}).get(category, {})
            category_stats[category] = {
                "count": len(items),
                "size": sum(item.get("size", 0) for item in items.values()),
            }

        return {
            "cache_enabled": self.cache_enabled,
            "total_size": total_size,
            "total_size_mb": total_size / 1024 / 1024,
            "max_size": max_size,
            "max_size_mb": max_size / 1024 / 1024,
            "usage_percent": (total_size / max_size * 100) if max_size > 0 else 0,
            "last_cleanup": stats.get("last_cleanup", 0),
            "categories": category_stats,
        }

    def get_cache_list(self, category: str = None, limit: int = 20) -> List[Dict]:
        """
        获取缓存文件列表（带详细信息）

        Args:
            category: 可选，指定类别 (events, cards, birthdays)，为 None 则返回全部
            limit: 返回条目数量限制

        Returns:
            缓存条目列表，每个条目包含：
            - category: 类别
            - cache_key: 缓存键
            - params: 原始查询参数
            - size: 文件大小
            - created_at: 创建时间
            - accessed_at: 最后访问时间
            - ttl: 过期时间
            - expires_at: 过期时间戳
            - is_expired: 是否已过期
        """
        result = []
        current_time = int(datetime.now().timestamp())

        categories = [category] if category else ["events", "cards", "birthdays"]

        for cat in categories:
            items = self.index.get("cache_index", {}).get(cat, {})
            for cache_key, cache_data in items.items():
                created_at = cache_data.get("created_at", 0)
                ttl = cache_data.get("ttl", 0)
                expires_at = created_at + ttl

                result.append(
                    {
                        "category": cat,
                        "cache_key": cache_key,
                        "params": cache_data.get("params", {}),
                        "size": cache_data.get("size", 0),
                        "created_at": created_at,
                        "accessed_at": cache_data.get("accessed_at", 0),
                        "ttl": ttl,
                        "expires_at": expires_at,
                        "is_expired": current_time > expires_at,
                    }
                )

        # 按访问时间降序排序（最近访问的在前）
        result.sort(key=lambda x: x["accessed_at"], reverse=True)

        return result[:limit]

    @property
    def cache_base_dir(self) -> Path:
        """返回缓存基础目录"""
        return self.cache_dir

    async def start_cleanup_scheduler(self) -> None:
        """
        启动定时清理任务

        在后台定期检查和清理缓存
        """
        logger.info("启动缓存清理调度器...")

        while True:
            try:
                await asyncio.sleep(self.cache_cleanup_interval)

                logger.debug("执行定时缓存清理...")
                await self.cleanup_expired()
                await self.cleanup_by_size()

            except Exception as e:
                logger.error(f"缓存清理调度器错误: {e}")
