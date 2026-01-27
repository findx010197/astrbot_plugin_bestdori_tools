import aiohttp
import logging
import base64
from pathlib import Path

try:
    from .birthday_service import BirthdayService
except ImportError:
    from birthday_service import BirthdayService

logger = logging.getLogger("astrbot_plugin_bestdori_tools")

# 基础素材 URL 基地址
BESTDORI_ICON_BASE = "https://bestdori.com/res/icon"
BESTDORI_IMAGE_BASE = "https://bestdori.com/res/image"
BESTDORI_ASSETS_BASE = "https://bestdori.com/assets"

# 资源定义
BAND_ICON_URL_MAP = {
    1: "band_1.svg",
    2: "band_2.svg",
    3: "band_4.svg",
    4: "band_5.svg",
    5: "band_3.svg",
    18: "band_18.svg",
    21: "band_21.svg",
    22: "band_45.svg",
    23: "band_45.svg",
}
ATTRIBUTES = ["powerful", "cool", "pure", "happy"]
# 所有角色 ID (1-45)
ALL_CHARACTERS = list(range(1, 46))


class ResourceManager:
    def __init__(self, data_dir: str, birthday_service: BirthdayService):
        self.data_dir = Path(data_dir)
        self.assets_dir = self.data_dir / "assets"
        self.birthday_service = birthday_service

        # 确保目录存在
        for subdir in [
            "bands",
            "attributes",
            "stars",
            "chibi",
            "frames",
            "costumes",
            "card_thumbs",
        ]:
            (self.assets_dir / subdir).mkdir(parents=True, exist_ok=True)

    async def _download_file(self, url: str, path: Path, force: bool = False) -> bool:
        """
        下载文件的私有方法

        Args:
            url: 下载URL
            path: 保存路径
            force: 是否强制重新下载

        Returns:
            是否下载成功
        """
        if not force and path.exists() and path.stat().st_size > 0:
            logger.debug(f"文件已存在，跳过下载: {path}")
            return True  # 文件已存在且不为空

        try:
            logger.info(f"正在下载: {url} -> {path}")
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        content = await resp.read()
                        with open(path, "wb") as f:
                            f.write(content)
                        logger.info(f"下载成功: {path.name} ({len(content)} bytes)")
                        return True
                    else:
                        logger.warning(f"下载失败 {url}: HTTP {resp.status}")
        except aiohttp.ClientError as e:
            logger.error(f"网络错误 {url}: {e}")
        except Exception as e:
            logger.error(f"下载异常 {url}: {e}")

        return False

    async def download_file(self, session, url, path):
        """保持向后兼容的下载方法"""
        if path.exists() and path.stat().st_size > 0:
            return True
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return True
        except Exception as e:
            logger.error(f"下载失败 {url}: {e}")
        return False

    async def download_basic_assets(self, check_existing: bool = False):
        """
        下载基础素材（属性图标、星级图标、乐队图标、所有角色 chibi、边框等）

        Args:
            check_existing: 是否检查已存在的文件，跳过下载
        """
        try:
            print("=" * 50)
            print("📥 开始下载基础素材...")
            print("=" * 50)

            # 创建目录
            for subdir in ["attributes", "stars", "chibi", "bands", "frames"]:
                (self.assets_dir / subdir).mkdir(parents=True, exist_ok=True)

            success_count = 0
            fail_count = 0
            skip_count = 0

            # 下载属性图标
            print("\n🎨 [1/5] 下载属性图标...")
            attributes = ["happy", "cool", "pure", "powerful"]
            for attr in attributes:
                file_path = self.assets_dir / "attributes" / f"{attr}.svg"
                if (
                    check_existing
                    and file_path.exists()
                    and file_path.stat().st_size > 0
                ):
                    skip_count += 1
                    continue

                url = f"{BESTDORI_ICON_BASE}/{attr}.svg"
                if await self._download_file(url, file_path):
                    success_count += 1
                    print(f"   ✅ {attr}.svg")
                else:
                    fail_count += 1
                    print(f"   ❌ {attr}.svg 下载失败")
            print(f"   属性图标: 已有 {skip_count} 个, 新下载 {success_count} 个")

            # 下载星级图标
            print("\n⭐ [2/5] 下载星级图标...")
            star_success = 0
            star_skip = 0
            star_files = [
                ("star.png", f"{BESTDORI_ICON_BASE}/star.png"),
                ("star_trained.png", f"{BESTDORI_ICON_BASE}/star_trained.png"),
            ]
            for filename, url in star_files:
                file_path = self.assets_dir / "stars" / filename
                if (
                    check_existing
                    and file_path.exists()
                    and file_path.stat().st_size > 0
                ):
                    star_skip += 1
                    skip_count += 1
                    continue

                if await self._download_file(url, file_path):
                    star_success += 1
                    success_count += 1
                    print(f"   ✅ {filename}")
                else:
                    fail_count += 1
                    print(f"   ❌ {filename} 下载失败")
            print(f"   星级图标: 已有 {star_skip} 个, 新下载 {star_success} 个")

            # 下载乐队图标
            print("\n🎸 [3/5] 下载乐队图标...")
            band_success = 0
            band_skip = 0
            for band_id, svg_name in BAND_ICON_URL_MAP.items():
                file_path = self.assets_dir / "bands" / f"band_{band_id}.svg"
                if (
                    check_existing
                    and file_path.exists()
                    and file_path.stat().st_size > 0
                ):
                    band_skip += 1
                    skip_count += 1
                    continue

                url = f"{BESTDORI_ICON_BASE}/{svg_name}"
                if await self._download_file(url, file_path):
                    band_success += 1
                    success_count += 1
                else:
                    fail_count += 1
            print(f"   乐队图标: 已有 {band_skip} 个, 新下载 {band_success} 个")

            # ========== 下载所有角色 chibi 图标 (45个角色) ==========
            print("\n👤 [4/5] 下载角色 Chibi 图标 (45个角色)...")
            chibi_success = 0
            chibi_skip = 0
            for char_id in ALL_CHARACTERS:
                file_path = self.assets_dir / "chibi" / f"chibi_{char_id}.png"
                if (
                    check_existing
                    and file_path.exists()
                    and file_path.stat().st_size > 0
                ):
                    chibi_skip += 1
                    skip_count += 1
                    continue

                url = f"{BESTDORI_ICON_BASE}/chara_icon_{char_id}.png"
                if await self._download_file(url, file_path):
                    chibi_success += 1
                    success_count += 1
                else:
                    fail_count += 1
            print(f"   Chibi 图标: 已有 {chibi_skip} 个, 新下载 {chibi_success} 个")

            # ========== 下载卡面边框 (frame 和 card 系列) ==========
            print("\n🖼️ [5/5] 下载卡面边框...")
            frame_success = 0
            frame_skip = 0

            # frame-X 系列 (用于大图)
            frame_files = [
                ("frame-2.png", f"{BESTDORI_IMAGE_BASE}/frame-2.png"),
                ("frame-3.png", f"{BESTDORI_IMAGE_BASE}/frame-3.png"),
                ("frame-4.png", f"{BESTDORI_IMAGE_BASE}/frame-4.png"),
            ]
            # 1星边框带属性
            for attr in attributes:
                frame_files.append(
                    (f"frame-1-{attr}.png", f"{BESTDORI_IMAGE_BASE}/frame-1-{attr}.png")
                )

            # card-X 系列 (用于缩略图)
            card_frame_files = [
                ("card-2.png", f"{BESTDORI_IMAGE_BASE}/card-2.png"),
                ("card-3.png", f"{BESTDORI_IMAGE_BASE}/card-3.png"),
                ("card-4.png", f"{BESTDORI_IMAGE_BASE}/card-4.png"),
            ]
            for attr in attributes:
                card_frame_files.append(
                    (f"card-1-{attr}.png", f"{BESTDORI_IMAGE_BASE}/card-1-{attr}.png")
                )

            all_frame_files = frame_files + card_frame_files
            for filename, url in all_frame_files:
                file_path = self.assets_dir / "frames" / filename
                if (
                    check_existing
                    and file_path.exists()
                    and file_path.stat().st_size > 0
                ):
                    frame_skip += 1
                    skip_count += 1
                    continue

                if await self._download_file(url, file_path):
                    frame_success += 1
                    success_count += 1
                else:
                    fail_count += 1
            print(f"   边框图标: 已有 {frame_skip} 个, 新下载 {frame_success} 个")

            # 打印汇总
            print("\n" + "=" * 50)
            print("📊 基础素材下载汇总:")
            print(f"   已存在: {skip_count} 个")
            print(f"   新下载: {success_count} 个")
            print(f"   失败:   {fail_count} 个")

            if fail_count == 0:
                print("✅ 基础素材全部就绪!")
            else:
                print(f"⚠️ 有 {fail_count} 个素材下载失败，请检查网络")
            print("=" * 50)

            return fail_count == 0

        except Exception as e:
            print(f"❌ 基础素材下载失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def download_all_costumes(self, costumes_data: dict = None) -> bool:
        """
        下载所有 Live2D 服装小人

        Args:
            costumes_data: 服装数据字典 (从 client.get_costumes() 获取)

        Returns:
            是否全部成功
        """
        if not costumes_data:
            print("⚠️ 没有服装数据，跳过服装下载")
            return True

        print(f"\n👗 开始下载 Live2D 服装小人 (共 {len(costumes_data)} 个)...")

        costume_dir = self.assets_dir / "costumes"
        costume_dir.mkdir(parents=True, exist_ok=True)

        success_count = 0
        fail_count = 0
        skip_count = 0

        for costume_id_str, costume_info in costumes_data.items():
            try:
                costume_id = int(costume_id_str)
                abn = costume_info.get("assetBundleName")
                if not abn:
                    skip_count += 1
                    continue

                file_path = costume_dir / f"costume_{costume_id}.png"
                if file_path.exists() and file_path.stat().st_size > 0:
                    success_count += 1
                    continue

                # 计算服装分组
                group = costume_id // 50

                # 尝试多个服务器
                downloaded = False
                for server in ["cn", "jp", "en", "tw", "kr"]:
                    url = f"{BESTDORI_ASSETS_BASE}/{server}/thumb/costume/group{group}_rip/{abn}.png"
                    if await self._download_file(url, file_path):
                        success_count += 1
                        downloaded = True
                        break

                if not downloaded:
                    fail_count += 1

            except Exception as e:
                logger.warning(f"下载服装 {costume_id_str} 失败: {e}")
                fail_count += 1

        print(
            f"   服装下载完成: 已有/成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}"
        )
        return fail_count == 0

    async def download_card_thumbs(self, cards_data: dict = None) -> bool:
        """
        下载所有卡面缩略图

        Args:
            cards_data: 卡面数据字典 (从 client.get_cards() 获取)

        Returns:
            是否全部成功
        """
        if not cards_data:
            print("⚠️ 没有卡面数据，跳过卡面缩略图下载")
            return True

        print(f"\n🃏 开始下载卡面缩略图 (共 {len(cards_data)} 张)...")

        thumb_dir = self.assets_dir / "card_thumbs"
        thumb_dir.mkdir(parents=True, exist_ok=True)

        success_count = 0
        fail_count = 0
        skip_count = 0

        for card_id_str, card_info in cards_data.items():
            try:
                card_id = int(card_id_str)
                res_name = card_info.get("resourceSetName")
                if not res_name:
                    skip_count += 1
                    continue

                # 计算资源分组
                group_id = card_id // 50
                folder_name = f"card{group_id:05d}_rip"

                # 下载特训后缩略图
                file_path = thumb_dir / f"card_{card_id}_trained.png"
                if not (file_path.exists() and file_path.stat().st_size > 0):
                    # 尝试多个服务器
                    downloaded = False
                    for server in ["cn", "jp", "en", "tw", "kr"]:
                        url = f"{BESTDORI_ASSETS_BASE}/{server}/thumb/chara/{folder_name}/{res_name}_after_training.png"
                        if await self._download_file(url, file_path):
                            downloaded = True
                            break

                    if downloaded:
                        success_count += 1
                    else:
                        # 1-2星卡没有特训后，尝试特训前
                        rarity = card_info.get("rarity", 1)
                        if rarity <= 2:
                            for server in ["cn", "jp", "en", "tw", "kr"]:
                                url = f"{BESTDORI_ASSETS_BASE}/{server}/thumb/chara/{folder_name}/{res_name}_normal.png"
                                if await self._download_file(url, file_path):
                                    downloaded = True
                                    break

                        if not downloaded:
                            fail_count += 1
                else:
                    success_count += 1

            except Exception as e:
                logger.warning(f"下载卡面 {card_id_str} 缩略图失败: {e}")
                fail_count += 1

        print(
            f"   卡面缩略图下载完成: 已有/成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}"
        )
        return fail_count == 0

    def get_local_chibi(self, char_id: int) -> str:
        """
        获取本地 chibi 图标的 base64 data URI

        Args:
            char_id: 角色 ID

        Returns:
            base64 data URI 或 None
        """
        file_path = self.assets_dir / "chibi" / f"chibi_{char_id}.png"
        if file_path.exists() and file_path.stat().st_size > 0:
            try:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/png;base64,{data}"
            except Exception as e:
                logger.warning(f"读取本地 chibi_{char_id}.png 失败: {e}")
        return None

    def get_local_frame(self, frame_name: str) -> str:
        """
        获取本地边框图片的 base64 data URI

        Args:
            frame_name: 边框文件名 (如 "frame-4.png" 或 "card-3.png")

        Returns:
            base64 data URI 或 None
        """
        file_path = self.assets_dir / "frames" / frame_name
        if file_path.exists() and file_path.stat().st_size > 0:
            try:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/png;base64,{data}"
            except Exception as e:
                logger.warning(f"读取本地边框 {frame_name} 失败: {e}")
        return None

    def get_local_costume(self, costume_id: int) -> str:
        """
        获取本地服装小人的 base64 data URI

        Args:
            costume_id: 服装 ID

        Returns:
            base64 data URI 或 None
        """
        file_path = self.assets_dir / "costumes" / f"costume_{costume_id}.png"
        if file_path.exists() and file_path.stat().st_size > 0:
            try:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/png;base64,{data}"
            except Exception as e:
                logger.warning(f"读取本地服装 costume_{costume_id}.png 失败: {e}")
        return None

    def get_local_card_thumb(self, card_id: int, trained: bool = True) -> str:
        """
        获取本地卡面缩略图的 base64 data URI

        Args:
            card_id: 卡面 ID
            trained: 是否为特训后

        Returns:
            base64 data URI 或 None
        """
        suffix = "trained" if trained else "normal"
        file_path = self.assets_dir / "card_thumbs" / f"card_{card_id}_{suffix}.png"
        if file_path.exists() and file_path.stat().st_size > 0:
            try:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/png;base64,{data}"
            except Exception as e:
                logger.warning(
                    f"读取本地卡面缩略图 card_{card_id}_{suffix}.png 失败: {e}"
                )
        return None

    def get_local_attribute(self, attr: str) -> str:
        """
        获取本地属性图标的 base64 data URI

        Args:
            attr: 属性名 (happy, cool, pure, powerful)

        Returns:
            base64 data URI 或 None
        """
        file_path = self.assets_dir / "attributes" / f"{attr.lower()}.svg"
        if file_path.exists() and file_path.stat().st_size > 0:
            try:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/svg+xml;base64,{data}"
            except Exception as e:
                logger.warning(f"读取本地属性图标 {attr}.svg 失败: {e}")
        return None

    def get_local_band(self, band_id: int) -> str:
        """
        获取本地乐队图标的 base64 data URI

        Args:
            band_id: 乐队 ID

        Returns:
            base64 data URI 或 None
        """
        file_path = self.assets_dir / "bands" / f"band_{band_id}.svg"
        if file_path.exists() and file_path.stat().st_size > 0:
            try:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                return f"data:image/svg+xml;base64,{data}"
            except Exception as e:
                logger.warning(f"读取本地乐队图标 band_{band_id}.svg 失败: {e}")
        return None

    async def check_resource_integrity(self) -> dict:
        """
        检查资源完整性

        Returns:
            资源检查结果字典
        """
        print("🔍 检查资源完整性...")
        integrity_report = {
            "basic_assets": self._check_basic_assets(),
            "birthday_resources": await self._check_birthday_resources(),
            "missing_basic": [],
            "missing_birthday": [],
        }

        # 统计缺失的基础素材
        basic_assets = integrity_report["basic_assets"]
        for category, assets in basic_assets.items():
            for asset_name, exists in assets.items():
                if not exists:
                    integrity_report["missing_basic"].append(f"{category}/{asset_name}")

        # 统计缺失的生日资源
        birthday_resources = integrity_report["birthday_resources"]
        for char_id, resources in birthday_resources.items():
            if not resources["has_cards"] or not resources["has_voices"]:
                integrity_report["missing_birthday"].append(char_id)

        # 输出检查报告
        total_missing_basic = len(integrity_report["missing_basic"])
        total_missing_birthday = len(integrity_report["missing_birthday"])

        if total_missing_basic == 0 and total_missing_birthday == 0:
            print("✅ 所有资源完整，无需下载")
        else:
            print("📊 资源检查完成:")
            if total_missing_basic > 0:
                print(f"  - 缺失基础素材: {total_missing_basic} 个")
            if total_missing_birthday > 0:
                print(f"  - 缺失生日资源: {total_missing_birthday} 个角色")

        return integrity_report

    def _check_basic_assets(self) -> dict:
        """
        检查基础素材完整性

        Returns:
            基础素材检查结果
        """
        basic_assets = {
            "attributes": {
                "happy.svg": False,
                "cool.svg": False,
                "pure.svg": False,
                "powerful.svg": False,
            },
            "stars": {"star.png": False, "star_trained.png": False},
            "chibi": {},  # 动态检查所有角色小人
            "bands": {},  # 动态检查乐队图标
            "frames": {},  # 动态检查边框
        }

        # 检查属性图标
        attr_dir = self.assets_dir / "attributes"
        for attr_file in basic_assets["attributes"]:
            basic_assets["attributes"][attr_file] = (attr_dir / attr_file).exists()

        # 检查星级图标
        star_dir = self.assets_dir / "stars"
        for star_file in basic_assets["stars"]:
            basic_assets["stars"][star_file] = (star_dir / star_file).exists()

        # 检查所有角色小人图标 (45个角色)
        chibi_dir = self.assets_dir / "chibi"
        for char_id in ALL_CHARACTERS:
            chibi_file = f"chibi_{char_id}.png"
            basic_assets["chibi"][chibi_file] = (chibi_dir / chibi_file).exists()

        # 检查乐队图标
        band_dir = self.assets_dir / "bands"
        for band_id in BAND_ICON_URL_MAP:
            band_file = f"band_{band_id}.svg"
            basic_assets["bands"][band_file] = (band_dir / band_file).exists()

        # 检查边框
        frame_dir = self.assets_dir / "frames"
        frame_files = [
            "frame-2.png",
            "frame-3.png",
            "frame-4.png",
            "card-2.png",
            "card-3.png",
            "card-4.png",
        ]
        for attr in ATTRIBUTES:
            frame_files.extend([f"frame-1-{attr}.png", f"card-1-{attr}.png"])
        for frame_file in frame_files:
            basic_assets["frames"][frame_file] = (frame_dir / frame_file).exists()

        return basic_assets

    async def _check_birthday_resources(self) -> dict:
        """
        检查生日资源完整性

        Returns:
            生日资源检查结果
        """
        birthday_check = {}

        # 检查主要角色的生日资源
        main_characters = [1, 21, 39, 16, 27]  # 几个主要角色

        for char_id in main_characters:
            # 检查生日卡面
            card_dir = self.birthday_service.data_dir / "birthday_cards" / str(char_id)
            has_cards = card_dir.exists() and len(list(card_dir.glob("*.png"))) > 0

            # 检查生日语音
            voice_dir = (
                self.birthday_service.data_dir / "birthday_voices" / str(char_id)
            )
            has_voices = voice_dir.exists() and len(list(voice_dir.glob("*.wav"))) > 0

            birthday_check[str(char_id)] = {
                "has_cards": has_cards,
                "has_voices": has_voices,
                "card_count": len(list(card_dir.glob("*.png")))
                if card_dir.exists()
                else 0,
                "voice_count": len(list(voice_dir.glob("*.wav")))
                if voice_dir.exists()
                else 0,
            }

        return birthday_check

    async def download_missing_resources(self, integrity_report: dict = None) -> bool:
        """
        仅下载缺失的资源

        Args:
            integrity_report: 资源完整性检查报告，如果为None则先执行检查

        Returns:
            是否成功
        """
        if integrity_report is None:
            integrity_report = await self.check_resource_integrity()

        success = True

        # 下载缺失的基础素材
        if integrity_report["missing_basic"]:
            print(
                f"📥 下载缺失的基础素材 ({len(integrity_report['missing_basic'])} 个)..."
            )
            basic_success = await self.download_basic_assets(check_existing=True)
            success = success and basic_success

        # 下载缺失的生日资源
        if integrity_report["missing_birthday"]:
            print(
                f"📥 下载缺失的生日资源 ({len(integrity_report['missing_birthday'])} 个角色)..."
            )
            for char_id in integrity_report["missing_birthday"]:
                try:
                    birthday_result = (
                        await self.birthday_service.download_birthday_resources(
                            int(char_id)
                        )
                    )
                    # download_birthday_resources 返回字典，检查是否有卡片数据
                    birthday_success = bool(
                        birthday_result and birthday_result.get("cards")
                    )
                    success = success and birthday_success
                except Exception as e:
                    print(f"❌ 下载角色 {char_id} 的生日资源失败: {e}")
                    success = False

        if success:
            print("✅ 所有缺失资源下载完成")
        else:
            print("⚠️ 部分资源下载失败，请检查网络连接")

        return success

    async def first_run_check(self, client=None):
        """
        首次运行时的资源检查
        始终检查关键资源是否存在，缺失则下载

        Args:
            client: BestdoriClient 实例，用于获取卡面和服装数据
        """
        try:
            print("\n" + "=" * 60)
            print("🔍 Bestdori 插件资源完整性检查")
            print("=" * 60)

            # 直接检查基础素材是否存在（不依赖标记文件）
            basic_ok = self._quick_check_basic_assets()

            if not basic_ok:
                print("📦 检测到缺失基础素材，开始下载...")
                await self.download_basic_assets(check_existing=True)
            else:
                # 验证并报告已有资源
                self._report_existing_assets()

            # 如果提供了 client，下载卡面缩略图和服装
            if client:
                try:
                    # 检查是否需要下载卡面缩略图
                    thumb_dir = self.assets_dir / "card_thumbs"
                    existing_thumbs = (
                        len(list(thumb_dir.glob("*.png"))) if thumb_dir.exists() else 0
                    )

                    # 检查是否需要下载服装
                    costume_dir = self.assets_dir / "costumes"
                    existing_costumes = (
                        len(list(costume_dir.glob("*.png")))
                        if costume_dir.exists()
                        else 0
                    )

                    # 只在首次或资源很少时下载
                    if existing_thumbs < 100:
                        print("\n📥 开始下载卡面缩略图（首次运行可能需要几分钟）...")
                        cards_data = await client.get_cards()
                        if cards_data:
                            await self.download_card_thumbs(cards_data)
                    else:
                        print(f"✅ 卡面缩略图: 已有 {existing_thumbs} 张")

                    if existing_costumes < 50:
                        print(
                            "📥 开始下载 Live2D 服装小人（首次运行可能需要几分钟）..."
                        )
                        costumes_data = await client.get_costumes()
                        if costumes_data:
                            await self.download_all_costumes(costumes_data)
                    else:
                        print(f"✅ Live2D 服装: 已有 {existing_costumes} 个")

                except Exception as e:
                    print(f"⚠️ 下载扩展资源失败（不影响基本功能）: {e}")

            # 最终验证
            print("\n" + "-" * 60)
            print("📊 资源完整性最终验证:")
            self._verify_and_report_assets()
            print("-" * 60)
            print("✅ 资源检查完成!")
            print("=" * 60 + "\n")

        except Exception as e:
            print(f"❌ 资源检查失败: {e}")
            import traceback

            traceback.print_exc()

    def _report_existing_assets(self):
        """报告已存在的资源"""
        print("\n📦 已安装的基础素材:")

        # 属性图标
        attr_count = sum(
            1
            for attr in ATTRIBUTES
            if (self.assets_dir / "attributes" / f"{attr}.svg").exists()
        )
        print(f"   🎨 属性图标: {attr_count}/{len(ATTRIBUTES)}")

        # 星级图标
        star_count = sum(
            1
            for f in ["star.png", "star_trained.png"]
            if (self.assets_dir / "stars" / f).exists()
        )
        print(f"   ⭐ 星级图标: {star_count}/2")

        # 乐队图标
        band_count = sum(
            1
            for bid in BAND_ICON_URL_MAP
            if (self.assets_dir / "bands" / f"band_{bid}.svg").exists()
        )
        print(f"   🎸 乐队图标: {band_count}/{len(BAND_ICON_URL_MAP)}")

        # Chibi 图标
        chibi_count = sum(
            1
            for cid in ALL_CHARACTERS
            if (self.assets_dir / "chibi" / f"chibi_{cid}.png").exists()
        )
        print(f"   👤 Chibi 图标: {chibi_count}/{len(ALL_CHARACTERS)}")

        # 边框
        frame_dir = self.assets_dir / "frames"
        frame_count = len(list(frame_dir.glob("*.png"))) if frame_dir.exists() else 0
        print(f"   🖼️ 边框图标: {frame_count}")

    def _verify_and_report_assets(self):
        """验证并报告资源状态"""
        all_ok = True

        # 验证属性图标
        missing_attrs = [
            attr
            for attr in ATTRIBUTES
            if not (self.assets_dir / "attributes" / f"{attr}.svg").exists()
        ]
        if missing_attrs:
            print(f"   ❌ 缺失属性图标: {missing_attrs}")
            all_ok = False
        else:
            print("   ✅ 属性图标: 全部就绪 (4/4)")

        # 验证星级图标
        missing_stars = [
            f
            for f in ["star.png", "star_trained.png"]
            if not (self.assets_dir / "stars" / f).exists()
        ]
        if missing_stars:
            print(f"   ❌ 缺失星级图标: {missing_stars}")
            all_ok = False
        else:
            print("   ✅ 星级图标: 全部就绪 (2/2)")

        # 验证乐队图标
        missing_bands = [
            bid
            for bid in BAND_ICON_URL_MAP
            if not (self.assets_dir / "bands" / f"band_{bid}.svg").exists()
        ]
        if missing_bands:
            print(f"   ❌ 缺失乐队图标: {missing_bands}")
            all_ok = False
        else:
            print(
                f"   ✅ 乐队图标: 全部就绪 ({len(BAND_ICON_URL_MAP)}/{len(BAND_ICON_URL_MAP)})"
            )

        # 验证 Chibi 图标
        missing_chibis = [
            cid
            for cid in ALL_CHARACTERS
            if not (self.assets_dir / "chibi" / f"chibi_{cid}.png").exists()
        ]
        if missing_chibis:
            print(f"   ⚠️ 缺失 Chibi 图标: {len(missing_chibis)} 个")
            all_ok = False
        else:
            print("   ✅ Chibi 图标: 全部就绪 (45/45)")

        # 验证边框
        frame_dir = self.assets_dir / "frames"
        frame_count = len(list(frame_dir.glob("*.png"))) if frame_dir.exists() else 0
        if frame_count >= 14:  # 应该有 14 个边框 (3+4属性 + 3+4属性)
            print(f"   ✅ 边框图标: 全部就绪 ({frame_count})")
        else:
            print(f"   ⚠️ 边框图标: {frame_count}/14")
            all_ok = False

        # 卡面缩略图和服装
        thumb_dir = self.assets_dir / "card_thumbs"
        thumb_count = len(list(thumb_dir.glob("*.png"))) if thumb_dir.exists() else 0
        if thumb_count > 0:
            print(f"   📷 卡面缩略图: {thumb_count} 张")

        costume_dir = self.assets_dir / "costumes"
        costume_count = (
            len(list(costume_dir.glob("*.png"))) if costume_dir.exists() else 0
        )
        if costume_count > 0:
            print(f"   👗 Live2D 服装: {costume_count} 个")

        return all_ok

    def _quick_check_basic_assets(self) -> bool:
        """
        快速检查关键基础素材是否存在

        Returns:
            True 如果所有关键素材都存在
        """
        # 检查属性图标（必需）
        for attr in ATTRIBUTES:
            attr_file = self.assets_dir / "attributes" / f"{attr}.svg"
            if not attr_file.exists() or attr_file.stat().st_size == 0:
                logger.debug(f"缺失属性图标: {attr_file}")
                return False

        # 检查星级图标（必需）
        for star_file in ["star.png", "star_trained.png"]:
            star_path = self.assets_dir / "stars" / star_file
            if not star_path.exists() or star_path.stat().st_size == 0:
                logger.debug(f"缺失星级图标: {star_path}")
                return False

        # 检查所有角色 chibi（必需）
        chibi_dir = self.assets_dir / "chibi"
        for char_id in ALL_CHARACTERS:
            chibi_path = chibi_dir / f"chibi_{char_id}.png"
            if not chibi_path.exists() or chibi_path.stat().st_size == 0:
                logger.debug(f"缺失角色小人: chibi_{char_id}.png")
                return False

        # 检查乐队图标（必需）
        band_dir = self.assets_dir / "bands"
        for band_id in BAND_ICON_URL_MAP:
            band_path = band_dir / f"band_{band_id}.svg"
            if not band_path.exists() or band_path.stat().st_size == 0:
                logger.debug(f"缺失乐队图标: band_{band_id}.svg")
                return False

        return True

    async def ensure_basic_assets(self) -> bool:
        """
        确保基础素材存在，如果不存在则下载
        供其他模块调用以确保渲染前资源就绪

        Returns:
            True 如果素材可用
        """
        if self._quick_check_basic_assets():
            return True

        logger.info("⚠️ 基础素材不完整，正在下载...")
        return await self.download_basic_assets(check_existing=True)

    async def download_all_resources(self):
        """
        智能下载所有资源（仅下载缺失的资源）
        在后台静默执行
        """
        try:
            print("🔍 开始检查资源完整性...")

            # 检查资源完整性
            integrity_report = await self.check_resource_integrity()

            # 仅下载缺失的资源
            success = await self.download_missing_resources(integrity_report)

            if success:
                print("✅ 资源检查和下载完成！")
            else:
                print("⚠️ 部分资源下载失败，请稍后重试")

        except Exception as e:
            print(f"❌ 资源下载失败: {e}")
