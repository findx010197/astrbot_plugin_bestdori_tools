import base64
import mimetypes
import os


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
