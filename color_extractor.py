"""
颜色提取工具模块
用于从卡面图像中提取主导色彩或从角色数据库获取主题色
"""

from PIL import Image
import colorsys
from typing import Optional, Tuple, List
import os
from collections import Counter

# 导入角色主题色数据库
try:
    from .character_colors import get_character_theme_color
except ImportError:
    # 在某些情况下使用绝对导入作为回退
    from character_colors import get_character_theme_color


class ColorExtractor:
    """图像颜色提取器"""

    def __init__(self):
        self.cache = {}

    def extract_character_color(self, character_id: str, image_path: str = None) -> str:
        """
        获取角色主题色，优先从数据库获取，回退到图像提取

        Args:
            character_id: 角色ID
            image_path: 可选的图像路径，用于回退提取

        Returns:
            十六进制颜色字符串，例如 "#e91e63"
        """
        # 首先尝试从角色数据库获取
        try:
            theme_color = get_character_theme_color(character_id)
            if theme_color != "#FF69B4":  # 不是默认色，说明找到了
                return theme_color
        except Exception as e:
            print(f"从角色数据库获取颜色失败: {e}")

        # 如果数据库没有，尝试从图像提取
        if image_path:
            print(f"角色 {character_id} 在数据库中未找到，尝试从图像提取颜色...")
            return self.extract_vibrant_color(image_path)

        # 最后回退到默认颜色
        return self._get_fallback_color()

    def extract_vibrant_color(self, image_path: str) -> str:
        """
        从图像中提取高饱和度的亮色

        Args:
            image_path: 图像路径（支持本地路径或URL）

        Returns:
            十六进制颜色字符串，例如 "#e91e63"
        """
        # 使用缓存避免重复处理
        if image_path in self.cache:
            return self.cache[image_path]

        try:
            # 加载图像
            img = self._load_image(image_path)
            if not img:
                return self._get_fallback_color()

            # 缩小图像以提高处理速度
            img = img.resize((150, 150), Image.LANCZOS)

            # 转换为RGB模式
            if img.mode != "RGB":
                img = img.convert("RGB")

            # 获取像素数据
            pixels = list(img.getdata())

            # 过滤出高饱和度的亮色像素
            vibrant_pixels = []
            for r, g, b in pixels:
                # 转换为HSV
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

                # 筛选条件：高饱和度(>0.4) 且 亮度适中(0.3-0.9)
                if s > 0.4 and 0.3 < v < 0.9:
                    # 排除过于接近白色/黑色/灰色的像素
                    if not (abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30):
                        vibrant_pixels.append((r, g, b))

            if not vibrant_pixels:
                # 如果没有找到符合条件的像素，放宽条件
                for r, g, b in pixels:
                    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                    if s > 0.3 and v > 0.4:  # 放宽条件
                        vibrant_pixels.append((r, g, b))

            if not vibrant_pixels:
                return self._get_fallback_color()

            # 使用k-means聚类找到主导色
            dominant_color = self._find_dominant_color(vibrant_pixels)

            # 确保颜色足够鲜艳
            dominant_color = self._enhance_color(dominant_color)

            # 转换为十六进制
            hex_color = "#{:02x}{:02x}{:02x}".format(*dominant_color)

            # 缓存结果
            self.cache[image_path] = hex_color

            return hex_color

        except Exception as e:
            print(f"颜色提取失败: {e}")
            return self._get_fallback_color()

    def _load_image(self, image_path: str) -> Optional[Image.Image]:
        """加载图像（仅支持本地文件，颜色主要从数据库获取）"""
        try:
            if image_path.startswith(("http://", "https://")):
                # 不再支持直接从URL加载，颜色应从角色数据库获取
                # 如果需要从URL获取，应先下载到本地
                return None
            elif image_path.startswith("file://"):
                # file:// URI
                local_path = image_path[7:]  # 移除 'file://' 前缀
                if os.path.exists(local_path):
                    return Image.open(local_path)
            else:
                # 本地文件路径
                if os.path.exists(image_path):
                    return Image.open(image_path)

            return None
        except Exception:
            return None

    def _find_dominant_color(
        self, pixels: List[Tuple[int, int, int]]
    ) -> Tuple[int, int, int]:
        """使用简化的聚类算法找到主导色"""
        if len(pixels) <= 5:
            return pixels[0]

        # 使用颜色直方图找到最常见的颜色区域
        color_counts = Counter()

        # 将相似颜色归类（减少颜色精度）
        for r, g, b in pixels:
            # 减少到32级精度
            key = (r // 8 * 8, g // 8 * 8, b // 8 * 8)
            color_counts[key] += 1

        # 获取最常见的颜色
        if color_counts:
            return color_counts.most_common(1)[0][0]
        else:
            return pixels[0]

    def _enhance_color(self, color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """增强颜色的饱和度和亮度"""
        r, g, b = color

        # 转换到HSV空间
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

        # 增强饱和度（但不超过1.0）
        s = min(1.0, s * 1.2)

        # 确保亮度在合适范围
        if v < 0.4:
            v = 0.5
        elif v > 0.9:
            v = 0.8

        # 转换回RGB
        r, g, b = colorsys.hsv_to_rgb(h, s, v)

        return (int(r * 255), int(g * 255), int(b * 255))

    def _get_fallback_color(self) -> str:
        """获取备用颜色"""
        import random

        fallback_colors = [
            "#e91e63",  # Pink
            "#9c27b0",  # Purple
            "#673ab7",  # Deep Purple
            "#3f51b5",  # Indigo
            "#2196f3",  # Blue
            "#00bcd4",  # Cyan
            "#009688",  # Teal
            "#4caf50",  # Green
            "#8bc34a",  # Light Green
            "#ff9800",  # Orange
            "#ff5722",  # Deep Orange
        ]
        return random.choice(fallback_colors)


# 创建全局实例
color_extractor = ColorExtractor()
