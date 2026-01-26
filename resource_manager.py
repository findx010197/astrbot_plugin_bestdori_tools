import aiohttp
import logging
from pathlib import Path

try:
    from .birthday_service import BirthdayService
except ImportError:
    from birthday_service import BirthdayService

logger = logging.getLogger("astrbot_plugin_bestdori_tools")

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
CHARACTERS = range(1, 46)


class ResourceManager:
    def __init__(self, data_dir: str, birthday_service: BirthdayService):
        self.data_dir = Path(data_dir)
        self.assets_dir = self.data_dir / "assets"
        self.birthday_service = birthday_service

        # 确保目录存在
        for subdir in ["bands", "attributes", "stars", "chibi"]:
            (self.assets_dir / subdir).mkdir(parents=True, exist_ok=True)

    async def _download_file(self, url: str, path: Path) -> bool:
        """
        下载文件的私有方法

        Args:
            url: 下载URL
            path: 保存路径

        Returns:
            是否下载成功
        """
        if path.exists() and path.stat().st_size > 0:
            return True  # 文件已存在且不为空

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return True
                    else:
                        print(f"下载失败 {url}: HTTP {resp.status}")
        except Exception as e:
            print(f"下载异常 {url}: {e}")

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
        下载基础素材（属性图标、星级图标等）

        Args:
            check_existing: 是否检查已存在的文件，跳过下载
        """
        try:
            print("📥 下载基础素材...")

            # 创建目录
            (self.assets_dir / "attributes").mkdir(parents=True, exist_ok=True)
            (self.assets_dir / "stars").mkdir(parents=True, exist_ok=True)
            (self.assets_dir / "chibi").mkdir(parents=True, exist_ok=True)
            (self.assets_dir / "bands").mkdir(parents=True, exist_ok=True)

            # 下载属性图标
            attributes = ["happy", "cool", "pure", "powerful"]
            for attr in attributes:
                file_path = self.assets_dir / "attributes" / f"{attr}.svg"
                if check_existing and file_path.exists():
                    continue  # 跳过已存在的文件

                url = f"https://bestdori.com/res/icon/{attr}.svg"
                await self._download_file(url, file_path)

            # 下载星级图标
            star_files = [
                ("star.png", "https://bestdori.com/res/icon/star.png"),
                ("star_trained.png", "https://bestdori.com/res/icon/star_trained.png"),
            ]
            for filename, url in star_files:
                file_path = self.assets_dir / "stars" / filename
                if check_existing and file_path.exists():
                    continue  # 跳过已存在的文件

                await self._download_file(url, file_path)

            # 下载乐队图标
            for band_id, svg_name in BAND_ICON_URL_MAP.items():
                file_path = self.assets_dir / "bands" / f"band_{band_id}.svg"
                if check_existing and file_path.exists():
                    continue  # 跳过已存在的文件

                url = f"https://bestdori.com/res/icon/{svg_name}"
                await self._download_file(url, file_path)

            # 下载常用角色小人（可选）
            common_chars = [1, 21, 39, 16, 27]  # 几个主要角色
            for char_id in common_chars:
                file_path = self.assets_dir / "chibi" / f"chibi_{char_id}.png"
                if check_existing and file_path.exists():
                    continue  # 跳过已存在的文件

                url = f"https://bestdori.com/res/icon/chara_icon_{char_id}.png"
                await self._download_file(url, file_path)

            print("✅ 基础素材下载完成")
            return True

        except Exception as e:
            print(f"❌ 基础素材下载失败: {e}")
            return False

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
            "chibi": {},  # 动态检查角色小人
            "bands": {},  # 动态检查乐队图标
        }

        # 检查属性图标
        attr_dir = self.assets_dir / "attributes"
        for attr_file in basic_assets["attributes"]:
            basic_assets["attributes"][attr_file] = (attr_dir / attr_file).exists()

        # 检查星级图标
        star_dir = self.assets_dir / "stars"
        for star_file in basic_assets["stars"]:
            basic_assets["stars"][star_file] = (star_dir / star_file).exists()

        # 检查小人图标（检查常见角色）
        chibi_dir = self.assets_dir / "chibi"
        common_chars = [1, 21, 39, 16, 27]  # Kasumi, Yukina, Soyo等常见角色
        for char_id in common_chars:
            chibi_file = f"chibi_{char_id}.png"
            basic_assets["chibi"][chibi_file] = (chibi_dir / chibi_file).exists()

        # 检查乐队图标
        band_dir = self.assets_dir / "bands"
        for band_id in BAND_ICON_URL_MAP:
            band_file = f"band_{band_id}.svg"
            basic_assets["bands"][band_file] = (band_dir / band_file).exists()

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

    async def first_run_check(self):
        """
        首次运行时的资源检查
        如果是第一次运行或资源不完整，自动下载
        """
        try:
            print("🔍 执行首次运行检查...")

            # 检查是否为首次运行
            flag_file = self.assets_dir / ".initialized"
            is_first_run = not flag_file.exists()

            if is_first_run:
                print("📦 检测到首次运行，正在初始化资源...")
                await self.download_all_resources()

                # 创建初始化标记文件
                flag_file.touch()
                print("✅ 插件初始化完成")
            else:
                # 非首次运行，仅检查关键资源
                print("🔍 检查关键资源...")
                integrity_report = await self.check_resource_integrity()

                # 如果缺失关键资源，自动补充
                if (
                    integrity_report["missing_basic"]
                    or integrity_report["missing_birthday"]
                ):
                    print("⚠️ 检测到缺失资源，正在自动补充...")
                    await self.download_missing_resources(integrity_report)
                else:
                    print("✅ 资源完整，无需下载")

        except Exception as e:
            print(f"❌ 首次运行检查失败: {e}")

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
