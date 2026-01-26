from typing import Dict, Any, Optional, List
from datetime import datetime

# 服务器常量
SERVER_JP = 0
SERVER_EN = 1
SERVER_TW = 2
SERVER_CN = 3
SERVER_KR = 4

SERVER_CODE_MAP = {
    SERVER_JP: "jp",
    SERVER_EN: "en",
    SERVER_TW: "tw",
    SERVER_CN: "cn",
    SERVER_KR: "kr",
}


class BaseModel:
    def __init__(self, data: Dict[str, Any]):
        self.raw_data = data

    @staticmethod
    def get_server_content(
        data: Any, server: int = 3, fallback_servers: List[int] = None
    ) -> Optional[str]:
        """获取指定服务器的内容，支持回退

        Args:
            data: 原始数据（可能是列表或字典）
            server: 首选服务器ID
            fallback_servers: 回退服务器列表，默认 [3, 0, 1, 2, 4]
        """
        if not data:
            return None

        if fallback_servers is None:
            fallback_servers = [SERVER_CN, SERVER_JP, SERVER_EN, SERVER_TW, SERVER_KR]

        # 确保首选服务器在最前面
        servers_to_try = [server] + [s for s in fallback_servers if s != server]

        if isinstance(data, dict):
            for s in servers_to_try:
                server_str = str(s)
                if server_str in data and data[server_str]:
                    return data[server_str]
        if isinstance(data, list):
            for s in servers_to_try:
                if 0 <= s < len(data) and data[s]:
                    return data[s]
        return None

    @staticmethod
    def has_server_data(data: Any, server: int) -> bool:
        """检查是否有指定服务器的数据"""
        if not data:
            return False
        if isinstance(data, dict):
            return str(server) in data and data[str(server)] is not None
        if isinstance(data, list):
            return 0 <= server < len(data) and data[server] is not None
        return False


class Event(BaseModel):
    def __init__(self, event_id: int, data: Dict[str, Any]):
        super().__init__(data)
        self.event_id = event_id

    @property
    def name(self) -> str:
        return (
            self.get_server_content(self.raw_data.get("eventName"))
            or f"Event {self.event_id}"
        )

    def get_name(self, server: int = SERVER_CN) -> str:
        """获取指定服务器的活动名称"""
        return (
            self.get_server_content(self.raw_data.get("eventName"), server)
            or f"Event {self.event_id}"
        )

    def get_start_time(self, server: int = 3) -> Optional[int]:
        raw = self.raw_data.get("startAt")
        if not raw:
            return None
        val = None
        if isinstance(raw, list) and 0 <= server < len(raw):
            val = raw[server]
        elif isinstance(raw, dict):
            val = raw.get(str(server))
        return int(val) if val else None

    def get_end_time(self, server: int = 3) -> Optional[int]:
        raw = self.raw_data.get("endAt")
        if not raw:
            return None
        val = None
        if isinstance(raw, list) and 0 <= server < len(raw):
            val = raw[server]
        elif isinstance(raw, dict):
            val = raw.get(str(server))
        return int(val) if val else None

    def is_available_on_server(self, server: int) -> bool:
        """检查活动是否在指定服务器上可用"""
        return self.get_start_time(server) is not None

    def get_available_servers(self) -> List[int]:
        """获取该活动可用的所有服务器列表"""
        return [
            s
            for s in [SERVER_JP, SERVER_EN, SERVER_TW, SERVER_CN, SERVER_KR]
            if self.is_available_on_server(s)
        ]

    @property
    def event_type(self) -> str:
        etype = self.raw_data.get("eventType")
        return etype if isinstance(etype, str) else str(etype)

    @property
    def event_type_cn(self) -> str:
        """获取活动类型的中文名称"""
        type_map = {
            "story": "一般",
            "challenge": "挑战",
            "versus": "VS Live",
            "live_try": "Live Try",
            "mission_live": "任务",
            "festival": "团队",
            "medley": "协力",
        }
        return type_map.get(self.event_type, self.event_type)

    @property
    def event_type_icon(self) -> str:
        """获取活动类型对应的图标URL"""
        # 活动类型图标 (bestdori 资源)
        icon_map = {
            "story": "https://bestdori.com/res/icon/event_story.svg",
            "challenge": "https://bestdori.com/res/icon/event_challenge.svg",
            "versus": "https://bestdori.com/res/icon/event_versus.svg",
            "live_try": "https://bestdori.com/res/icon/event_livetry.svg",
            "mission_live": "https://bestdori.com/res/icon/event_mission.svg",
            "festival": "https://bestdori.com/res/icon/event_festival.svg",
            "medley": "https://bestdori.com/res/icon/event_medley.svg",
        }
        return icon_map.get(self.event_type, "")

    @property
    def bonus_attributes(self) -> List[str]:
        attrs = self.raw_data.get("attributes", [])
        return [a.get("attribute") for a in attrs if isinstance(a, dict)]

    @property
    def bonus_characters(self) -> List[int]:
        chars = self.raw_data.get("characters", [])
        return [c.get("characterId") for c in chars if isinstance(c, dict)]

    def get_formatted_time(self, is_start: bool = True, server: int = 3) -> str:
        raw_key = "startAt" if is_start else "endAt"
        ts = self.get_server_content(self.raw_data.get(raw_key), server)
        if not ts:
            return "未知时间"
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")

    @property
    def banner_url(self) -> str:
        asset_name = self.raw_data.get("assetBundleName")
        if not asset_name:
            return ""
        return (
            f"https://bestdori.com/assets/cn/event/{asset_name}/images_rip/banner.png"
        )

    def get_logo_url(self, server: int = 3) -> str:
        """获取活动logo图片URL

        Args:
            server: 服务器ID (0=jp, 1=en, 2=tw, 3=cn, 4=kr)

        Returns:
            活动logo的URL
        """
        asset_name = self.raw_data.get("assetBundleName")
        if not asset_name:
            return ""

        # 服务器代码映射
        server_map = {0: "jp", 1: "en", 2: "tw", 3: "cn", 4: "kr"}
        server_code = server_map.get(server, "cn")

        return f"https://bestdori.com/assets/{server_code}/event/{asset_name}/images_rip/logo.png"


class Card(BaseModel):
    def __init__(self, card_id: int, data: Dict[str, Any]):
        super().__init__(data)
        self.card_id = card_id

    @property
    def character_id(self) -> int:
        return self.raw_data.get("characterId", 0)

    @property
    def title(self) -> str:
        return self.get_server_content(self.raw_data.get("prefix")) or ""

    @property
    def rarity(self) -> int:
        return self.raw_data.get("rarity", 1)

    @property
    def attribute(self) -> str:
        return self.raw_data.get("attribute", "Unknown")

    @property
    def resource_set_name(self) -> Optional[str]:
        return self.raw_data.get("resourceSetName")

    @property
    def card_type(self) -> str:
        """卡面类型：permanent(常驻), limited(期间限定), dreamfes(梦限), birthday(生日限定)等"""
        return self.raw_data.get("type", "permanent")

    def get_released_at(self, server: int = 3) -> Optional[int]:
        raw = self.raw_data.get("releasedAt")
        if isinstance(raw, list) and 0 <= server < len(raw):
            return int(raw[server]) if raw[server] else None
        elif isinstance(raw, dict):
            return int(raw.get(str(server)) or 0) or None
        return None

    def get_card_icon_url(self, type: str = "thumb", server: str = None) -> str:
        """
        获取卡面图片 URL
        :param type: 'thumb' (缩略图), 'rip_normal' (特训前大图), 'rip_trained' (特训后大图)
        :param server: 服务器代码 ('jp', 'cn', 'en', 'tw', 'kr')，None 时自动判断
        """
        res_name = self.resource_set_name
        if not res_name:
            return ""

        # 判断服务器前缀
        if server is None:
            # CN 专有卡片 (ID >= 10000) 使用 cn 目录
            # 其他卡片默认使用 jp 目录
            server = "cn" if self.card_id >= 10000 else "jp"

        # 特训后大图
        if type == "rip_trained":
            return f"https://bestdori.com/assets/{server}/characters/resourceset/{res_name}_rip/card_after_training.png"

        # 特训前大图
        if type == "rip_normal":
            return f"https://bestdori.com/assets/{server}/characters/resourceset/{res_name}_rip/card_normal.png"

        # 特训前缩略图 (CN 特殊规则)
        if type == "thumb":
            # 缩略图分组规则: card_id // 50
            group_id = self.card_id // 50
            folder_name = f"card{group_id:05d}_rip"
            return f"https://bestdori.com/assets/cn/thumb/chara/{folder_name}/{res_name}_normal.png"

        return ""

    def get_thumb_url(self, trained: bool = True) -> str:
        """
        获取卡面缩略图 URL
        :param trained: True 为特训后，False 为特训前
        注意：1-2星卡没有特训后图，自动返回特训前

        URL格式: https://bestdori.com/assets/cn/thumb/chara/card{group}_rip/{res_name}_{suffix}.png
        分组规则: group = card_id // 50，目录名格式为 card00000_rip
        """
        res_name = self.resource_set_name
        if not res_name:
            return ""

        # 1-2星卡没有特训后，强制使用特训前
        if self.rarity <= 2:
            trained = False

        suffix = "after_training" if trained else "normal"

        # 计算资源分组
        group_id = self.card_id // 50
        folder_name = f"card{group_id:05d}_rip"

        return f"https://bestdori.com/assets/cn/thumb/chara/{folder_name}/{res_name}_{suffix}.png"

    def get_rip_frame_url(self) -> str:
        """
        获取 rip 大图用的外框 URL (frame-X 系列)
        用于：卡面大图展示、活动综合卡面展示、最新卡面等
        """
        if self.rarity == 1:
            return (
                f"https://bestdori.com/res/image/frame-1-{self.attribute.lower()}.png"
            )
        else:
            return f"https://bestdori.com/res/image/frame-{self.rarity}.png"

    def get_thumb_frame_url(self) -> str:
        """
        获取缩略图用的外框 URL (card-X 系列)
        用于：卡面列表、卡池列表、筹卡器等
        """
        if self.rarity == 1:
            return f"https://bestdori.com/res/image/card-1-{self.attribute.lower()}.png"
        else:
            return f"https://bestdori.com/res/image/card-{self.rarity}.png"

    def get_frame_url(self, is_rip: bool = True) -> str:
        """
        获取卡面外框 URL (兼容旧代码)
        is_rip=True (大图): frame-X 系列
        is_rip=False (缩略图): card-X 系列
        """
        return self.get_rip_frame_url() if is_rip else self.get_thumb_frame_url()

    def get_star_icon_url(self, trained: bool = True) -> str:
        """获取星级图标 URL

        Args:
            trained: True 返回觉醒(金)星 star_trained.png, False 返回普通(白)星 star.png
        """
        if trained:
            return "https://bestdori.com/res/icon/star_trained.png"
        else:
            return "https://bestdori.com/res/icon/star.png"


class Gacha(BaseModel):
    def __init__(self, gacha_id: int, data: Dict[str, Any]):
        super().__init__(data)
        self.gacha_id = gacha_id

    @property
    def name(self) -> str:
        return (
            self.get_server_content(self.raw_data.get("gachaName"))
            or f"Gacha {self.gacha_id}"
        )

    @property
    def new_card_ids(self) -> List[int]:
        """获取该卡池的新卡ID列表"""
        new_cards = self.raw_data.get("newCards", [])
        return [int(cid) for cid in new_cards] if new_cards else []

    def get_gacha_type_by_cards(self, cards_data: Dict[str, Any]) -> str:
        """
        通过卡池内五星卡的类型判断卡池类型
        优先级：梦限 > 生日限定 > 期间限定 > 常驻 > 特殊
        """
        if not self.new_card_ids:
            # 如果没有新卡信息，回退到原始type字段
            gtype = self.raw_data.get("type", "normal")
            type_map = {
                "normal": "普通招募",
                "limited": "期间限定",
                "permanent": "普通招募",
                "dreamfes": "梦限招募",
                "special": "特殊招募",
                "birthday": "生日限定",
            }
            return type_map.get(str(gtype).lower(), str(gtype))

        # 查找五星卡的类型
        five_star_types = []
        for card_id in self.new_card_ids:
            card_data = cards_data.get(str(card_id))
            if card_data and card_data.get("rarity") == 5:
                card_type = card_data.get("type", "permanent")
                five_star_types.append(card_type)

        # 根据五星卡类型判断卡池类型
        if "dreamfes" in five_star_types:
            return "梦限招募"
        elif "birthday" in five_star_types:
            return "生日限定"
        elif "limited" in five_star_types:
            return "期间限定"
        elif "permanent" in five_star_types:
            return "普通招募"
        else:
            return "特殊招募"

    @property
    def gacha_type(self) -> str:
        """招募类型（旧方法，保留向后兼容）"""
        gtype = self.raw_data.get("gachaType", "normal")
        type_map = {
            "normal": "常驻",
            "limited": "期间限定",
            "permanent": "常驻",
            "dreamfes": "梦限",
            "special": "特殊",
        }
        return type_map.get(str(gtype).lower(), str(gtype))

    @property
    def banner_url(self) -> str:
        # 优先使用 bannerAssetBundleName 字段
        # 注意：国服(cn)通常没有招募封面资源，使用日服(jp)资源
        banner_asset = self.raw_data.get("bannerAssetBundleName", "")
        if banner_asset:
            return f"https://bestdori.com/assets/jp/homebanner_rip/{banner_asset}.png"
        # 降级：使用招募ID构建URL
        return f"https://bestdori.com/assets/jp/homebanner_rip/banner_gacha{self.gacha_id}.png"

    def get_formatted_time(self, is_start: bool = True, server: int = 3) -> str:
        raw_key = "publishedAt" if is_start else "closedAt"
        ts = self.get_server_content(self.raw_data.get(raw_key), server)
        if not ts:
            return "未知时间"
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")

    def get_start_time(self, server: int = 3) -> Optional[int]:
        raw = self.raw_data.get("publishedAt")
        if isinstance(raw, list) and 0 <= server < len(raw):
            return int(raw[server]) if raw[server] else None
        elif isinstance(raw, dict):
            return int(raw.get(str(server)) or 0) or None
        return None

    def get_end_time(self, server: int = 3) -> Optional[int]:
        raw = self.raw_data.get("closedAt")
        if isinstance(raw, list) and 0 <= server < len(raw):
            return int(raw[server]) if raw[server] else None
        elif isinstance(raw, dict):
            return int(raw.get(str(server)) or 0) or None
        return None
