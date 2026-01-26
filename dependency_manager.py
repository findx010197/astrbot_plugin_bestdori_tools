"""
依赖管理模块
负责检查和安装插件所需的Python依赖包和系统依赖（如字体）
"""

import subprocess
import sys
import importlib
from typing import List, Dict, Tuple
import os
import shutil


class DependencyManager:
    """依赖管理器"""

    def __init__(self):
        # 定义插件所需的依赖包
        self.required_packages = {
            "aiohttp": "aiohttp>=3.8.0",
            "jinja2": "Jinja2>=3.1.0",
            "html2image": "html2image>=2.0.0",
            "pillow": "Pillow>=9.0.0",
            "pydub": "pydub>=0.25.0",
            "colorsys": None,  # 标准库，无需安装
            "pathlib": None,  # 标准库，无需安装
        }

        # 可选依赖（用于音频处理等）
        self.optional_packages = {
            "ffmpeg-python": "ffmpeg-python>=0.2.0",
        }
        
        # 中文字体包（不同发行版的包名）
        self.font_packages = {
            "apt": ["fonts-noto-cjk", "fonts-wqy-microhei"],  # Debian/Ubuntu
            "apk": ["font-noto-cjk"],  # Alpine
            "yum": ["google-noto-sans-cjk-ttc-fonts", "wqy-microhei-fonts"],  # CentOS/RHEL
            "dnf": ["google-noto-sans-cjk-ttc-fonts", "wqy-microhei-fonts"],  # Fedora
        }

    def check_package_installed(self, package_name: str) -> bool:
        """
        检查指定包是否已安装

        Args:
            package_name: 包名

        Returns:
            是否已安装
        """
        try:
            importlib.import_module(package_name.replace("-", "_"))
            return True
        except ImportError:
            return False

    def get_missing_packages(self) -> Tuple[List[str], List[str]]:
        """
        获取缺失的依赖包

        Returns:
            (缺失的必需包, 缺失的可选包)
        """
        missing_required = []
        missing_optional = []

        # 检查必需包
        for package_name, install_spec in self.required_packages.items():
            if install_spec is None:  # 标准库，跳过
                continue

            if not self.check_package_installed(package_name):
                missing_required.append(install_spec or package_name)

        # 检查可选包
        for package_name, install_spec in self.optional_packages.items():
            if not self.check_package_installed(package_name):
                missing_optional.append(install_spec or package_name)

        return missing_required, missing_optional

    def install_package(self, package_spec: str) -> bool:
        """
        安装指定的包

        Args:
            package_spec: 包安装规范（如 "aiohttp>=3.8.0"）

        Returns:
            是否安装成功
        """
        try:
            print(f"正在安装依赖包: {package_spec}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_spec],
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
            )

            if result.returncode == 0:
                print(f"✅ 成功安装: {package_spec}")
                return True
            else:
                print(f"❌ 安装失败: {package_spec}")
                print(f"错误信息: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print(f"⏰ 安装超时: {package_spec}")
            return False
        except Exception as e:
            print(f"❌ 安装异常: {package_spec} - {e}")
            return False

    def auto_install_dependencies(self) -> Dict[str, bool]:
        """
        自动安装缺失的依赖

        Returns:
            安装结果字典 {package_name: success}
        """
        missing_required, missing_optional = self.get_missing_packages()
        results = {}

        if not missing_required and not missing_optional:
            print("✅ 所有依赖包都已安装")
            return {}

        print("🔍 检测到缺失的依赖包，开始自动安装...")

        # 安装必需包
        for package_spec in missing_required:
            package_name = package_spec.split(">=")[0].split("==")[0]
            success = self.install_package(package_spec)
            results[package_name] = success

            if not success:
                print(f"⚠️ 必需依赖 {package_name} 安装失败，插件可能无法正常工作")

        # 安装可选包（失败也不影响核心功能）
        for package_spec in missing_optional:
            package_name = package_spec.split(">=")[0].split("==")[0]
            success = self.install_package(package_spec)
            results[package_name] = success

            if not success:
                print(f"ℹ️ 可选依赖 {package_name} 安装失败，部分功能可能受限")

        return results

    def check_system_dependencies(self) -> Dict[str, bool]:
        """
        检查系统依赖（如Chrome浏览器、中文字体等）
        在 Linux 环境下会尝试自动安装缺失的依赖

        Returns:
            系统依赖检查结果
        """
        system_deps = {}

        # 1. 检查并安装 Chrome/Chromium（html2image需要）
        chrome_found = self._check_chrome_browser()
        
        if not chrome_found and sys.platform.startswith("linux"):
            # Linux 环境尝试自动安装 Chromium
            print("🔍 未检测到 Chromium 浏览器，尝试自动安装...")
            chrome_found = self._install_chromium()
        
        system_deps["chrome_or_chromium"] = chrome_found
        
        if not chrome_found:
            print("⚠️ 未检测到 Chrome/Chromium 浏览器，HTML 渲染功能将不可用")
            if sys.platform.startswith("linux"):
                print("💡 请手动安装: apt-get install -y chromium 或 chromium-browser")
            else:
                print("💡 请安装 Chrome 或 Edge 浏览器")

        # 2. 检查并安装中文字体（仅 Linux）
        if sys.platform.startswith("linux"):
            fonts_ok = self._check_and_install_chinese_fonts()
            system_deps["chinese_fonts"] = fonts_ok
        else:
            system_deps["chinese_fonts"] = True  # Windows/Mac 通常有中文字体

        return system_deps

    def _check_chrome_browser(self) -> bool:
        """检查是否安装了 Chrome/Chromium 浏览器"""
        if sys.platform.startswith("win"):
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    return True
            return False
        else:
            # Linux: 使用 which 命令检查
            for browser in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]:
                if shutil.which(browser):
                    return True
            return False

    def _install_chromium(self) -> bool:
        """
        自动安装 Chromium 浏览器（仅 Linux）
        
        Returns:
            是否安装成功
        """
        pm = self._detect_package_manager()
        if not pm:
            print("⚠️ 未检测到支持的包管理器，无法自动安装 Chromium")
            return False
        
        # 不同包管理器的 Chromium 包名
        chromium_packages = {
            "apt": ["chromium", "chromium-browser"],  # Debian/Ubuntu，不同版本包名不同
            "apk": ["chromium"],  # Alpine
            "yum": ["chromium"],  # CentOS
            "dnf": ["chromium"],  # Fedora
        }
        
        packages = chromium_packages.get(pm, ["chromium"])
        
        # 尝试安装（可能需要尝试不同的包名）
        for pkg in packages:
            print(f"📦 尝试安装 {pkg}...")
            if self._install_system_packages(pm, [pkg]):
                # 验证安装是否成功
                if self._check_chrome_browser():
                    print(f"✅ Chromium 安装成功")
                    return True
        
        print("❌ Chromium 安装失败")
        return False

    def _check_chinese_fonts_installed(self) -> bool:
        """
        检查系统是否安装了中文字体
        
        Returns:
            是否安装了中文字体
        """
        # 检查常见的中文字体目录
        font_dirs = [
            "/usr/share/fonts/opentype/noto",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/noto-cjk",
            "/usr/share/fonts/truetype/wqy",
            "/usr/share/fonts/truetype/droid",
            "/usr/share/fonts/google-noto-cjk",
        ]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir) and os.listdir(font_dir):
                return True
        
        # 使用 fc-list 检查中文字体
        try:
            result = subprocess.run(
                ["fc-list", ":lang=zh"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return False

    def _detect_package_manager(self) -> str:
        """
        检测系统使用的包管理器
        
        Returns:
            包管理器名称 (apt, apk, yum, dnf) 或空字符串
        """
        package_managers = ["apt-get", "apk", "dnf", "yum"]
        for pm in package_managers:
            if shutil.which(pm):
                # apt-get 返回 "apt"
                return "apt" if pm == "apt-get" else pm
        return ""

    def _check_and_install_chinese_fonts(self) -> bool:
        """
        检查并自动安装中文字体
        
        Returns:
            是否成功（已安装或安装成功）
        """
        # 检查是否已安装
        if self._check_chinese_fonts_installed():
            print("✅ 中文字体已安装")
            return True
        
        # 检查本地字体目录
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        local_font = os.path.join(plugin_dir, "data", "fonts", "NotoSansSC-Regular.otf")
        if os.path.exists(local_font):
            print("✅ 本地中文字体已存在")
            # 配置到系统
            self._configure_local_fonts(os.path.dirname(local_font))
            return True
        
        print("🔍 未检测到中文字体，尝试自动安装...")
        
        # 检测包管理器
        pm = self._detect_package_manager()
        if not pm:
            print("⚠️ 未检测到支持的包管理器，无法自动安装字体")
            print("💡 请手动安装中文字体:")
            print("   Debian/Ubuntu: apt-get install -y fonts-noto-cjk")
            print("   Alpine: apk add font-noto-cjk")
            print("   CentOS/Fedora: dnf install -y google-noto-sans-cjk-ttc-fonts")
            return False
        
        # 获取对应的字体包
        font_packages = self.font_packages.get(pm, [])
        if not font_packages:
            print(f"⚠️ 未知的包管理器 {pm}，无法自动安装字体")
            return False
        
        # 尝试安装字体
        success = self._install_system_packages(pm, font_packages)
        
        if success:
            # 刷新字体缓存
            self._refresh_font_cache()
            print("✅ 中文字体安装成功")
            return True
        else:
            print("⚠️ 中文字体安装失败，渲染的图片中文可能显示为方块")
            print("💡 请尝试手动安装或以 root 权限运行")
            return False

    def _install_system_packages(self, pm: str, packages: List[str]) -> bool:
        """
        使用系统包管理器安装软件包
        
        Args:
            pm: 包管理器名称
            packages: 要安装的包列表
            
        Returns:
            是否安装成功
        """
        try:
            # 构建安装命令
            if pm == "apt":
                # 先更新包列表
                print("📦 更新软件包列表...")
                update_cmd = ["apt-get", "update", "-qq"]
                subprocess.run(update_cmd, capture_output=True, timeout=120)
                
                install_cmd = ["apt-get", "install", "-y", "-qq"] + packages
            elif pm == "apk":
                install_cmd = ["apk", "add", "--no-cache"] + packages
            elif pm in ("yum", "dnf"):
                install_cmd = [pm, "install", "-y"] + packages
            else:
                return False
            
            print(f"📦 安装字体包: {' '.join(packages)}")
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                return True
            else:
                # 可能需要 root 权限，尝试使用 sudo
                if "Permission denied" in result.stderr or "permission" in result.stderr.lower():
                    print("🔐 需要 root 权限，尝试使用 sudo...")
                    sudo_cmd = ["sudo"] + install_cmd
                    result = subprocess.run(
                        sudo_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    return result.returncode == 0
                
                print(f"安装错误: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("⏰ 安装超时")
            return False
        except FileNotFoundError:
            print(f"❌ 包管理器 {pm} 不可用")
            return False
        except Exception as e:
            print(f"❌ 安装异常: {e}")
            return False

    def _refresh_font_cache(self):
        """刷新字体缓存"""
        try:
            print("🔄 刷新字体缓存...")
            subprocess.run(
                ["fc-cache", "-f"],
                capture_output=True,
                timeout=60
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # fc-cache 不是必需的

    async def download_font_to_local(self) -> bool:
        """
        下载中文字体到本地作为备选方案
        当系统包管理器安装失败时使用
        优先下载 woff2 格式（更小），回退到 OTF 格式
        
        Returns:
            是否下载成功
        """
        try:
            import aiohttp
            
            # 字体保存目录
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            fonts_dir = os.path.join(plugin_dir, "data", "fonts")
            os.makedirs(fonts_dir, exist_ok=True)
            
            # 检查是否已存在任何字体文件
            woff2_file = os.path.join(fonts_dir, "NotoSansSC-Regular.woff2")
            otf_file = os.path.join(fonts_dir, "NotoSansSC-Regular.otf")
            
            if os.path.exists(woff2_file) and os.path.getsize(woff2_file) > 100000:
                print(f"✅ 本地字体已存在: {woff2_file}")
                return True
            if os.path.exists(otf_file) and os.path.getsize(otf_file) > 1000000:
                print(f"✅ 本地字体已存在: {otf_file}")
                return True
            
            # 字体 URL 列表（优先 woff2，回退 OTF）
            font_urls = [
                # Google Fonts woff2 (小，约1-2MB)
                ("NotoSansSC-Regular.woff2", "https://fonts.gstatic.com/s/notosanssc/v36/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaG9_FnYxNbPzS5HE.woff2"),
                # GitHub OTF (大，约16MB，作为备选)
                ("NotoSansSC-Regular.otf", "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf"),
            ]
            
            print(f"📥 正在下载中文字体...")
            
            async with aiohttp.ClientSession() as session:
                for filename, font_url in font_urls:
                    try:
                        font_file = os.path.join(fonts_dir, filename)
                        print(f"   尝试下载: {filename}...")
                        
                        async with session.get(font_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                            if resp.status == 200:
                                content = await resp.read()
                                
                                # 验证内容大小（woff2 应该大于 100KB，OTF 大于 1MB）
                                min_size = 100000 if filename.endswith(".woff2") else 1000000
                                if len(content) < min_size:
                                    print(f"   ⚠️ 文件太小，跳过")
                                    continue
                                
                                with open(font_file, "wb") as f:
                                    f.write(content)
                                print(f"✅ 字体下载成功: {font_file} ({len(content)} bytes)")
                                
                                # 配置本地字体目录
                                self._configure_local_fonts(fonts_dir)
                                return True
                            else:
                                print(f"   ⚠️ HTTP {resp.status}，尝试下一个源...")
                    except Exception as e:
                        print(f"   ⚠️ 下载失败: {e}，尝试下一个源...")
            
            print(f"❌ 所有字体源下载失败")
            return False
                        
        except Exception as e:
            print(f"❌ 字体下载异常: {e}")
            return False

    def _configure_local_fonts(self, fonts_dir: str):
        """
        配置本地字体目录到 fontconfig
        
        Args:
            fonts_dir: 字体目录路径
        """
        try:
            # 创建用户字体配置
            home = os.path.expanduser("~")
            local_fonts_dir = os.path.join(home, ".fonts")
            os.makedirs(local_fonts_dir, exist_ok=True)
            
            # 创建符号链接到我们的字体目录
            for font_file in os.listdir(fonts_dir):
                if font_file.endswith((".ttf", ".otf", ".woff2")):
                    src = os.path.join(fonts_dir, font_file)
                    dst = os.path.join(local_fonts_dir, font_file)
                    if not os.path.exists(dst):
                        try:
                            os.symlink(src, dst)
                        except OSError:
                            # 符号链接失败，尝试复制
                            import shutil
                            shutil.copy2(src, dst)
            
            # 刷新字体缓存
            self._refresh_font_cache()
            print(f"✅ 已配置本地字体目录: {local_fonts_dir}")
            
        except Exception as e:
            print(f"⚠️ 配置本地字体目录失败: {e}")


# 创建全局依赖管理器实例
dependency_manager = DependencyManager()
