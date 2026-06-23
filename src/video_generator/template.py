TEMPLATES = {
    "清新治愈": {
        "name": "清新治愈",
        "prompt_prefix": (
            "温馨治愈风格短视频。柔和渐变背景(淡蓝渐变到淡粉)，"
            "画面干净简洁，色调温暖明亮，舒缓放松。"
        ),
        "music": "light_piano",
        "intro_style": "soft_fade",
    },
    "专业简约": {
        "name": "专业简约",
        "prompt_prefix": (
            "简洁专业风格短视频。深蓝色纯色背景，"
            "画面整洁干净，白色几何装饰元素，专业可信赖。"
        ),
        "music": "calm_guitar",
        "intro_style": "clean_slide",
    },
    "温暖互动": {
        "name": "温暖互动",
        "prompt_prefix": (
            "活泼温暖风格短视频。暖橙色渐变背景，"
            "圆润可爱的手绘装饰元素，色彩饱满温馨，亲切有活力。"
        ),
        "music": "ukulele_happy",
        "intro_style": "bounce_in",
    },
    "知识点卡": {
        "name": "知识点卡",
        "prompt_prefix": (
            "知识讲解风格短视频。米白色柔和背景，"
            "简洁优雅的排版风格，知性清新。"
        ),
        "music": "ambient_soft",
        "intro_style": "card_flip",
    },
}

THEME_VISUALS = {
    "学业心理": "抽象的学习场景元素，书本、笔、课桌的极简线条，柔和舒缓的蓝色调。",
    "人际关系": "两个抽象人形轮廓的柔和交流场景，温暖圆形光晕，橙色调。",
    "情绪管理": "柔和流动的云朵或波浪线条，呼吸节奏般的缓慢运动，蓝绿色调。",
    "自我成长": "生长中的抽象植物或树木剪影，向上延展的线条，充满生机的绿色调。",
    "行为习惯": "手机闹钟等日常物品的极简抽象线条，规律节奏感，温馨米色调。",
    "青春期心理": "蝴蝶或蜕变相关的抽象图案，柔光粒子效果，粉紫色调。",
    "家庭教育": "大小两个圆形相互环绕的温馨构图，家的抽象轮廓，暖黄色调。",
    "心理危机": "灰暗中逐渐亮起的微光效果，从暗到明的渐变过渡，暗示希望。",
}

SUBCATEGORY_KEYWORDS = {
    "考试焦虑": "倒计时的抽象表达，沙漏或时钟的柔化轮廓。",
    "学习动力": "火箭或箭头向上攀升的抽象线条。",
    "校园欺凌": "破碎到愈合的抽象表达，碎片重聚效果。",
    "亲子沟通": "两颗心形或两个圆形的对话连接线。",
    "网络成瘾": "手机屏幕逐渐淡出的效果。",
    "压力应对": "重物从身上逐渐释放的抽象动画。",
    "自信心": "镜子映照出的发光人影轮廓。",
    "抑郁预防": "从灰色到彩色的缓慢过渡效果。",
}


def build_video_prompt(content_item=None, template_name: str = "清新治愈",
                       duration: int = 15) -> str:
    tpl = TEMPLATES.get(template_name, TEMPLATES["清新治愈"])

    parts = [tpl["prompt_prefix"]]

    if content_item:
        cat = content_item.get("topic_category", "") if isinstance(content_item, dict) else getattr(content_item, "topic_category", "")
        sub = content_item.get("sub_category", "") if isinstance(content_item, dict) else getattr(content_item, "sub_category", "")
        theme = THEME_VISUALS.get(cat, "")
        sub_theme = SUBCATEGORY_KEYWORDS.get(sub, "")

        if theme:
            parts.append(f"画面主题元素：{theme}")
        if sub_theme:
            parts.append(f"细节元素：{sub_theme}")

    parts.append(f"整体视频时长约{duration}秒。")
    parts.append(f"9:16竖屏比例，1080x1920高清画质，画面中不包含任何文字或字幕。")
    parts.append(f"画面持续缓慢运动(如渐变、流动、粒子)，不要静止画面。无边框、无水印。")

    return "".join(parts)


def get_music(template_name: str) -> str:
    tpl = TEMPLATES.get(template_name, TEMPLATES["清新治愈"])
    return tpl.get("music", "light_piano")
