import base64
import mimetypes
import os
from typing import Optional

from astrbot.api import logger


def file_to_base64_uri(file_path: str) -> str:
    """将本地图片文件转换为 Base64 Data URI"""
    if not file_path or not os.path.exists(file_path):
        return ""

    # 根据文件扩展名猜测 MIME 类型
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        if file_path.endswith(".svg"):
            mime_type = "image/svg+xml"
        else:
            mime_type = "image/png"  # 默认

    try:
        with open(file_path, "rb") as f:
            binary_data = f.read()

        base64_data = base64.b64encode(binary_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"
    except Exception:
        return ""


def enhance_image(
    input_path: str,
    output_path: Optional[str] = None,
    scale: float = 1.5,
    sharpen: bool = True,
    denoise: bool = False,
) -> Optional[str]:
    """
    增强图片清晰度

    使用高质量重采样 + 锐化滤镜来提升图像质量

    Args:
        input_path: 输入图片路径
        output_path: 输出图片路径（None 则覆盖原文件）
        scale: 放大倍数 (1.0-4.0)，默认 1.5
        sharpen: 是否应用锐化
        denoise: 是否降噪（轻微模糊后再锐化，适合有噪点的图）

    Returns:
        增强后的图片路径，失败返回 None
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        logger.warning("PIL 未安装，无法进行图像增强")
        return input_path

    if not os.path.exists(input_path):
        logger.warning(f"图片不存在: {input_path}")
        return None

    if output_path is None:
        # 生成增强后的文件名
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_enhanced{ext}"

    try:
        # 打开图片
        img = Image.open(input_path)
        original_size = img.size

        # 确保是 RGB 或 RGBA 模式
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.mode else "RGB")

        # 1. 高质量放大（使用 LANCZOS 重采样）
        if scale > 1.0:
            new_width = int(img.width * scale)
            new_height = int(img.height * scale)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 2. 可选的降噪处理（轻微高斯模糊）
        if denoise:
            img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

        # 3. 锐化处理
        if sharpen:
            # 使用 UnsharpMask 进行自适应锐化
            # radius: 模糊半径
            # percent: 锐化强度 (100-200 适中)
            # threshold: 阈值，避免锐化噪点
            img = img.filter(
                ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2)
            )

        # 4. 轻微增强对比度
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.05)  # 轻微增强

        # 5. 轻微增强色彩饱和度
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.02)  # 非常轻微

        # 保存
        if img.mode == "RGBA":
            img.save(output_path, "PNG", optimize=True)
        else:
            # JPEG 质量设为 95
            if output_path.lower().endswith((".jpg", ".jpeg")):
                img.save(output_path, "JPEG", quality=95, optimize=True)
            else:
                img.save(output_path, "PNG", optimize=True)

        logger.info(
            f"图像增强完成: {original_size[0]}x{original_size[1]} -> "
            f"{img.size[0]}x{img.size[1]} (scale={scale}, sharpen={sharpen})"
        )

        return output_path

    except Exception as e:
        logger.error(f"图像增强失败: {e}")
        return input_path  # 失败时返回原图路径


def enhance_card_image(
    input_path: str,
    output_dir: Optional[str] = None,
) -> str:
    """
    专门针对卡面图片的增强处理

    - 适度放大 (1.5x)
    - 锐化处理
    - 优化色彩

    Args:
        input_path: 输入图片路径
        output_dir: 输出目录（None 则使用原目录）

    Returns:
        增强后的图片路径
    """
    if not os.path.exists(input_path):
        return input_path

    # 确定输出路径
    filename = os.path.basename(input_path)
    base, ext = os.path.splitext(filename)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{base}_hd{ext}")
    else:
        dir_path = os.path.dirname(input_path)
        output_path = os.path.join(dir_path, f"{base}_hd{ext}")

    # 如果已经增强过，直接返回
    if os.path.exists(output_path):
        return output_path

    # 执行增强
    result = enhance_image(
        input_path=input_path,
        output_path=output_path,
        scale=1.5,  # 放大 1.5 倍
        sharpen=True,
        denoise=False,  # 卡面图一般质量不错，不需要降噪
    )

    return result if result else input_path
