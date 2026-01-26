import aiohttp
import asyncio  # 添加 asyncio
import json
import os
import time
import logging
from typing import Dict, Any, Optional


class BestdoriClient:
    BASE_URL = "https://bestdori.com/api"
    # 服务器映射: 0=JP, 1=EN, 2=TW, 3=CN, 4=KR
    SERVER_CN = 3

    def __init__(self, cache_dir: str = "data/bestdori_cache"):
        """
        初始化客户端
        :param cache_dir: 缓存文件存储的目录
        """
        self.server = self.SERVER_CN
        self.cache_dir = cache_dir
        self.logger = logging.getLogger("bestdori_client")

        # 如果缓存目录不存在，就创建一个
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    async def _fetch_json(
        self, endpoint: str, filename: str, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        通用的 JSON 获取方法，带缓存功能
        :param endpoint: API 的后缀路径，例如 'events/all.5.json'
        :param filename: 本地保存的文件名，例如 'events.json'
        :param force_refresh: 是否强制从网络重新下载
        """
        file_path = os.path.join(self.cache_dir, filename)

        # 1. 检查缓存
        # 如果不强制刷新，且文件存在
        if not force_refresh and os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            # 如果文件是 6 小时内创建的 (21600秒)，直接使用
            if time.time() - mtime < 21600:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError:
                    # 如果文件损坏，则继续向下执行去重新下载
                    pass

        # 2. 从网络下载
        async with aiohttp.ClientSession() as session:
            url = f"{self.BASE_URL}/{endpoint}"
            try:
                self.logger.info(f"正在从 {url} 下载数据...")
                async with session.get(url) as response:
                    response.raise_for_status()  # 如果状态码不是 200，抛出异常
                    data = await response.json()

                    # 3. 保存到本地
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                    return data
            except Exception as e:
                self.logger.error(f"下载失败: {e}")
                # 4. 如果下载失败（比如没网），尝试读取过期的缓存作为保底
                if os.path.exists(file_path):
                    self.logger.warning("使用过期的本地缓存作为后备。")
                    with open(file_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                raise e  # 既没网也没缓存，只能报错了

    async def get_events(self, force_refresh: bool = False):
        """获取所有活动数据"""
        # events/all.5.json 包含了所有活动的摘要信息
        # .5.json 是 bestdori 的一种压缩格式，但也包含主要信息
        return await self._fetch_json("events/all.5.json", "events.json", force_refresh)

    async def get_cards(self, force_refresh: bool = False):
        """获取所有卡面数据"""
        return await self._fetch_json("cards/all.5.json", "cards.json", force_refresh)

    async def get_all_cards(self, force_refresh: bool = False):
        """获取所有卡面数据（别名方法）"""
        return await self.get_cards(force_refresh)

    async def get_gachas(self, force_refresh: bool = False):
        """获取所有招募数据"""
        return await self._fetch_json("gacha/all.5.json", "gachas.json", force_refresh)

    async def get_songs(self, force_refresh: bool = False):
        """获取所有歌曲数据"""
        return await self._fetch_json("songs/all.5.json", "songs.json", force_refresh)

    async def get_event_detail(self, event_id: int, force_refresh: bool = False):
        """获取单个活动的详细信息（包含追加歌曲、表情包奖励等）"""
        return await self._fetch_json(
            f"events/{event_id}.json", f"event_{event_id}.json", force_refresh
        )

    async def get_song_detail(self, song_id: int, force_refresh: bool = False):
        """获取单首歌曲的详细信息"""
        return await self._fetch_json(
            f"songs/{song_id}.json", f"song_{song_id}.json", force_refresh
        )

    async def get_card_detail(self, card_id: int, force_refresh: bool = False):
        """获取单张卡面的详细信息"""
        return await self._fetch_json(
            f"cards/{card_id}.json", f"card_{card_id}.json", force_refresh
        )

    async def get_costume_detail(self, costume_id: int, force_refresh: bool = False):
        """获取服装详细信息（包含assetBundleName用于Live2D小人URL）"""
        return await self._fetch_json(
            f"costumes/{costume_id}.json", f"costume_{costume_id}.json", force_refresh
        )

    async def get_stamps(self, force_refresh: bool = False):
        """获取所有表情包数据（包含imageName用于构建URL）"""
        return await self._fetch_json("stamps/all.2.json", "stamps.json", force_refresh)

    async def get_costumes(self, force_refresh: bool = False):
        """获取所有服装数据"""
        return await self._fetch_json(
            "costumes/all.5.json", "costumes.json", force_refresh
        )

    def get_costume_icon_url(
        self, costume_id: int, asset_bundle_name: str, server: str = "cn"
    ) -> str:
        """
        获取服装 Live2D 缩略图 URL

        Args:
            costume_id: 服装ID
            asset_bundle_name: 资源包名称
            server: 服务器代码 (jp, en, tw, cn, kr)，默认 cn

        Returns:
            服装缩略图URL
        """
        group = costume_id // 50
        return f"https://bestdori.com/assets/{server}/thumb/costume/group{group}_rip/{asset_bundle_name}.png"

    async def download_image(self, url: str) -> Optional[str]:
        """
        下载图片并保存到本地缓存 (使用 aiohttp 异步下载)
        """
        if not url:
            return None

        # 生成文件名
        parts = url.split("/")
        if len(parts) >= 3:
            if "resourceset" in parts:
                try:
                    idx = parts.index("resourceset")
                    prefix = parts[idx + 1]
                    filename = f"{prefix}_{parts[-1]}"
                except:
                    filename = f"{parts[-3]}_{parts[-1]}"
            elif "images_rip" in url:
                filename = f"{parts[-3]}_{parts[-1]}"
            else:
                filename = parts[-1]
        else:
            filename = parts[-1]

        if "/thumb/" in url and not filename.startswith("thumb_"):
            filename = f"thumb_{filename}"

        img_dir = os.path.join(self.cache_dir, "images")
        if not os.path.exists(img_dir):
            os.makedirs(img_dir)

        file_path = os.path.join(img_dir, filename)
        abs_path = os.path.abspath(file_path)

        is_rip = "rip" in url
        min_size = 5000 if is_rip else 100

        # 检查缓存文件
        if os.path.exists(file_path) and os.path.getsize(file_path) > min_size:
            return abs_path

        # 构建尝试 URL 列表
        try_urls = [url]

        # 添加备用服务器 (仅针对 Bestdori 资源)
        if "bestdori.com/assets/" in url:
            servers = ["jp", "cn", "en", "tw", "kr"]
            current_server = None
            for s in servers:
                if f"/assets/{s}/" in url:
                    current_server = s
                    break

            if current_server:
                for s in servers:
                    if s != current_server:
                        try_urls.append(
                            url.replace(f"/assets/{current_server}/", f"/assets/{s}/")
                        )

        headers = {"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"}

        async with aiohttp.ClientSession() as session:
            for try_url in try_urls:
                try:
                    async with session.get(
                        try_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            continue

                        content_type = resp.headers.get("Content-Type", "").lower()
                        if "image" not in content_type:
                            continue

                        content = await resp.read()

                        with open(file_path, "wb") as f:
                            f.write(content)

                        if os.path.getsize(file_path) < 100:
                            # 文件太小，尝试下一个 URL
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                            continue

                        self.logger.info(f"下载成功: {filename}")
                        return abs_path

                except asyncio.TimeoutError:
                    self.logger.warning(f"下载超时: {try_url}")
                except Exception as e:
                    self.logger.warning(f"aiohttp 下载异常 ({try_url}): {e}")

                # 清理可能的不完整文件
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass

        # 所有尝试都失败
        self.logger.warning(f"图片下载失败 (尝试了 {len(try_urls)} 个服务器): {url}")
        return None
