"""
依赖管理模块
负责检查和安装插件所需的Python依赖包
"""

import subprocess
import sys
import importlib
from typing import List, Dict, Tuple
import os


class DependencyManager:
    """依赖管理器"""

    def __init__(self):
        # 定义插件所需的依赖包
        self.required_packages = {
            "aiohttp": "aiohttp>=3.8.0",
            "jinja2": "Jinja2>=3.1.0",
            "html2image": "html2image>=2.0.0",
            "requests": "requests>=2.28.0",
            "pillow": "Pillow>=9.0.0",
            "pydub": "pydub>=0.25.0",
            "colorsys": None,  # 标准库，无需安装
            "pathlib": None,  # 标准库，无需安装
        }

        # 可选依赖（用于音频处理等）
        self.optional_packages = {
            "ffmpeg-python": "ffmpeg-python>=0.2.0",
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
        检查系统依赖（如Chrome浏览器等）

        Returns:
            系统依赖检查结果
        """
        system_deps = {}

        # 检查Chrome/Chromium（html2image需要）
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]

        chrome_found = False
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_found = True
                break

        system_deps["chrome_or_edge"] = chrome_found

        if not chrome_found:
            print("⚠️ 未检测到Chrome或Edge浏览器，HTML渲染功能可能无法正常工作")
            print("💡 建议安装Chrome或Edge浏览器以获得最佳体验")

        return system_deps


# 创建全局依赖管理器实例
dependency_manager = DependencyManager()
