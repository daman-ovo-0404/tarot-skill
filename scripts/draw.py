#!/usr/bin/env python3
"""
塔罗牌抽牌脚本 — 实现 SKILL.md 定义的完整抽牌算法。

用法:
  python3 draw.py --spread single
  python3 draw.py --spread three --question "事业方向"
  python3 draw.py --spread celtic --question "感情" --seed 12345
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# 脚本自身所在目录（不依赖调用路径，适配任意安装位置）
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# ─── 78 张牌定义（与 cards.md 标题完全一致） ───

MAJOR_ARCANA = [
    "愚者", "魔术师", "女祭司", "女皇", "皇帝", "教皇", "恋人", "战车",
    "力量", "隐士", "命运之轮", "正义", "倒吊人", "死神", "节制", "恶魔",
    "高塔", "星星", "月亮", "太阳", "审判", "世界",
]

SUITS = {
    "权杖": "火",
    "圣杯": "水",
    "宝剑": "风",
    "星币": "土",
}

RANKS = ["Ace", "二", "三", "四", "五", "六", "七", "八", "九", "十",
         "侍从", "骑士", "皇后", "国王"]

MINOR_ARCANA = [f"{suit}{rank}" for suit in SUITS for rank in RANKS]

ALL_CARDS = MAJOR_ARCANA + MINOR_ARCANA  # 22 + 56 = 78

# 大阿卡纳的元素归属（用于时段因子）
MAJOR_ELEMENT = {
    "愚者": "风", "魔术师": "风", "女祭司": "水", "女皇": "土",
    "皇帝": "火", "教皇": "土", "恋人": "风", "战车": "水",
    "力量": "火", "隐士": "土", "命运之轮": "火", "正义": "风",
    "倒吊人": "水", "死神": "水", "节制": "火", "恶魔": "土",
    "高塔": "火", "星星": "风", "月亮": "水", "太阳": "火",
    "审判": "火", "世界": "土",
}

# ─── 牌阵定义（与 spreads.md 一致） ───

SPREADS = {
    "single": {
        "name": "单张牌",
        "positions": [
            {"name": "当前指引", "key_position": True},
        ],
    },
    "three": {
        "name": "三牌阵",
        "positions": [
            {"name": "过去", "key_position": False},
            {"name": "现在", "key_position": True},
            {"name": "未来", "key_position": False, "favor_upright": True},
        ],
    },
    "diamond": {
        "name": "五牌阵",
        "positions": [
            {"name": "核心", "key_position": True},
            {"name": "根源", "key_position": False},
            {"name": "阻力", "key_position": False},
            {"name": "潜力", "key_position": False},
            {"name": "建议", "key_position": True, "favor_upright": True},
        ],
    },
    "moon": {
        "name": "月亮牌阵",
        "positions": [
            {"name": "新月", "key_position": True},
            {"name": "上弦", "key_position": False},
            {"name": "满月", "key_position": True},
            {"name": "下弦", "key_position": False},
        ],
    },
    "horseshoe": {
        "name": "马蹄形",
        "positions": [
            {"name": "远期过去", "key_position": False},
            {"name": "近期过去", "key_position": False},
            {"name": "当前", "key_position": True},
            {"name": "近期未来", "key_position": False},
            {"name": "外部影响", "key_position": True},
            {"name": "建议", "key_position": False, "favor_upright": True},
            {"name": "结果", "key_position": True, "favor_upright": True},
        ],
    },
    "celtic": {
        "name": "凯尔特十字",
        "positions": [
            {"name": "核心", "key_position": True},
            {"name": "交叉", "key_position": False},
            {"name": "意识目标", "key_position": False},
            {"name": "根基过去", "key_position": False},
            {"name": "近期过去", "key_position": True},
            {"name": "近期未来", "key_position": False},
            {"name": "自我", "key_position": False},
            {"name": "环境", "key_position": False},
            {"name": "希望与恐惧", "key_position": False},
            {"name": "结果", "key_position": True, "favor_upright": True},
        ],
    },
}

# ─── 时段因子 ───

def get_time_factor():
    """根据当前小时返回时段及受 +8% 加成的元素列表。"""
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return "morning", ["火", "风"]
    elif 12 <= hour < 18:
        return "afternoon", ["水", "土"]
    else:
        return "night", ["major"]  # 夜晚加成大阿卡纳整体


def card_element(card_name: str) -> str | None:
    """返回牌的元素；大阿卡纳返回其对应元素，小阿卡纳返回花色元素。"""
    if card_name in MAJOR_ELEMENT:
        return MAJOR_ELEMENT[card_name]
    for suit, element in SUITS.items():
        if card_name.startswith(suit):
            return element
    return None


# ─── 抽牌核心 ───

def draw_cards(spread_key: str, question: str, seed: int | None = None):
    if spread_key not in SPREADS:
        print(f"错误：未知牌阵 '{spread_key}'", file=sys.stderr)
        print(f"可选：{', '.join(SPREADS.keys())}", file=sys.stderr)
        sys.exit(1)

    spread = SPREADS[spread_key]
    positions = spread["positions"]

    if seed is None:
        raw = hashlib.sha256(f"{time.time_ns()}{question}".encode()).hexdigest()
        seed = int(raw[:16], 16)

    rng = random.Random(seed)
    time_factor_name, boosted = get_time_factor()
    pool = list(ALL_CARDS)
    drawn = []

    for i, pos in enumerate(positions):
        is_key = pos.get("key_position", False)
        favor_upright = pos.get("favor_upright", False)

        weights = []
        for card in pool:
            is_major = card in MAJOR_ARCANA
            w = 1.0

            # 位置权重：关键位置大阿卡纳 60%，普通位置 28%
            if is_key and is_major:
                w *= 60 / 28  # ~2.14x
            elif not is_key and is_major:
                w *= 1.0  # 自然概率

            # 时段因子 +8%
            elem = card_element(card)
            if "major" in boosted and is_major:
                w *= 1.08
            elif elem in boosted:
                w *= 1.08

            weights.append(w)

        chosen_idx = rng.choices(range(len(pool)), weights=weights, k=1)[0]
        chosen_card = pool.pop(chosen_idx)

        # 正逆位
        upright_prob = 0.70 if favor_upright else 0.60
        orientation = "正位" if rng.random() < upright_prob else "逆位"

        drawn.append({
            "position": pos["name"],
            "card": chosen_card,
            "orientation": orientation,
            "is_major": chosen_card in MAJOR_ARCANA,
        })

    return {
        "seed": seed,
        "spread": spread_key,
        "spread_name": spread["name"],
        "question": question,
        "time_factor": time_factor_name,
        "cards": drawn,
    }


# ─── 人类可读输出 ───

TIME_FACTOR_LABEL = {
    "morning": "早晨（火/风元素活跃期）",
    "afternoon": "午后（水/土元素活跃期）",
    "night": "夜晚（灵性/潜意识活跃期）",
}

def print_human_readable(result: dict):
    print(f"\n{'=' * 40}")
    print(f"🔮 {result['spread_name']}")
    if result["question"]:
        print(f"❓ 问题：{result['question']}")
    print(f"🕐 时段：{TIME_FACTOR_LABEL[result['time_factor']]}")
    print(f"🌱 种子：{result['seed']}")
    print(f"{'=' * 40}\n")

    for c in result["cards"]:
        arrow = "⬆️" if c["orientation"] == "正位" else "⬇️"
        major_tag = " [大阿卡纳]" if c["is_major"] else ""
        print(f"  {c['position']:　<8} 🃏 {c['card']} {arrow}{c['orientation']}{major_tag}")

    print()


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="塔罗牌抽牌脚本")
    parser.add_argument("--spread", required=True, choices=SPREADS.keys(),
                        help="牌阵类型")
    parser.add_argument("--question", default="", help="问卜问题（可选）")
    parser.add_argument("--seed", type=int, default=None,
                        help="指定随机种子（用于复现）")
    parser.add_argument("--json-only", action="store_true",
                        help="仅输出 JSON，不输出人类可读文本")
    args = parser.parse_args()

    result = draw_cards(args.spread, args.question, args.seed)

    if not args.json_only:
        print_human_readable(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
