"""
生日服务模块
负责处理角色生日相关功能：主动查询和被动推送
"""

import json
import asyncio
import random
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

try:
    from .client import BestdoriClient
    from .consts import (
        CHARACTER_MAP,
        CHARACTER_BIRTHDAYS,
        CHARACTER_BAND_MAP,
        BAND_ID_MAP,
    )
except ImportError:
    from client import BestdoriClient
    from consts import (
        CHARACTER_MAP,
        CHARACTER_BIRTHDAYS,
        CHARACTER_BAND_MAP,
        BAND_ID_MAP,
    )


class BirthdayService:
    """生日服务类"""

    def __init__(self, data_dir: str):
        """
        初始化生日服务

        Args:
            data_dir: 数据存储目录（插件工作区下的data目录）
        """
        self.data_dir = Path(data_dir)
        self.birthday_data_dir = self.data_dir / "birthdays"
        self.birthday_data_dir.mkdir(parents=True, exist_ok=True)
        self.client = BestdoriClient(cache_dir=str(self.data_dir))

    def get_today_birthdays(self) -> List[int]:
        """
        获取今天过生日的角色ID列表

        Returns:
            角色ID列表
        """
        today = datetime.now()
        month, day = today.month, today.day

        birthday_chars = []
        for char_id, (birth_month, birth_day) in CHARACTER_BIRTHDAYS.items():
            if birth_month == month and birth_day == day:
                birthday_chars.append(char_id)

        return birthday_chars

    def get_character_birthday(self, character_id: int) -> Optional[tuple]:
        """
        获取指定角色的生日

        Args:
            character_id: 角色ID

        Returns:
            (月, 日) 元组，如果不存在返回 None
        """
        return CHARACTER_BIRTHDAYS.get(character_id)

    def get_character_name(self, character_id: int) -> str:
        """
        获取角色名称

        Args:
            character_id: 角色ID

        Returns:
            角色名称
        """
        if character_id in CHARACTER_MAP:
            return CHARACTER_MAP[character_id][0]
        return "未知角色"

    def get_character_band_name(self, character_id: int) -> str:
        """
        获取角色所属乐队名称

        Args:
            character_id: 角色ID

        Returns:
            乐队名称
        """
        band_id = CHARACTER_BAND_MAP.get(character_id)
        if band_id:
            return BAND_ID_MAP.get(band_id, "未知乐队")
        return "未知乐队"

    async def get_birthday_cards(self, character_id: int) -> List[Dict[str, Any]]:
        """
        获取指定角色的生日卡片数据

        Args:
            character_id: 角色ID

        Returns:
            生日卡片列表
        """
        try:
            # 获取所有卡片数据
            cards_data = await self.client.get_all_cards()

            # 筛选该角色的生日卡
            birthday_cards = []
            for card_id, card_info in cards_data.items():
                # 检查是否是该角色的生日卡
                if (
                    card_info.get("characterId") == character_id
                    and card_info.get("type") == "birthday"
                ):
                    birthday_cards.append(
                        {
                            "card_id": card_id,
                            "resource_set_name": card_info.get("resourceSetName", ""),
                            "prefix": card_info.get("prefix", ""),
                            "rarity": card_info.get("rarity", 0),
                            "released_at": card_info.get("releasedAt"),
                        }
                    )

            # 按发布时间排序（最新的在前）
            birthday_cards.sort(key=lambda x: x.get("released_at", 0), reverse=True)

            return birthday_cards

        except Exception as e:
            print(f"获取生日卡片失败: {e}")
            return []

    async def download_birthday_resources(self, character_id: int) -> Dict[str, Any]:
        """
        下载指定角色的生日资源（卡面、语音、文本等）

        Args:
            character_id: 角色ID

        Returns:
            资源信息字典
        """
        char_name = self.get_character_name(character_id)
        char_dir = self.birthday_data_dir / f"char_{character_id}"
        char_dir.mkdir(exist_ok=True)

        resources = {
            "character_id": character_id,
            "character_name": char_name,
            "cards": [],
            "downloaded_at": datetime.now().isoformat(),
        }

        try:
            # 获取生日卡片
            birthday_cards = await self.get_birthday_cards(character_id)

            for card in birthday_cards:
                resource_name = card["resource_set_name"]
                card_id = card["card_id"]

                # 处理prefix（可能是列表，取中文版）
                prefix = card["prefix"]
                if isinstance(prefix, list):
                    # 优先使用索引3（国服），如果不存在则使用第一个
                    prefix = prefix[3] if len(prefix) > 3 else prefix[0]

                # 卡面URL（训练后）
                card_image_url = f"https://bestdori.com/assets/jp/characters/resourceset/{resource_name}_rip/card_after_training.png"

                # 生日文本URL（从scenario获取）
                # 生日scenario ID通常是 {cardId}_birthday
                scenario_id = f"{card_id}_birthday"

                card_info = {
                    "card_id": card_id,
                    "resource_set_name": resource_name,
                    "prefix": prefix,
                    "rarity": card["rarity"],
                    "card_image_url": card_image_url,
                    "voice_url": None,  # 下载成功后更新
                    "scenario_id": scenario_id,
                    "birthday_text": None,  # 将在下载时获取
                    "local_card_path": None,
                    "local_voice_path": None,
                }

                # 下载卡面图片
                card_local_path = char_dir / f"card_{card_id}.png"
                if not card_local_path.exists():
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(card_image_url) as resp:
                                    if resp.status == 200:
                                        with open(card_local_path, "wb") as f:
                                            f.write(await resp.read())
                                        card_info["local_card_path"] = str(
                                            card_local_path
                                        )
                                        break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                print(f"下载卡面 {card_id} 失败: {e}")
                            else:
                                await asyncio.sleep(1)
                else:
                    card_info["local_card_path"] = str(card_local_path)

                # 下载语音文件（尝试两种URL格式）
                voice_local_path = char_dir / f"voice_{card_id}.mp3"

                # 即使文件存在，也建议检查一下大小，确保不是错误的HTML文件（可选，但考虑到之前的错误，这里先不强制重下，除非文件极小）
                # 为了稳健，我们先假设如果存在且大于1KB就是好的。
                need_download_voice = True
                if voice_local_path.exists() and voice_local_path.stat().st_size > 1024:
                    need_download_voice = False
                    card_info["local_voice_path"] = str(voice_local_path)

                if need_download_voice:
                    # 早期生日卡用spin_rip，后期用birthdayspin_rip，尝试两种URL
                    # 优先尝试 birthdayspin_rip (新卡概率高)，然后 spin_rip
                    voice_urls = [
                        f"https://bestdori.com/assets/cn/sound/voice/gacha/birthdayspin_rip/{resource_name}.mp3",
                        f"https://bestdori.com/assets/cn/sound/voice/gacha/spin_rip/{resource_name}.mp3",
                    ]

                    downloaded = False
                    async with aiohttp.ClientSession() as session:
                        for voice_url_attempt in voice_urls:
                            try:
                                async with session.get(voice_url_attempt) as resp:
                                    if resp.status == 200:
                                        content = await resp.read()
                                        # 验证是否为音频文件（检查Content-Type或文件头）
                                        content_type = resp.headers.get(
                                            "Content-Type", ""
                                        )
                                        # 检查文件头 ID3 或 MP3 sync word (FF FB / FF F3)
                                        is_mp3 = False
                                        if "audio" in content_type:
                                            is_mp3 = True
                                        elif len(content) > 3 and (
                                            content[:3] == b"ID3"
                                            or content[:2] in [b"\xff\xfb", b"\xff\xf3"]
                                        ):
                                            is_mp3 = True

                                        if is_mp3:
                                            with open(voice_local_path, "wb") as f:
                                                f.write(content)
                                            card_info["local_voice_path"] = str(
                                                voice_local_path
                                            )
                                            card_info["voice_url"] = voice_url_attempt
                                            downloaded = True
                                            break
                            except Exception:
                                continue

                    if not downloaded:
                        print(f"下载语音 {card_id} 失败: 尝试了所有URL格式")

                # 获取生日文本（从API）
                try:
                    text = await self._get_birthday_text(card_id)
                    if text:
                        card_info["birthday_text"] = text
                except Exception as e:
                    print(f"获取生日文本 {card_id} 失败: {e}")

                resources["cards"].append(card_info)

            # 保存资源信息到本地
            resource_file = char_dir / "resources.json"
            with open(resource_file, "w", encoding="utf-8") as f:
                json.dump(resources, f, ensure_ascii=False, indent=2)

            return resources

        except Exception as e:
            print(f"下载角色 {char_name} 生日资源失败: {e}")
            return resources

    async def _get_birthday_text(self, card_id: int) -> Optional[str]:
        """
        从Bestdori API获取生日文本（从gachaText获取）

        Args:
            card_id: 卡片ID

        Returns:
            生日文本（中文）
        """
        try:
            # 获取卡片信息中的gachaText
            card_url = f"https://bestdori.com/api/cards/{card_id}.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(card_url) as resp:
                    if resp.status != 200:
                        return None

                    card_data = await resp.json()

                    # gachaText数组: [日文, 英文, 繁中, 简中, 韩文]
                    # 索引3是简体中文
                    gacha_text = card_data.get("gachaText", [])
                    if gacha_text and len(gacha_text) > 3:
                        cn_text = gacha_text[3]  # 简中
                        if cn_text and cn_text.strip():
                            return cn_text.strip()

                    # 如果没有简中，尝试日文
                    if gacha_text and len(gacha_text) > 0:
                        jp_text = gacha_text[0]
                        if jp_text and jp_text.strip():
                            return jp_text.strip()

        except Exception as e:
            print(f"获取生日文本失败: {e}")

        return None

    async def download_all_birthday_resources(self):
        """
        预下载所有角色的生日资源
        """
        print("开始预下载所有角色的生日资源...")
        count = 0
        total = len(CHARACTER_BIRTHDAYS)

        for character_id in CHARACTER_BIRTHDAYS.keys():
            char_name = self.get_character_name(character_id)
            print(
                f"[{count + 1}/{total}] 正在下载 {char_name} (ID: {character_id}) 的生日资源..."
            )

            try:
                await self.download_birthday_resources(character_id)
                # 避免请求过于频繁
                await asyncio.sleep(1)
            except Exception as e:
                print(f"下载 {char_name} 资源出错: {e}")

            count += 1

        print("所有角色生日资源下载完成！")

    def get_cached_birthday_resources(
        self, character_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的生日资源信息

        Args:
            character_id: 角色ID

        Returns:
            资源信息字典，如果不存在返回 None
        """
        char_dir = self.birthday_data_dir / f"char_{character_id}"
        resource_file = char_dir / "resources.json"

        if resource_file.exists():
            try:
                with open(resource_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取缓存失败: {e}")

        return None

    async def get_birthday_message(self, character_id: int) -> Dict[str, Any]:
        """
        获取生日祝福消息内容（随机选择一张生日卡）

        Args:
            character_id: 角色ID

        Returns:
            包含角色信息、生日信息、随机选中的生日卡等的字典
        """
        char_name = self.get_character_name(character_id)
        band_name = self.get_character_band_name(character_id)
        birthday = self.get_character_birthday(character_id)

        if not birthday:
            return {}

        month, day = birthday

        # 尝试从缓存读取
        resources = self.get_cached_birthday_resources(character_id)

        # 如果缓存不存在，实时下载
        if not resources:
            resources = await self.download_birthday_resources(character_id)

        # 随机选择一张生日卡
        selected_card = None
        if resources.get("cards"):
            selected_card = random.choice(resources["cards"])

        return {
            "character_id": character_id,
            "character_name": char_name,
            "band_name": band_name,
            "birthday": f"{month}月{day}日",
            "selected_card": selected_card,  # 只包含一张随机选择的卡
            "all_cards_count": len(resources.get("cards", [])),
        }
