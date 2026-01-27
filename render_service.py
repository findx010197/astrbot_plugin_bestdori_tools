import os
from jinja2 import Environment, FileSystemLoader
from html2image import Html2Image
from typing import Dict, Any
import sys
from PIL import Image
import logging

logger = logging.getLogger("bestdori_render")


class RenderService:
    def __init__(self, template_dir: str, output_dir: str = None):
        self.template_dir = template_dir
        self.output_dir = output_dir  # 渲染图片输出目录
        self.env = Environment(loader=FileSystemLoader(template_dir))

        # 延迟初始化 Html2Image，避免在 Docker 等无 Chrome 环境中崩溃
        self._hti = None
        self._browser_path = None
        self._chrome_available = None  # None 表示未检测

        # 尝试自动查找浏览器路径
        self._detect_browser()

        # 检测中文字体
        self._check_chinese_fonts()

    def _detect_browser(self):
        """检测可用的浏览器"""
        # Windows 路径
        if sys.platform.startswith("win"):
            potential_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ]
        # Linux 路径 (Docker 环境)
        else:
            potential_paths = [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/snap/bin/chromium",
            ]

        for path in potential_paths:
            if os.path.exists(path):
                self._browser_path = path
                logger.info(f"检测到浏览器: {path}")
                return

        logger.warning("未检测到 Chrome/Chromium 浏览器，图片渲染功能可能不可用")

    def _check_chinese_fonts(self):
        """检测系统是否安装了中文字体"""
        if sys.platform.startswith("win"):
            # Windows 通常有中文字体支持
            return

        # Linux: 检查常见的中文字体文件
        font_paths = [
            "/usr/share/fonts/opentype/noto",  # Noto CJK
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/wqy",  # 文泉驿
            "/usr/share/fonts/truetype/droid",  # Droid
            "/usr/share/fonts/noto-cjk",  # Alpine
        ]

        has_chinese_font = False
        for font_path in font_paths:
            if os.path.exists(font_path):
                has_chinese_font = True
                logger.info(f"检测到中文字体目录: {font_path}")
                break

        if not has_chinese_font:
            logger.warning(
                "⚠️ 未检测到中文字体，渲染的图片中文可能显示为方块！\n"
                "请安装中文字体: apt-get install -y fonts-noto-cjk fonts-wqy-microhei\n"
                "然后运行: fc-cache -fv"
            )

    @property
    def hti(self) -> Html2Image:
        """惰性加载 Html2Image 实例"""
        if self._hti is None:
            flags = [
                "--hide-scrollbars",
                "--disable-gpu",
                "--log-level=3",
                "--no-sandbox",  # Docker 环境需要
                "--disable-dev-shm-usage",  # Docker 环境需要
                "--lang=zh-CN",  # 设置语言为中文
                "--font-render-hinting=none",  # 禁用字体 hinting，改善渲染
                "--force-color-profile=srgb",  # 强制颜色配置
            ]
            try:
                if self._browser_path:
                    self._hti = Html2Image(
                        browser_executable=self._browser_path, custom_flags=flags
                    )
                else:
                    self._hti = Html2Image(custom_flags=flags)
                self._chrome_available = True
            except FileNotFoundError as e:
                logger.error(f"Chrome/Chromium 未找到: {e}")
                self._chrome_available = False
                raise RuntimeError(
                    "图片渲染需要 Chrome/Chromium 浏览器。\n"
                    "Docker 用户请安装 chromium 和中文字体:\n"
                    "apt-get install -y chromium fonts-noto-cjk\n"
                    "或使用包含 Chrome 的镜像。"
                ) from e
        return self._hti

    def is_render_available(self) -> bool:
        """检查渲染功能是否可用"""
        if self._chrome_available is not None:
            return self._chrome_available
        try:
            _ = self.hti
            return True
        except RuntimeError:
            return False

    def render_template(self, template_name: str, **kwargs) -> str:
        """
        渲染模板为HTML字符串

        Args:
            template_name: 模板文件名
            **kwargs: 传递给模板的数据

        Returns:
            渲染后的HTML字符串
        """
        template = self.env.get_template(template_name)
        return template.render(**kwargs)

    def _get_local_font_base64(self) -> str:
        """
        获取本地字体的 base64 编码

        Returns:
            字体的 base64 编码，如果本地不存在则返回 None
        """
        import base64

        # 检查本地字体文件
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        font_paths = [
            os.path.join(plugin_dir, "data", "fonts", "NotoSansSC-Regular.otf"),
            os.path.join(plugin_dir, "data", "fonts", "NotoSansSC-Regular.woff2"),
        ]

        for font_path in font_paths:
            if os.path.exists(font_path) and os.path.getsize(font_path) > 100000:
                try:
                    with open(font_path, "rb") as f:
                        font_data = f.read()

                    # 确定字体格式
                    if font_path.endswith(".woff2"):
                        font_format = "woff2"
                        mime_type = "font/woff2"
                    elif font_path.endswith(".otf"):
                        font_format = "opentype"
                        mime_type = "font/otf"
                    else:
                        font_format = "truetype"
                        mime_type = "font/ttf"

                    b64 = base64.b64encode(font_data).decode("utf-8")
                    logger.info(
                        f"✅ 已加载本地字体: {font_path} ({len(font_data)} bytes)"
                    )
                    return f"data:{mime_type};base64,{b64}", font_format
                except Exception as e:
                    logger.warning(f"读取本地字体失败 {font_path}: {e}")

        return None, None

    def _inject_font_fallback(self, html_content: str) -> str:
        """
        为 HTML 注入中文字体回退支持
        优先使用本地嵌入的字体，回退到 Web 字体

        Args:
            html_content: 原始 HTML 内容

        Returns:
            注入字体支持后的 HTML
        """
        # 尝试获取本地字体
        local_font_data, font_format = self._get_local_font_base64()

        if local_font_data:
            # 使用本地嵌入的字体
            font_css = f"""
<style id="bestdori-font-embedded">
/* 本地嵌入字体 - 确保任何环境都能正确渲染中文 */
@font-face {{
    font-family: 'Noto Sans SC Embedded';
    font-style: normal;
    font-weight: 400;
    font-display: block;
    src: url('{local_font_data}') format('{font_format}');
}}

@font-face {{
    font-family: 'Noto Sans SC Embedded';
    font-style: normal;
    font-weight: 700;
    font-display: block;
    src: url('{local_font_data}') format('{font_format}');
}}

/* 中文字体回退栈 - 嵌入字体优先 */
:root {{
    --zh-font-stack: "Noto Sans SC Embedded", "Noto Sans CJK SC", "Noto Sans SC", 
                     "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", 
                     "Hiragino Sans GB", "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
                     "SimHei", "Droid Sans Fallback", "Heiti SC", sans-serif;
}}

/* 全局字体强制覆盖 */
* {{
    font-family: var(--zh-font-stack) !important;
}}

html, body {{
    font-family: var(--zh-font-stack) !important;
}}
</style>
"""
            logger.info("✅ 已注入嵌入式中文字体支持")
        else:
            # 回退到 Web 字体
            font_css = """
<!-- 字体预加载 - 多 CDN 源 -->
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>

<style id="bestdori-font-fallback">
/* Web 字体加载 - Google Fonts CDN */
@font-face {
    font-family: 'Noto Sans SC Web';
    font-style: normal;
    font-weight: 400;
    font-display: block;
    src: url('https://fonts.gstatic.com/s/notosanssc/v36/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaG9_FnYxNbPzS5HE.woff2') format('woff2'),
         url('https://cdn.jsdelivr.net/npm/@aspect-build/aspect-fonts-noto-sans-sc@5.0.0/dist/NotoSansSC-Regular.woff2') format('woff2');
    unicode-range: U+4E00-9FFF, U+3400-4DBF, U+3000-303F, U+FF00-FFEF, U+2E80-2EFF;
}

@font-face {
    font-family: 'Noto Sans SC Web';
    font-style: normal;
    font-weight: 700;
    font-display: block;
    src: url('https://fonts.gstatic.com/s/notosanssc/v36/k3kXo84MPvpLmixcA63oeALhLOCT-xWNm8Hqd37g1OkDRZe7lR4sg1IzSy-MNbE9VH8V.0.woff2') format('woff2');
    unicode-range: U+4E00-9FFF, U+3400-4DBF, U+3000-303F, U+FF00-FFEF, U+2E80-2EFF;
}

/* 中文字体回退栈 - Web 字体优先 */
:root {
    --zh-font-stack: "Noto Sans SC Web", "Noto Sans CJK SC", "Noto Sans SC", 
                     "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", 
                     "Hiragino Sans GB", "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
                     "SimHei", "Droid Sans Fallback", "Heiti SC", sans-serif;
}

/* 全局字体强制覆盖 */
* {
    font-family: var(--zh-font-stack) !important;
}

html, body {
    font-family: var(--zh-font-stack) !important;
}
</style>

<!-- 字体加载检测脚本 -->
<script>
(function() {
    // 等待字体加载完成
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function() {
            document.body.setAttribute('data-fonts-loaded', 'true');
            console.log('Fonts loaded');
        });
    }
    // 强制触发字体加载
    var testEl = document.createElement('div');
    testEl.style.fontFamily = 'Noto Sans SC Web';
    testEl.style.position = 'absolute';
    testEl.style.left = '-9999px';
    testEl.textContent = '测试字体加载中文';
    document.body.appendChild(testEl);
})();
</script>
"""
            logger.info("✅ 已注入 Web 字体支持（本地字体不存在）")

        # 在 <head> 标签后注入字体 CSS
        if "<head>" in html_content:
            html_content = html_content.replace("<head>", "<head>\n" + font_css, 1)
        elif "<HEAD>" in html_content:
            html_content = html_content.replace("<HEAD>", "<HEAD>\n" + font_css, 1)
        else:
            # 如果没有 head 标签，在开头添加
            html_content = font_css + html_content

        return html_content

    async def html_to_image(
        self,
        html_content: str,
        prefix: str = "render",
        width: int = 900,
        output_path: str = None,
        inject_fonts: bool = True,
    ) -> str:
        """
        将HTML内容转换为图片

        Args:
            html_content: HTML字符串
            prefix: 输出文件名前缀
            width: 渲染宽度（默认900，横向布局可设置更大）
            output_path: 指定输出文件的绝对路径（如果指定则忽略 prefix）
            inject_fonts: 是否注入字体回退支持（默认 True）

        Returns:
            图片文件的绝对路径

        Raises:
            RuntimeError: 当 Chrome/Chromium 不可用时
        """
        # 注入字体回退支持
        if inject_fonts:
            html_content = self._inject_font_fallback(html_content)

        # 检查渲染功能是否可用
        if not self.is_render_available():
            raise RuntimeError(
                "图片渲染功能不可用：未找到 Chrome/Chromium 浏览器。\n"
                "Docker 用户解决方案：\n"
                "1. 在 Dockerfile 中添加: RUN apt-get update && apt-get install -y chromium\n"
                "2. 或使用包含 Chrome 的基础镜像"
            )

        import tempfile
        import uuid

        # 确定输出目录和文件路径
        if output_path:
            output_dir = os.path.dirname(output_path)
            output_file = os.path.basename(output_path)
        else:
            # 使用工作区目录或临时目录
            if self.output_dir:
                output_dir = os.path.join(self.output_dir, "renders")
            else:
                output_dir = os.path.join(tempfile.gettempdir(), "bestdori_renders")

            output_file = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
            output_path = os.path.join(output_dir, output_file)

        os.makedirs(output_dir, exist_ok=True)

        # 保存HTML到文件（用于file://方式渲染，确保图片能加载）
        html_path = output_path.replace(".png", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 渲染图片 - 使用文件URL方式，确保远程图片能够加载
        self.hti.output_path = output_dir
        # 使用 url 参数而非 html_str，让浏览器有时间加载远程图片
        file_url = f"file:///{html_path.replace(os.sep, '/')}"

        # 等待一段时间让字体和图片加载
        import asyncio

        await asyncio.sleep(3)  # 等待3秒让字体和图片预加载

        logger.info(f"🖼️ 开始渲染: {output_file}")

        self.hti.screenshot(url=file_url, save_as=output_file, size=(width, 4000))

        # 自动裁剪背景（移除紫色渐变区域）并添加圆角
        try:
            img = Image.open(output_path)

            # 确保是RGB模式（用于裁剪检测）
            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img_for_detection = background
            else:
                img_for_detection = img

            pixels = img_for_detection.load()
            width, height = img_for_detection.size

            # 检测函数：判断像素是否为页面外的空白背景
            # 页面背景: linear-gradient(180deg, #fff5f7 0%, #ffe8ec 100%) - 淡粉色
            # 页脚背景: linear-gradient(135deg, #6b3a5b, #4a2848) - 深紫色
            def is_outside_background(pixel):
                r, g, b = pixel[0], pixel[1], pixel[2]
                # 纯白色或接近白色（html2image的默认背景）
                if r > 250 and g > 250 and b > 250:
                    return True
                # 黑色（可能的截图默认色）
                if r < 10 and g < 10 and b < 10:
                    return True
                # 淡粉色背景 (R~255, G~230-245, B~235-247)
                # 识别为背景，以便裁剪到白色内容区域，然后再加 Padding 露出一部分粉色
                if r > 240 and g > 220 and b > 220:
                    return True
                return False

            # 检测页脚：深紫色 #6b3a5b 到 #4a2848
            def is_footer_area(pixel):
                r, g, b = pixel[0], pixel[1], pixel[2]
                # 深紫色范围检测
                if 60 <= r <= 120 and 40 <= g <= 80 and 70 <= b <= 110:
                    return True
                return False

            # 从下往上找到页脚底部（第一个非空白行）
            bottom = height
            found_footer = False
            for y in range(height - 1, -1, -1):
                has_content = False
                for x in range(width):
                    if not is_outside_background(pixels[x, y]):
                        has_content = True
                        break
                if has_content:
                    bottom = min(height, y + 1)
                    found_footer = True
                    break

            # 如果没找到内容，保持原始高度
            if not found_footer:
                bottom = height

            # 从上往下找到第一行内容（通常是卡片顶部）
            top = 0
            for y in range(height):
                has_content = False
                for x in range(width):
                    if not is_outside_background(pixels[x, y]):
                        has_content = True
                        break
                if has_content:
                    top = max(0, y)
                    break

            # 从左往右找到第一列卡片内容
            left = 0
            for x in range(width):
                has_content = False
                for y in range(top, bottom):  # 只在内容范围内检测
                    if not is_outside_background(pixels[x, y]):
                        has_content = True
                        break
                if has_content:
                    left = max(0, x)
                    break

            # 从右往左找到最后一列卡片内容
            right = width
            for x in range(width - 1, -1, -1):
                has_content = False
                for y in range(top, bottom):  # 只在内容范围内检测
                    if not is_outside_background(pixels[x, y]):
                        has_content = True
                        break
                if has_content:
                    right = min(width, x + 1)
                    break

            # 获取背景色：从内容区域边缘附近采样，避免取到 html2image 的白色边缘
            # 尝试在内容左上方一点点的位置采样（应该是淡粉色背景）
            sample_x = max(0, left - 5) if left > 10 else min(left + 5, width - 1)
            sample_y = max(0, top - 5) if top > 10 else min(top + 5, height - 1)
            bg_color = img.getpixel((sample_x, sample_y))

            # 如果采样到的是白色或接近白色，说明可能采样位置不对，使用预设的淡粉色
            r, g, b = bg_color[0], bg_color[1], bg_color[2]
            if r > 250 and g > 250 and b > 250:
                # 使用模板中定义的淡粉色 #fff5f7
                bg_color = (255, 245, 247)

            # 定义内容区域（不含 Padding）
            content_left = left
            content_top = top
            content_right = right
            content_bottom = bottom

            # 定义 Padding
            padding_x = 35
            padding_top = 35
            padding_bottom = 0

            # 计算目标尺寸
            content_w = content_right - content_left
            content_h = content_bottom - content_top
            target_w = content_w + padding_x * 2
            target_h = content_h + padding_top + padding_bottom

            # 创建新画布并填充背景色
            new_img = Image.new("RGB", (target_w, target_h), bg_color)

            # 裁剪内容区域并粘贴到新画布
            content_img = img.crop(
                (content_left, content_top, content_right, content_bottom)
            )
            new_img.paste(content_img, (padding_x, padding_top))

            img = new_img

            # 更新尺寸变量（用于后续处理）
            width, height = img.size

            # 添加圆角边缘（仅针对生日卡片）
            if prefix == "birthday":
                from PIL import ImageDraw

                # 更新尺寸（裁剪后）
                width, height = img.size
                radius = 30  # 圆角半径

                # 确保图片是RGB模式
                if img.mode == "RGBA":
                    img = img.convert("RGB")
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # 创建圆角矩形遮罩
                mask = Image.new("L", (width, height), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle(
                    [(0, 0), (width, height)], radius=radius, fill=255
                )

                # 创建带透明度的输出图片
                rounded_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

                # 将原图粘贴到圆角图片上，使用圆角遮罩
                rounded_img.paste(img, (0, 0), mask)

                # 保存为PNG（带透明背景）
                rounded_img.save(output_path, "PNG")
            else:
                img.save(output_path)

        except Exception as e:
            print(f"⚠️ 自动裁剪失败，保留原图: {e}")

        return output_path

    def render_event_card(self, data: Dict[str, Any], output_path: str):
        """
        渲染活动卡片
        :param data: 模板数据
        :param output_path: 输出图片的绝对路径
        """
        # 检查渲染功能是否可用
        if not self.is_render_available():
            logger.error("渲染活动卡片失败：Chrome/Chromium 不可用")
            raise RuntimeError(
                "图片渲染功能不可用：未找到 Chrome/Chromium 浏览器。\n"
                "Docker 用户请执行: apt-get update && apt-get install -y chromium"
            )

        template = self.env.get_template("event_card.html")
        html_content = template.render(**data)

        # 为了调试，可以先把 HTML 保存下来看看
        html_path = output_path.replace(".png", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 渲染图片
        # 这里的 output_path 必须是文件名，output_path 的目录作为 save_as 的路径
        output_dir = os.path.dirname(output_path)
        output_file = os.path.basename(output_path)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            self.hti.output_path = output_dir
            # 设置更大的初始高度以容纳长图内容（从3000增加到6000）
            # 需要配合 HTML 的 body { height: fit-content } 实现自适应
            self.hti.screenshot(
                html_str=html_content, save_as=output_file, size=(900, 6000)
            )
            logger.info(f"活动卡片渲染成功: {output_path}")
        except Exception as e:
            logger.error(f"活动卡片渲染失败: {e}")
            raise RuntimeError(f"渲染活动卡片失败: {e}") from e

        # 自动裁剪底部空白
        try:
            img = Image.open(output_path)
            # 转换为RGB模式（如果是RGBA）
            if img.mode == "RGBA":
                # 创建白色背景
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])  # 使用alpha通道作为mask
                img = background

            # 从下往上扫描，找到第一行非空白内容
            pixels = img.load()
            width, height = img.size
            bottom = height

            # 定义空白行的阈值（允许少量噪点）
            for y in range(height - 1, -1, -1):
                is_blank = True
                for x in range(width):
                    pixel = pixels[x, y]
                    # 检查是否接近白色 (RGB 都大于 250)
                    if not (pixel[0] > 250 and pixel[1] > 250 and pixel[2] > 250):
                        is_blank = False
                        break
                if not is_blank:
                    bottom = y + 1
                    break

            # 裁剪图片（保留顶部到最后有内容的行，加20px边距）
            if bottom < height - 50:  # 如果底部有超过50px的空白才裁剪
                img_cropped = img.crop((0, 0, width, min(bottom + 20, height)))
                img_cropped.save(output_path)
        except Exception as e:
            print(f"⚠️ 自动裁剪失败，保留原图: {e}")

        return output_path

    def render_event_overview_card(self, data: Dict[str, Any], output_path: str):
        """
        渲染活动一览卡片（新格式，包含多个活动元素）
        :param data: 模板数据，包含新成员、活动详情、招募信息等
        :param output_path: 输出图片的绝对路径
        """
        # 检查渲染功能是否可用
        if not self.is_render_available():
            logger.error("渲染活动一览卡片失败：Chrome/Chromium 不可用")
            raise RuntimeError(
                "图片渲染功能不可用：未找到 Chrome/Chromium 浏览器。\n"
                "Docker 用户请执行: apt-get update && apt-get install -y chromium"
            )

        template = self.env.get_template("event_overview_card.html")
        html_content = template.render(**data)

        # 调试：保存HTML文件
        html_path = output_path.replace(".png", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 渲染图片
        output_dir = os.path.dirname(output_path)
        output_file = os.path.basename(output_path)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            self.hti.output_path = output_dir
            # 活动一览卡片通常更长，设置更大的初始高度
            self.hti.screenshot(
                html_str=html_content, save_as=output_file, size=(900, 8000)
            )
            logger.info(f"活动一览卡片渲染成功: {output_path}")
        except Exception as e:
            logger.error(f"活动一览卡片渲染失败: {e}")
            raise RuntimeError(f"渲染活动一览卡片失败: {e}") from e

        # 自动裁剪：识别页脚并在页脚底部裁剪
        try:
            img = Image.open(output_path)
            # 转换为RGB模式（如果是RGBA）
            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background

            pixels = img.load()
            width, height = img.size

            # 页脚颜色检测：深紫色 #6b3a5b (107,58,91) 到 #4a2848 (74,40,72)
            def is_footer_color(pixel):
                r, g, b = pixel[0], pixel[1], pixel[2]
                # 深紫色范围：R在50-130, G在30-80, B在50-120
                if 50 <= r <= 130 and 30 <= g <= 80 and 50 <= b <= 120:
                    # 额外检查：紫色特征 - R接近B，G最小
                    if abs(r - b) < 50 and g < r and g < b:
                        return True
                return False

            # 从下往上扫描，找到页脚区域
            # 策略：找到连续的页脚颜色行，然后在其底部截断
            footer_bottom = None
            footer_found = False
            consecutive_footer_rows = 0

            for y in range(height - 1, -1, -1):
                # 采样检测：检查这一行中间区域是否是页脚颜色
                footer_pixels = 0
                sample_points = [width // 4, width // 2, 3 * width // 4]

                for x in sample_points:
                    if is_footer_color(pixels[x, y]):
                        footer_pixels += 1

                # 如果至少2个采样点是页脚颜色，认为这是页脚行
                if footer_pixels >= 2:
                    if not footer_found:
                        footer_bottom = y + 1  # 记录页脚底部位置
                        footer_found = True
                    consecutive_footer_rows += 1
                else:
                    if footer_found and consecutive_footer_rows >= 20:
                        # 找到了页脚区域（至少20行高），结束扫描
                        break
                    elif footer_found:
                        # 页脚不够高，可能是误检，重置
                        footer_found = False
                        consecutive_footer_rows = 0

            # 如果找到了页脚，在页脚底部裁剪
            if footer_found and footer_bottom and footer_bottom < height - 50:
                crop_bottom = footer_bottom
                img_cropped = img.crop((0, 0, width, crop_bottom))
                img_cropped.save(output_path)
                print(f"✂️ 自动裁剪: {height}px → {crop_bottom}px")
            else:
                # 降级方案：检测空白行裁剪
                bottom = height
                for y in range(height - 1, -1, -1):
                    is_blank = True
                    for x in range(0, width, 10):  # 每10像素采样一次
                        pixel = pixels[x, y]
                        if not (pixel[0] > 250 and pixel[1] > 250 and pixel[2] > 250):
                            is_blank = False
                            break
                    if not is_blank:
                        bottom = y + 1
                        break

                if bottom < height - 100:
                    img_cropped = img.crop((0, 0, width, bottom))
                    img_cropped.save(output_path)
                    print(f"✂️ 空白裁剪: {height}px → {bottom}px")

        except Exception as e:
            print(f"⚠️ 活动一览卡片自动裁剪失败，保留原图: {e}")
            import traceback

            traceback.print_exc()

        return output_path

    def render_latest_cards(self, data: Dict[str, Any], output_path: str):
        """
        渲染最新卡面一览卡片
        :param data: 模板数据，包含 server_name, event_count, card_count, cards 等
        :param output_path: 输出图片的绝对路径
        """
        # 检查渲染功能是否可用
        if not self.is_render_available():
            logger.error("渲染最新卡面卡片失败：Chrome/Chromium 不可用")
            raise RuntimeError(
                "图片渲染功能不可用：未找到 Chrome/Chromium 浏览器。\n"
                "Docker 用户请执行: apt-get update && apt-get install -y chromium"
            )

        template = self.env.get_template("latest_cards.html")
        html_content = template.render(**data)

        # 调试：保存HTML文件
        html_path = output_path.replace(".png", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 渲染图片
        output_dir = os.path.dirname(output_path)
        output_file = os.path.basename(output_path)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            self.hti.output_path = output_dir
            # 最新卡面卡片可能很长，设置较大的初始高度
            self.hti.screenshot(
                html_str=html_content, save_as=output_file, size=(900, 8000)
            )
            logger.info(f"最新卡面卡片渲染成功: {output_path}")
        except Exception as e:
            logger.error(f"最新卡面卡片渲染失败: {e}")
            raise RuntimeError(f"渲染最新卡面卡片失败: {e}") from e

        # 自动裁剪：识别页脚并在页脚底部裁剪
        self._auto_crop_by_footer(output_path)

        return output_path

    def _auto_crop_by_footer(self, output_path: str):
        """
        通用的页脚检测裁剪方法
        检测深紫色页脚 (#6b3a5b) 并在其底部裁剪
        """
        try:
            img = Image.open(output_path)
            # 转换为RGB模式（如果是RGBA）
            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background

            pixels = img.load()
            width, height = img.size

            # 页脚颜色检测：深紫色 #6b3a5b (107,58,91) 到 #4a2848 (74,40,72)
            def is_footer_color(pixel):
                r, g, b = pixel[0], pixel[1], pixel[2]
                # 深紫色范围：R在50-130, G在30-80, B在50-120
                if 50 <= r <= 130 and 30 <= g <= 80 and 50 <= b <= 120:
                    # 额外检查：紫色特征 - R接近B，G最小
                    if abs(r - b) < 50 and g < r and g < b:
                        return True
                return False

            # 从下往上扫描，找到页脚区域
            footer_bottom = None
            footer_found = False
            consecutive_footer_rows = 0

            for y in range(height - 1, -1, -1):
                # 采样检测：检查这一行中间区域是否是页脚颜色
                footer_pixels = 0
                sample_points = [width // 4, width // 2, 3 * width // 4]

                for x in sample_points:
                    if is_footer_color(pixels[x, y]):
                        footer_pixels += 1

                # 如果至少2个采样点是页脚颜色，认为这是页脚行
                if footer_pixels >= 2:
                    if not footer_found:
                        footer_bottom = y + 1  # 记录页脚底部位置
                        footer_found = True
                    consecutive_footer_rows += 1
                else:
                    if footer_found and consecutive_footer_rows >= 20:
                        # 找到了页脚区域（至少20行高），结束扫描
                        break
                    elif footer_found:
                        # 页脚不够高，可能是误检，重置
                        footer_found = False
                        consecutive_footer_rows = 0

            # 如果找到了页脚，在页脚底部裁剪
            if footer_found and footer_bottom and footer_bottom < height - 50:
                crop_bottom = footer_bottom
                img_cropped = img.crop((0, 0, width, crop_bottom))
                img_cropped.save(output_path)
                print(f"✂️ 自动裁剪: {height}px → {crop_bottom}px")
            else:
                # 降级方案：检测空白行裁剪
                bottom = height
                for y in range(height - 1, -1, -1):
                    is_blank = True
                    for x in range(0, width, 10):  # 每10像素采样一次
                        pixel = pixels[x, y]
                        if not (pixel[0] > 250 and pixel[1] > 250 and pixel[2] > 250):
                            is_blank = False
                            break
                    if not is_blank:
                        bottom = y + 1
                        break

                if bottom < height - 100:
                    img_cropped = img.crop((0, 0, width, bottom))
                    img_cropped.save(output_path)
                    print(f"✂️ 空白裁剪: {height}px → {bottom}px")

        except Exception as e:
            print(f"⚠️ 自动裁剪失败，保留原图: {e}")
            import traceback

            traceback.print_exc()
