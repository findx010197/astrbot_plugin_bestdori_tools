"""
角色主题色映射数据库
存储每个角色的官方主题色或代表色
"""

"""
角色主题色映射数据库
存储每个角色的官方主题色或代表色
基于官方乐队成员配色方案
"""

# 官方角色主题色数据（基于用户提供的JSON，修正ID映射）
OFFICIAL_CHARACTER_COLORS = {
    # Poppin'Party (1-5)
    "1": "#FF4433",  # 戸山香澄 (Kasumi)
    "2": "#0077DD",  # 花園たえ (Tae)
    "3": "#FF88AA",  # 牛込りみ (Rimi)
    "4": "#FFCC11",  # 山吹沙綾 (Saya)
    "5": "#AA66DD",  # 市ヶ谷有咲 (Arisa)
    # Afterglow (6-10)
    "6": "#AA2233",  # 美竹蘭 (Ran)
    "7": "#00CCAA",  # 青葉モカ (Moca)
    "8": "#FF8899",  # 上原ひまり (Himari)
    "9": "#992233",  # 宇田川巴 (Tomoe)
    "10": "#FFEE88",  # 羽沢つぐみ (Tsugumi)
    # Hello, Happy World! (11-15)
    "11": "#FFDD00",  # 弦巻こころ (Kokoro)
    "12": "#AA33CC",  # 瀬田薫 (Kaoru)
    "13": "#FF9900",  # 北沢はぐみ (Hagumi)
    "14": "#44CCFF",  # 松原花音 (Kanon)
    "15": "#334466",  # 奥沢美咲 (Misaki)
    # Pastel*Palettes (16-20)
    "16": "#FF99AA",  # 丸山彩 (Aya)
    "17": "#44DDAA",  # 氷川日菜 (Hina)
    "18": "#FFEEAA",  # 白鷺千聖 (Chisato)
    "19": "#99DD88",  # 大和麻弥 (Maya)
    "20": "#CCEEFF",  # 若宮イヴ (Eve)
    # Roselia (21-25)
    "21": "#6644CC",  # 湊友希那 (Yukina) - 紫色
    "22": "#00AAAA",  # 氷川紗夜 (Sayo) - 青绿色
    "23": "#DD2200",  # 今井リサ (Lisa) - 红色
    "24": "#DD33BB",  # 宇田川あこ (Ako) - 粉紫色
    "25": "#BBBBCC",  # 白金燐子 (Rinko) - 灰蓝色
    # Morfonica (26-30)
    "26": "#D8DDE9",  # 倉田ましろ (Mashiro) - 仓田真白
    "27": "#F24D50",  # 桐谷透子 (Touko)
    "28": "#EE7D52",  # 広町七深 (Nanami)
    "29": "#EF86BA",  # 二葉つくし (Tsukushi)
    "30": "#64A38C",  # 八潮瑠唯 (Rui)
    # RAISE A SUILEN
    "31": "#CC2222",  # レイヤ (LAYER)
    "32": "#99DD44",  # ロック (LOCK)
    "33": "#DDBB33",  # マスキング (MASKING)
    "34": "#FF99BB",  # パレオ (PAREO)
    "35": "#3355BB",  # チュチュ (CHU2)
    # MyGO!!!!! (36-40)
    "36": "#5F7499",  # 高松灯 (Tomori)
    "37": "#F48C9E",  # 千早爱音 (Anon)
    "38": "#8CC04F",  # 要乐奈 (Rana)
    "39": "#F5D35E",  # 长崎爽世 (Soyo) - 蜜橘色/金黄色
    "40": "#323C52",  # 椎名立希 (Taki) - 深蓝灰色
    # Ave Mujica (41-45)
    "41": "#7F1D48",  # 三角初华 (Doloris)
    "42": "#6D8E6F",  # 若叶睦 (Mortis)
    "43": "#2B3549",  # 八幡海铃 (Timoris)
    "44": "#CF3D69",  # 祐天寺若麦 (Amoris)
    "45": "#4F5577",  # 丰川祥子 (Oblivionis)
}

# 保留旧的映射表作为备用（如果官方数据中没有对应的角色）
FALLBACK_CHARACTER_COLORS = {
    # 一些可能的额外角色或特殊情况
}

# 乐队主题色
BAND_THEME_COLORS = {
    "1": "#FFB6C1",  # Poppin'Party - 淡粉色
    "2": "#FF6347",  # Afterglow - 橙红色
    "3": "#FFB6C1",  # Pastel*Palettes - 淡粉色
    "4": "#8A2BE2",  # Roselia - 紫色
    "5": "#FFD700",  # ハロー、ハッピーワールド！ - 金黄色
    "18": "#FFA500",  # MyGO!!!!! - 橙色
    "21": "#8B0000",  # Ave Mujica - 深红色
}

# 属性主题色
ATTRIBUTE_COLORS = {
    "powerful": "#FF6B6B",  # 红色系
    "cool": "#4ECDC4",  # 青色系
    "pure": "#45B7D1",  # 蓝色系
    "happy": "#FFA726",  # 橙色系
}


def get_character_theme_color(character_id: str) -> str:
    """
    获取角色的主题色

    Args:
        character_id: 角色ID字符串

    Returns:
        十六进制颜色代码
    """
    # 首先尝试从官方颜色数据获取
    color = OFFICIAL_CHARACTER_COLORS.get(character_id)
    if color:
        return color

    # 回退到备用数据
    color = FALLBACK_CHARACTER_COLORS.get(character_id)
    if color:
        return color

    # 最终回退到默认粉色
    return "#FF69B4"


def get_band_theme_color(band_id: str) -> str:
    """
    获取乐队的主题色

    Args:
        band_id: 乐队ID字符串

    Returns:
        十六进制颜色代码
    """
    return BAND_THEME_COLORS.get(band_id, "#FFB6C1")  # 默认淡粉色


def get_attribute_color(attribute: str) -> str:
    """
    获取属性的主题色

    Args:
        attribute: 属性名称

    Returns:
        十六进制颜色代码
    """
    return ATTRIBUTE_COLORS.get(attribute.lower(), "#FF69B4")  # 默认粉色
