"""
AstrBot 音频文件发送方案

提供音频格式转换功能，支持将 MP3 转换为 WAV 格式以便于跨平台发送。
"""

import os
import subprocess
from astrbot.api import logger


def convert_to_wav(mp3_path: str, wav_path: str) -> bool:
    """
    将 MP3 文件转换为 WAV 格式

    Args:
        mp3_path: 源 MP3 文件路径
        wav_path: 目标 WAV 文件路径

    Returns:
        bool: 转换是否成功
    """
    if not os.path.exists(mp3_path):
        logger.warning(f"源文件不存在: {mp3_path}")
        return False

    # 如果目标文件已存在，直接返回成功
    if os.path.exists(wav_path):
        logger.info(f"WAV 文件已存在: {wav_path}")
        return True

    # 尝试方案1: 使用 pydub
    try:
        from pydub import AudioSegment

        logger.info(f"使用 pydub 转换 MP3 到 WAV: {mp3_path}")
        audio = AudioSegment.from_mp3(mp3_path)
        audio.export(wav_path, format="wav")

        if os.path.exists(wav_path):
            logger.info(f"pydub 转换成功: {wav_path}")
            return True
    except ImportError:
        logger.debug("pydub 未安装，尝试其他方案")
    except Exception as e:
        logger.warning(f"pydub 转换失败: {e}")

    # 尝试方案2: 使用 ffmpeg
    try:
        logger.info(f"使用 ffmpeg 转换 MP3 到 WAV: {mp3_path}")
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                mp3_path,
                "-ar",
                "44100",
                "-ac",
                "2",
                "-y",  # 覆盖已存在的文件
                wav_path,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if os.path.exists(wav_path):
            logger.info(f"ffmpeg 转换成功: {wav_path}")
            return True
    except FileNotFoundError:
        logger.debug("ffmpeg 未安装")
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg 转换超时")
    except Exception as e:
        logger.warning(f"ffmpeg 转换失败: {e}")

    # 尝试方案3: 使用 moviepy（如果安装了的话）
    try:
        from moviepy.editor import AudioFileClip

        logger.info(f"使用 moviepy 转换 MP3 到 WAV: {mp3_path}")
        audio = AudioFileClip(mp3_path)
        audio.write_audiofile(wav_path, verbose=False, logger=None)
        audio.close()

        if os.path.exists(wav_path):
            logger.info(f"moviepy 转换成功: {wav_path}")
            return True
    except ImportError:
        logger.debug("moviepy 未安装")
    except Exception as e:
        logger.warning(f"moviepy 转换失败: {e}")

    logger.error("所有音频转换方案均失败，请安装 pydub 或 ffmpeg")
    return False


def get_audio_info(file_path: str) -> dict:
    """
    获取音频文件信息

    Args:
        file_path: 音频文件路径

    Returns:
        dict: 包含文件大小、格式等信息的字典
    """
    info = {
        "exists": False,
        "size_bytes": 0,
        "size_kb": 0,
        "format": "",
        "path": file_path,
    }

    if not os.path.exists(file_path):
        return info

    info["exists"] = True
    info["size_bytes"] = os.path.getsize(file_path)
    info["size_kb"] = info["size_bytes"] / 1024

    # 根据扩展名判断格式
    ext = os.path.splitext(file_path)[1].lower()
    format_map = {
        ".mp3": "MP3",
        ".wav": "WAV",
        ".ogg": "OGG",
        ".flac": "FLAC",
        ".m4a": "M4A",
        ".aac": "AAC",
    }
    info["format"] = format_map.get(ext, ext.upper().replace(".", ""))

    return info


if __name__ == "__main__":
    print(__doc__)
