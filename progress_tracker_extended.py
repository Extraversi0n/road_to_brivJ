#!/usr/bin/env python3
# coding: utf-8

import os
import re
import json
import requests
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# === CONFIG ===
LOG_PATH = r"C:/IdleChampions/IdleChampions/IdleDragons_Data/StreamingAssets/downloaded_files/webRequestLog.txt"
OUTPUT_PATH = "overlay_extended.png"

FONT_MED_PATH = "arial.ttf"
FONT_SMALL_PATH = "arial.ttf"

IMG_WIDTH   = 950
ROW_HEIGHT  = 84
PADDING     = 16
ICON_SIZE   = (56, 56)
BAR_WIDTH   = 520
BAR_HEIGHT  = 22

# Spacing & styling
TITLE_BAR_GAP = 10
LEGEND_GAP    = 6
BAR_OUTLINE   = (58, 58, 58)
SEGMENT_SEPARATOR = (25, 25, 25)
SHOW_SEG_SEPARATORS = False  # can set True for thin dividers

# Colors
COLOR_GOLD      = (255, 215,   0)   # Gold
COLOR_SILVER    = (192, 192, 192)   # Silver
COLOR_GEMS      = (100, 200, 150)   # Gems = old BSC base green
COLOR_BSC_BASE  = ( 80, 170, 255)   # NEW BSC base color (distinct blue)


# English month names (stable regardless of OS locale)
MONTHS_EN = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

# Goals
GOAL_BSC    = 15_360_005   # target in BSC units

# === UTILS ===
def extract_value(text, key):
    lines = text.strip().splitlines()[::-1]
    for line in lines:
        m = re.search(rf'{re.escape(key)}=([^&\n]+)', line)
        if m:
            return m.group(1)
    return None

def extract_value_json(text, key):
    lines = text.strip().splitlines()[::-1]
    for line in lines:
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    return None

def extract_mobile_client_version(text, default="633"):
    """Find latest mobile_client_version in the raw log (supports JSON and key=value)."""
    candidates = []
    for m in re.finditer(r'"mobile_client_version"\s*:\s*"(\d+)"', text): candidates.append(m.group(1))
    for m in re.finditer(r'"mobile_client_version"\s*:\s*(\d+)', text):  candidates.append(m.group(1))
    for m in re.finditer(r'\bmobile_client_version=([0-9]+)', text):      candidates.append(m.group(1))
    return candidates[-1] if candidates else default

def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return default

def get_nested(d, path, default=None):
    cur = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur

def _percent(value, goal):
    # If nothing is needed from this resource, treat it as complete.
    if goal <= 0:
        return "100%"
    p = min(1.0, value / goal) * 100.0
    s = f"{p:.1f}%"
    return s[:-3] + "%" if s.endswith(".0%") else s

# === READ LOG & CALL API ===
with open(LOG_PATH, "r", encoding="utf-8") as f:
    log = f.read()

play_server = extract_value_json(log, "play_server") or extract_value(log, "play_server")
if play_server:
    play_server = play_server.replace(r"\/", "/")

user_id = extract_value_json(log, "internal_user_id") or extract_value(log, "internal_user_id")
hash_val = extract_value(log, "hash")
mcv = extract_mobile_client_version(log, default="633")

if not all([play_server, user_id, hash_val]):
    raise Exception("❌ play_server, internal_user_id or hash not found in log!")

api_url = f"{play_server}post.php"
params = {
    "call": "getuserdetails",
    "user_id": user_id,
    "hash": hash_val,
    "instance_key": "0",
    "include_free_play_objectives": "true",
    "timestamp": "0",
    "request_id": "0",
    "language_id": "1",
    "network_id": "21",
    "mobile_client_version": mcv,   # dynamic from log
    "localization_aware": "true"
}
headers = {"User-Agent": "Mozilla/5.0"}

print("🔍 API:", api_url)
resp = requests.get(api_url, params=params, headers=headers, timeout=30)
if resp.status_code != 200 or not resp.text.strip().startswith("{"):
    raise Exception(f"Invalid API response: {resp.status_code}")
data = resp.json()

# === VALUES ===
chests = data.get("details", {}).get("chests", {})
gold   = safe_int(chests.get("2", 0))                  # gold chests (units)
silver = safe_int(chests.get("1", 0))                  # silver chests (units)
gems   = safe_int(get_nested(data, "details.red_rubies", 0))  # gems (units)

# Base BSC from contract buffs
BSC_WEIGHTS = {31:1, 32:2, 33:6, 34:24, 1797:120}

def find_contract_buffs_anywhere(obj):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and 'buff_id' in obj[0] and 'inventory_amount' in obj[0]:
            return obj
        for item in obj:
            res = find_contract_buffs_anywhere(item)
            if res: return res
    elif isinstance(obj, dict):
        for v in obj.values():
            res = find_contract_buffs_anywhere(v)
            if res: return res
    return None

def compute_bsc_from_buffs(json_data):
    buff_list = find_contract_buffs_anywhere(json_data)
    total = 0
    breakdown = {k: 0 for k in BSC_WEIGHTS.keys()}
    if not buff_list: return 0, breakdown
    for entry in buff_list:
        try:
            b_id = int(entry.get("buff_id", -1))
            amt  = int(entry.get("inventory_amount", 0))
        except Exception:
            continue
        if b_id in BSC_WEIGHTS and amt > 0:
            total += amt * BSC_WEIGHTS[b_id]
            breakdown[b_id] += amt
    return total, breakdown

bsc_base, _b = compute_bsc_from_buffs(data)

# Projection to BSC units (for the stacked bar & legend)
bsc_from_gold   = gold               # 1 gold chest = 1 BSC
bsc_from_silver = silver // 10       # 10 silver = 1 BSC
bsc_from_gems   = gems // 500        # 500 gems = 1 BSC

# --- per-resource goals: exclude this resource's own contribution
gold_needed_bsc   = max(GOAL_BSC - (bsc_base + bsc_from_silver + bsc_from_gems), 0)
silver_needed_bsc = max(GOAL_BSC - (bsc_base + bsc_from_gold   + bsc_from_gems), 0)
gems_needed_bsc   = max(GOAL_BSC - (bsc_base + bsc_from_gold   + bsc_from_silver), 0)

gold_goal_units   = gold_needed_bsc * 1      # 1 gold chest = 1 BSC
silver_goal_units = silver_needed_bsc * 10   # 10 silver = 1 BSC
gems_goal_units   = gems_needed_bsc * 500    # 500 gems = 1 BSC


# === DRAW ===
img_h = PADDING*2 + 4*ROW_HEIGHT + 40
img = Image.new("RGBA", (IMG_WIDTH, img_h), (0,0,0,0))
draw = ImageDraw.Draw(img)

font_med   = ImageFont.truetype(FONT_MED_PATH, 21)
font_small = ImageFont.truetype(FONT_SMALL_PATH, 15)

# Date only (e.g., "28 September 2025")
now = datetime.now()
date_str = f"{now.day} {MONTHS_EN[now.month]} {now.year}"
draw.text((PADDING, 6), date_str, font=font_small, fill=(180, 180, 180))

def try_icon(path):
    if path and os.path.exists(path):
        try:
            return Image.open(path).convert("RGBA").resize(ICON_SIZE)
        except Exception:
            return None
    return None

icon_gold   = try_icon("goldtruhe_icon.png")
icon_silver = try_icon("silbertruhe_icon.png")
icon_gems   = try_icon("gems_icon.png")
icon_bsc    = try_icon("blacksmithcontract_icon.png")

def draw_progress_block(y, value, goal, icon, bar_color, title="", meta_suffix=""):
    """Generic bar with spacing and outline; title line shows % to goal; meta line shows Remaining/Goal."""
    bar_x = PADDING + (ICON_SIZE[0] + 10 if icon else 0)
    title_y = y
    title_h = 0
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_med)
        title_h = bbox[3] - bbox[1]
    bar_y = y + title_h + TITLE_BAR_GAP

    # background + outline
    draw.rectangle([bar_x, bar_y, bar_x + BAR_WIDTH, bar_y + BAR_HEIGHT], fill=(40, 40, 40))
    draw.rectangle([bar_x, bar_y, bar_x + BAR_WIDTH - 1, bar_y + BAR_HEIGHT - 1], outline=BAR_OUTLINE, width=1)

    # fill
    frac = 0 if goal <= 0 else min(value / goal, 1.0)
    fill_w = int(BAR_WIDTH * frac)
    if fill_w > 0:
        draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + BAR_HEIGHT], fill=bar_color)

    # icon
    if icon:
        img.paste(icon, (PADDING, y + (ROW_HEIGHT - ICON_SIZE[1]) // 2), icon)

    # title + percent
    if title:
        draw.text((bar_x, title_y), title, font=font_med, fill=(255, 255, 255))
    pct = _percent(value, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + BAR_WIDTH - w, title_y), pct, font=font_small, fill=(220, 220, 220))

    # meta line
    remaining_units = max(goal - value, 0)
    meta = f"Remaining: {remaining_units:,} • Goal: {goal:,}{meta_suffix}".replace(",", ".")
    draw.text((bar_x, bar_y + BAR_HEIGHT + 4), meta, font=font_small, fill=(210,210,210))

def draw_stacked_bsc_block(y, segments, goal, title, icon=None):
    """Stacked BSC bar; title line shows %; legend lists BSC values only."""
    bar_x = PADDING + (ICON_SIZE[0] + 10 if icon else 0)
    title_y = y
    title_h = 0
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_med)
        title_h = bbox[3] - bbox[1]
    bar_y = y + title_h + TITLE_BAR_GAP
    bar_w, bar_h = BAR_WIDTH, BAR_HEIGHT

    # background + outline
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(40,40,40))
    draw.rectangle([bar_x, bar_y, bar_x + bar_w - 1, bar_y + bar_h - 1], outline=BAR_OUTLINE, width=1)

    # stacked fill
    used_px = 0
    total_bsc = sum(v for _, v, _ in segments)
    for _, val, color in segments:
        if goal <= 0 or val <= 0:
            continue
        remaining_px = bar_w - used_px
        seg_w = int(round(bar_w * (val / goal)))
        if seg_w > remaining_px: seg_w = remaining_px
        if seg_w <= 0 and remaining_px > 0: seg_w = 1
        draw.rectangle([bar_x + used_px, bar_y, bar_x + used_px + seg_w, bar_y + bar_h], fill=color)
        used_px += seg_w
        if SHOW_SEG_SEPARATORS and used_px < bar_w:
            draw.line([(bar_x + used_px, bar_y), (bar_x + used_px, bar_y + bar_h)], fill=SEGMENT_SEPARATOR, width=1)
        if used_px >= bar_w:
            break

    # icon
    if icon:
        img.paste(icon, (PADDING, y + (ROW_HEIGHT - ICON_SIZE[1]) // 2), icon)

    # title + % on title line
    if title:
        draw.text((bar_x, title_y), title, font=font_med, fill=(255,255,255))
    pct = _percent(total_bsc, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + bar_w - w, title_y), pct, font=font_small, fill=(220,220,220))

    # simplified legend (BSC values)
    labels = [f"{lbl} {val:,}".replace(",", ".") for lbl, val, _ in segments]  # "BSC 123 | Gold 45 | Silver 67 | Gems 89"
    legend = " | ".join(labels)
    draw.text((bar_x, bar_y + bar_h + LEGEND_GAP), legend, font=font_small, fill=(210,210,210))

    # remaining + goal under legend
    remaining = max(goal - total_bsc, 0)
    meta = f"Remaining: {remaining:,} • Goal: {goal:,}".replace(",", ".")
    draw.text((bar_x, bar_y + bar_h + LEGEND_GAP + 18), meta, font=font_small, fill=(200,200,200))

# === DRAW BARS ===
y0 = 26

# Build stacked BSC segments (values are in BSC units)
segments = [
    ("BSC",   bsc_base,        COLOR_BSC_BASE),  # <-- neue BSC-Base-Farbe
    ("Gold",  bsc_from_gold,   COLOR_GOLD),
    ("Silver",bsc_from_silver, COLOR_SILVER),
    ("Gems",  bsc_from_gems,   COLOR_GEMS),      # <-- Gems = grün (wie alte Base)
]

# Resource bars now show how many UNITS you have vs how many UNITS are needed to close remaining BSC
# Add a short suffix to clarify unit→BSC factor.
draw_progress_block(y0 + 0*ROW_HEIGHT, gold,   gold_goal_units,   icon_gold,   COLOR_GOLD,
                    title="Gold-Chests",   meta_suffix=" (1 = 1 BSC)")
draw_progress_block(y0 + 1*ROW_HEIGHT, silver, silver_goal_units, icon_silver, COLOR_SILVER,
                    title="Silver-Chests", meta_suffix=" (10 = 1 BSC)")
draw_progress_block(y0 + 2*ROW_HEIGHT, gems,   gems_goal_units,   icon_gems,   COLOR_GEMS,
                    title="Gems",          meta_suffix=" (500 = 1 BSC)")

draw_stacked_bsc_block(y0 + 3*ROW_HEIGHT, segments, GOAL_BSC, "Blacksmith Contracts", icon=icon_bsc)

# === SAVE ===
img.save(OUTPUT_PATH)
print(f"✅ Overlay saved as {OUTPUT_PATH}")
