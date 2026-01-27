# 乐队 ID 映射
BAND_ID_MAP = {
    1: "Poppin'Party",
    2: "Afterglow",
    3: "Pastel*Palettes",
    4: "Roselia",
    5: "Hello, Happy World!",
    18: "RAISE A SUILEN",
    21: "Morfonica",
    22: "MyGO!!!!!",
    23: "Ave Mujica",
}

# ==================== 服务器配置 ====================
# 服务器 ID 映射: 0=JP, 1=EN, 2=TW, 3=CN, 4=KR
SERVER_JP = 0
SERVER_EN = 1
SERVER_TW = 2
SERVER_CN = 3
SERVER_KR = 4

# 服务器代码映射
SERVER_CODE_MAP = {
    SERVER_JP: "jp",
    SERVER_EN: "en",
    SERVER_TW: "tw",
    SERVER_CN: "cn",
    SERVER_KR: "kr",
}

# 服务器名称映射（中文）
SERVER_NAME_MAP = {
    SERVER_JP: "日服",
    SERVER_EN: "国际服",
    SERVER_TW: "台服",
    SERVER_CN: "国服",
    SERVER_KR: "韩服",
}

# 服务器名称映射（简短）
SERVER_SHORT_NAME_MAP = {
    SERVER_JP: "JP",
    SERVER_EN: "EN",
    SERVER_TW: "TW",
    SERVER_CN: "CN",
    SERVER_KR: "KR",
}

# 默认服务器优先级（资源获取时的回退顺序）
DEFAULT_SERVER_PRIORITY = [SERVER_CN, SERVER_JP, SERVER_EN, SERVER_TW, SERVER_KR]


# 根据服务器名称/代码获取服务器ID
def get_server_id(name: str) -> int:
    """根据服务器名称或代码获取服务器ID

    Args:
        name: 服务器名称（国服/日服/cn/jp等）

    Returns:
        服务器ID，未找到返回 SERVER_CN (3)
    """
    name = name.lower().strip()

    # 代码匹配
    for sid, code in SERVER_CODE_MAP.items():
        if name == code:
            return sid

    # 名称匹配
    name_to_id = {
        "国服": SERVER_CN,
        "cn": SERVER_CN,
        "中国": SERVER_CN,
        "简中": SERVER_CN,
        "日服": SERVER_JP,
        "jp": SERVER_JP,
        "日本": SERVER_JP,
        "国际服": SERVER_EN,
        "en": SERVER_EN,
        "英服": SERVER_EN,
        "全球": SERVER_EN,
        "台服": SERVER_TW,
        "tw": SERVER_TW,
        "台湾": SERVER_TW,
        "繁中": SERVER_TW,
        "韩服": SERVER_KR,
        "kr": SERVER_KR,
        "韩国": SERVER_KR,
    }

    return name_to_id.get(name, SERVER_CN)


CHARACTER_MAP = {
    # Poppin'Party (1-5)
    1: ["户山香澄", "ksm", "香澄", "非凡之星"],
    2: ["花园多惠", "tae", "otae", "惠惠", "追兔花园"],
    3: ["牛込里美", "rimi", "里美", "李美丽", "巧克力螺", "告一段螺"],
    4: ["山吹沙绫", "saaya", "沙绫", "发酵少女"],
    5: ["市谷有咲", "arisa", "ars", "有咲", "甜辣个性"],
    # Afterglow (6-10)
    6: ["美竹兰", "ran", "兰", "叛逆的红挑染"],
    7: ["青叶摩卡", "moka", "摩卡", "毛力", "GO MY WAY"],
    8: ["上原绯玛丽", "hmr", "绯玛丽", "一呼零应"],
    9: ["宇田川巴", "tomoe", "巴", "宇田川姐", "豚骨酱油大姐头"],
    10: ["羽泽鸫", "tsugu", "鸫鸫", "伟大的平凡"],
    # Hello, Happy World! (11-15)
    11: ["弦卷心", "kkr", "笑容波状攻击", "Happy Lucky Smile Yeah"],
    12: [
        "濑田薰",
        "kaoru",
        "薰",
        "薰哥",
        "小薰",
        "小猫咪们",
        "哈卡奈",
        "梦幻",
        "荒诞无稽的独角戏",
    ],
    13: ["北泽育美", "hgm", "育美", "北泽元气认证"],
    14: ["松原花音", "kanon", "花音", "迷宫中的水母"],
    15: ["奥泽美咲", "米歇尔", "msk", "美咲", "有常识的熊"],
    # Pastel*Palettes (16-20)
    16: ["丸山彩", "aya", "彩", "丸山添彩", "疯狂的自我搜索者"],
    17: ["冰川日菜", "hina", "日菜", "噜", "冰川妹", "隔壁家的小天才"],
    18: ["白鹭千圣", "chisato", "小千", "千圣", "微笑的铁假面"],
    19: ["大和麻弥", "maya", "麻弥", "呼嘿嘿", "狂暴的器材宅"],
    20: ["若宫伊芙", "eve", "伊芙", "来自北欧的武士"],
    # Roselia (21-25)
    21: ["凑友希那", "ykn", "友希那", "狂乱绽放的紫炎蔷薇"],
    22: ["冰川纱夜", "sayo", "纱夜", "冰川姐", "忧伤节拍器"],
    23: ["今井莉莎", "lisa", "莉莎", "慈爱女神"],
    24: ["宇田川亚子", "ako", "亚子", "宇田川妹", "引起黑暗波动略黑的堕天使"],
    25: ["白金燐子", "rinko", "燐子", "燐燐", "稳如磐石的高玩"],
    # Morfonica (26-30)
    26: ["仓田真白", "msr", "真白", "向后全速前进"],
    27: ["桐谷透子", "toko", "透子", "天上天下", "唯我独尊"],
    28: ["广町七深", "nnm", "七深", "我说了什么奇怪的话吗"],
    29: ["二叶筑紫", "tks", "筑紫", "土笔", "长大的Girl"],
    30: ["八潮瑠唯", "rui", "瑠唯", "るいるい", "道理轰炸机"],
    # RAISE A SUILEN (31-35)
    31: ["和奏瑞依", "layer", "大姐头", "容易被别人叫成姐"],
    32: ["朝日六花", "lock", "六花", "六六", "吉他狂战士"],
    33: ["佐藤益木", "masking", "无赖鼓手人情派"],
    34: ["鳰原令王那", "pareo", "暗黑丸山彩", "忠犬PARE公"],
    35: ["珠手知由", "chuchu", "CHU2", "楚萍芳", "小矮子革命儿"],
    # MyGO!!!!! (36-40)
    36: ["高松灯", "tomorin", "灯"],
    37: ["千早爱音", "anon", "ano", "爱音", "Staff A"],
    38: ["要乐奈", "rana", "乐奈", "猫猫", "野良猫", "流浪猫"],
    39: ["长崎爽世", "soyo", "素世", "soyorin", "长期素食"],
    40: ["椎名立希", "taki", "立希", "rikki"],
    # Ave Mujica (41-45)
    41: ["三角初华", "doloris", "初华"],
    42: ["若叶睦", "mortis", "睦", "睦头人", "黄瓜"],
    43: ["八幡海铃", "timoris", "海铃", "雇佣兵"],
    44: ["祐天寺若麦", "amoris", "喵梦"],
    45: ["丰川祥子", "oblivionis", "祥子", "客服S"],
    # 其他角色
    46: ["纯田真奈", "mana", "甜甜圈"],
}

# 角色 -> 乐队 ID 映射
CHARACTER_BAND_MAP = {
    **{i: 1 for i in range(1, 6)},  # Poppin'Party (1-5)
    **{i: 2 for i in range(6, 11)},  # Afterglow (6-10)
    **{i: 5 for i in range(11, 16)},  # Hello, Happy World! (11-15)
    **{i: 3 for i in range(16, 21)},  # Pastel*Palettes (16-20)
    **{i: 4 for i in range(21, 26)},  # Roselia (21-25)
    **{i: 21 for i in range(26, 31)},  # Morfonica (26-30)
    **{i: 18 for i in range(31, 36)},  # RAISE A SUILEN (31-35)
    **{i: 22 for i in range(36, 41)},  # MyGO!!!!! (36-40)
    **{i: 23 for i in range(41, 46)},  # Ave Mujica (41-45)
    46: 0,  # 纯田真奈 (暂定为无乐队)
}

# 乐队图标 URL 映射 (bandId -> SVG文件名)
BAND_ICON_URL_MAP = {
    1: "band_1.svg",  # Poppin'Party
    2: "band_2.svg",  # Afterglow
    5: "band_3.svg",  # Hello, Happy World! (band_3.svg对应HHW)
    3: "band_4.svg",  # Pastel*Palettes (band_4.svg对应PP)
    4: "band_5.svg",  # Roselia (band_5.svg对应RO)
    18: "band_18.svg",  # RAISE A SUILEN
    21: "band_21.svg",  # Morfonica
    22: "band_45.svg",  # MyGO!!!!! (特殊，用 band_45.svg)
    23: "band_45.svg",  # Ave Mujica (暂用 MyGO 的，需确认)
}

# 角色生日映射 (character_id -> (月, 日))
CHARACTER_BIRTHDAYS = {
    # Poppin'Party (1-5)
    1: (7, 14),  # 户山香澄 (Kasumi)
    2: (12, 4),  # 花园多惠 (Tae)
    3: (3, 23),  # 牛込里美 (Rimi)
    4: (5, 19),  # 山吹沙绫 (Saaya)
    5: (10, 27),  # 市谷有咲 (Arisa)
    # Afterglow (6-10)
    6: (4, 10),  # 美竹兰 (Ran)
    7: (9, 3),  # 青叶摩卡 (Moca)
    8: (10, 23),  # 上原绯玛丽 (Himari)
    9: (4, 15),  # 宇田川巴 (Tomoe)
    10: (1, 7),  # 羽泽鸫 (Tsugumi)
    # Hello, Happy World! (11-15)
    11: (8, 8),  # 弦卷心 (Kokoro)
    12: (2, 28),  # 濑田薰 (Kaoru)
    13: (7, 30),  # 北泽育美 (Hagumi)
    14: (5, 11),  # 松原花音 (Kanon)
    15: (10, 1),  # 奥泽美咲 (Misaki)
    # Pastel*Palettes (16-20)
    16: (12, 27),  # 丸山彩 (Aya)
    17: (3, 20),  # 冰川日菜 (Hina)
    18: (4, 6),  # 白鹭千圣 (Chisato)
    19: (11, 3),  # 大和麻弥 (Maya)
    20: (6, 27),  # 若宫伊芙 (Eve)
    # Roselia (21-25)
    21: (10, 26),  # 凑友希那 (Yukina)
    22: (3, 20),  # 冰川纱夜 (Sayo)
    23: (8, 25),  # 今井莉莎 (Lisa)
    24: (7, 3),  # 宇田川亚子 (Ako)
    25: (10, 17),  # 白金燐子 (Rinko)
    # Morfonica (26-30)
    26: (2, 19),  # 仓田真白 (Mashiro)
    27: (12, 16),  # 桐谷透子 (Touko)
    28: (6, 16),  # 广町七深 (Nanami)
    29: (9, 15),  # 二叶筑紫 (Tsukushi)
    30: (11, 19),  # 八潮瑠唯 (Rui)
    # RAISE A SUILEN (31-35)
    31: (1, 13),  # 和奏瑞依 (Layer)
    32: (7, 17),  # 朝日六花 (Lock)
    33: (5, 12),  # 佐藤益木 (Masking)
    34: (3, 25),  # 鳰原令王那 (Pareo)
    35: (12, 7),  # 珠手知由 (Chu2)
    # MyGO!!!!! (36-40)
    36: (11, 22),  # 高松灯 (Tomori)
    37: (9, 8),  # 千早爱音 (Anon)
    38: (2, 22),  # 要乐奈 (Raana)
    39: (5, 27),  # 长崎爽世 (Soyo)
    40: (8, 9),  # 椎名立希 (Taki)
    # Ave Mujica (41-45)
    41: (6, 26),  # 三角初华 (Uika / Doloris)
    42: (1, 14),  # 若叶睦 (Mutsumi / Mortis)
    43: (4, 7),  # 八幡海铃 (Umiri / Timoris)
    44: (6, 1),  # 祐天寺若麦 (Nyamu / Amoris)
    45: (2, 14),  # 丰川祥子 (Sakiko / Oblivionis)
}


def get_character_id_by_name(name: str) -> int:
    """
    根据角色名称获取角色ID
    支持精确匹配和模糊匹配
    """
    name = name.lower().strip()

    # 如果输入为空，直接返回0
    if not name:
        return 0

    # 首先尝试精确匹配
    for char_id, aliases in CHARACTER_MAP.items():
        if name in [a.lower() for a in aliases]:
            return char_id

    # 如果精确匹配失败，尝试模糊匹配
    # 但要确保查询词长度足够（至少2个字符）且不是其他词的子串导致误匹配
    if len(name) >= 2:
        for char_id, aliases in CHARACTER_MAP.items():
            for alias in aliases:
                alias_lower = alias.lower()
                # 检查是否完整包含查询名称，避免子串误匹配
                if name in alias_lower and len(name) >= len(alias_lower) * 0.4:
                    return char_id
                # 或者查询名称包含别名（处理缩写情况）
                if alias_lower in name and len(alias_lower) >= 3:
                    return char_id

    return 0
