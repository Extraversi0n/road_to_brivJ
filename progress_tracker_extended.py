#!/usr/bin/env python3
# coding: utf-8

import os
import re
import sys
import json
import requests
import certifi
import locale
from pathlib import Path
from urllib.parse import urlparse, parse_qsl
from PIL import Image, ImageDraw, ImageFont as _IF
from datetime import datetime

# =========================
# PyInstaller helpers (EXE-safe)
# =========================
def resource_path(name: str) -> str:
    """Return path to bundled resource (icons, etc.), works in script and --onefile EXE."""
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return str(Path(base) / name)

def _set_cwd_to_app_dir():
    """Ensure default outputs (overlay, config) land next to the script/EXE."""
    try:
        base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        os.chdir(base)
    except Exception:
        pass

_set_cwd_to_app_dir()

# =========================
# Locale (numbers + percentages)
# =========================
try:
    locale.setlocale(locale.LC_ALL, "")  # user's OS locale
except Exception:
    pass

def fmt_int(n: int) -> str:
    """Format an integer with grouping per OS locale."""
    try:
        return locale.format_string("%d", int(n), grouping=True)
    except Exception:
        return f"{int(n)}"

# Percent display style: "dot" | "locale" | "int"
PERCENT_STYLE = "locale"

def percent_str(value, goal, style=PERCENT_STYLE):
    """Return a percent string with controlled decimal style (dot/locale/int)."""
    p = 100.0 if goal <= 0 else min(1.0, value / goal) * 100.0

    if style == "int":
        return f"{int(round(p))}%"

    # one decimal; trim trailing .0
    s = f"{p:.1f}"
    if s.endswith(".0"):
        s = s[:-2]

    if style == "locale":
        dec = locale.localeconv().get("decimal_point", ".") or "."
        s = s.replace(".", dec)
    else:
        s = s.replace(",", ".")  # force dot

    return s + "%"

# =========================
# CONFIG (Defaults)
# =========================
LOG_PATH    = r"C:/IdleChampions/IdleChampions/IdleDragons_Data/StreamingAssets/downloaded_files/webRequestLog.txt"
OUTPUT_PATH = "overlay_extended.png"
GOAL_BSC    = 15_360_005  # target in BSC units

FONT_MED_PATH   = "arial.ttf"
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
SHOW_SEG_SEPARATORS = False  # set True for thin dividers

# Colors
COLOR_GOLD      = (255, 215,   0)   # Gold
COLOR_SILVER    = (192, 192, 192)   # Silver
COLOR_GEMS      = (100, 200, 150)   # Gems = old BSC base green
COLOR_BSC_BASE  = ( 80, 170, 255)   # NEW BSC base color (distinct blue)

# English month names (stable regardless of OS locale)
MONTHS_EN = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

# =========================
# ALWAYS-SHOW SETUP DIALOG (with Skip)
# =========================
CONFIG_FILE = "tracker_config.json"

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def show_config_dialog(defaults: dict):
    """Show Tk dialog every run; 'Skip' uses saved defaults if available."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        # No Tk available? Just use defaults.
        return defaults or {}

    root = tk.Tk()
    root.title("IdleChamps Overlay – Settings")
    root.resizable(False, False)

    # Pre-fill with saved/default values or script defaults:
    v_log  = tk.StringVar(value=defaults.get("log_path", LOG_PATH))
    v_goal = tk.StringVar(value=str(defaults.get("goal_bsc", GOAL_BSC)))
    v_out  = tk.StringVar(value=defaults.get("output_path", OUTPUT_PATH))
    v_rem  = tk.BooleanVar(value=True)  # remember on Save & Run

    def pick_log():
        p = filedialog.askopenfilename(
            title="Select webRequestLog.txt",
            filetypes=[("webRequestLog.txt","webRequestLog.txt"), ("Text files","*.txt"), ("All files","*.*")]
        )
        if p: v_log.set(p)

    def pick_out():
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            v_out.set(os.path.join(d, "overlay_extended.png"))

    def validate_goal(text):
        try:
            return int(text.replace("_","").strip()) > 0
        except Exception:
            return False

    result = {}

    def do_run(save_it: bool):
        g = v_goal.get().strip()
        if not validate_goal(g):
            messagebox.showerror("Invalid goal", "Please enter a positive integer for BSC goal.")
            return
        cfg = {
            "log_path": v_log.get().strip(),
            "goal_bsc": int(g.replace("_","")),
            "output_path": v_out.get().strip()
        }
        if save_it and v_rem.get():
            save_config(cfg)
        result["cfg"] = cfg
        root.destroy()

    def do_skip():
        if not defaults:
            messagebox.showinfo("No saved settings", "No saved settings found yet.")
            return
        result["cfg"] = defaults
        root.destroy()

    def do_cancel():
        root.destroy()
        sys.exit(0)

    pad = {"padx": 10, "pady": 6}

    tk.Label(root, text="webRequestLog.txt:").grid(row=0, column=0, sticky="w", **pad)
    f0 = tk.Frame(root); f0.grid(row=0, column=1, sticky="we", **pad)
    e0 = tk.Entry(f0, textvariable=v_log, width=48); e0.pack(side="left", fill="x", expand=True)
    tk.Button(f0, text="Browse…", command=pick_log).pack(side="left", padx=6)

    tk.Label(root, text="BSC Goal:").grid(row=1, column=0, sticky="w", **pad)
    tk.Entry(root, textvariable=v_goal, width=20).grid(row=1, column=1, sticky="w", **pad)

    tk.Label(root, text="Output image:").grid(row=2, column=0, sticky="w", **pad)
    f2 = tk.Frame(root); f2.grid(row=2, column=1, sticky="we", **pad)
    e2 = tk.Entry(f2, textvariable=v_out, width=48); e2.pack(side="left", fill="x", expand=True)
    tk.Button(f2, text="Folder…", command=pick_out).pack(side="left", padx=6)

    tk.Checkbutton(root, text="Remember these settings", variable=v_rem).grid(row=3, column=1, sticky="w", **pad)

    bf = tk.Frame(root); bf.grid(row=4, column=0, columnspan=2, sticky="e", padx=10, pady=10)
    btn_skip = tk.Button(bf, text="Skip (use saved)", command=do_skip,
                         state=("normal" if defaults else "disabled"))
    btn_skip.pack(side="left", padx=4)
    tk.Button(bf, text="Run", command=lambda: do_run(save_it=False)).pack(side="left", padx=4)
    tk.Button(bf, text="Save & Run", command=lambda: do_run(save_it=True)).pack(side="left", padx=4)
    tk.Button(bf, text="Cancel", command=do_cancel).pack(side="left", padx=4)

    e0.focus_set()
    root.mainloop()

    return result.get("cfg", defaults or {})

# apply dialog (always shown)
_saved = load_config()
_cfg = show_config_dialog(_saved)

# override script defaults with chosen values
LOG_PATH    = _cfg.get("log_path", LOG_PATH)
OUTPUT_PATH = _cfg.get("output_path", OUTPUT_PATH)
GOAL_BSC    = int(_cfg.get("goal_bsc", GOAL_BSC))

# =========================
# Small helpers
# =========================
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

def _load_font(path, size):
    """Load a TTF if available; otherwise fall back to a safe default."""
    try:
        if path and os.path.exists(path):
            return _IF.truetype(path, size)
        # system fallbacks
        for p in (r"C:\Windows\Fonts\arial.ttf",
                  "/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.exists(p):
                return _IF.truetype(p, size)
    except Exception:
        pass
    return _IF.load_default()

# --- Single-line parsing helpers ---
def find_latest_getuserdetails_line(text):
    """Return the last log line that contains 'getuserdetails' (case-insensitive)."""
    for line in reversed(text.splitlines()):
        if "getuserdetails" in line.lower():
            return line
    return None

def extract_post_url_from_line(line):
    """Pull the exact .../post.php URL from the line, if present."""
    m = re.search(r'(https?://[^\s"\'<>]+/post\.php)', line, flags=re.I)
    return m.group(1) if m else None

def parse_kv_from_line(line):
    """
    Parse key/value pairs from a single log line:
    - JSON-like:   "key":"value" or "key":value
    - URL params:  ...?key=value&key2=value2
    - Plain pairs: key=value (stops at &, whitespace, quotes, <, >, #)
    Last occurrence wins.
    """
    out = {}

    # JSON-like "key":"value"
    for k, v in re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*"([^"]+)"', line):
        out[k] = v

    # JSON-like "key":value (unquoted)
    for k, v in re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*([A-Za-z0-9_.-]+)', line):
        out[k] = v

    # key=value plain
    for k, v in re.findall(r'([A-Za-z0-9_]+)\s*=\s*([^\s&"\'<>#]+)', line):
        out[k] = v

    # Any URLs? Parse their query strings too
    for url in re.findall(r'https?://[^\s"\'<>]+', line):
        try:
            q = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
            out.update(q)
        except Exception:
            pass

    return out

# =========================
# READ LOG & CALL API (single-line parse)
# =========================
with open(LOG_PATH, "r", encoding="utf-8") as f:
    log_text = f.read()

line = find_latest_getuserdetails_line(log_text)
if not line:
    raise Exception("Could not find a 'getuserdetails' line in webRequestLog.txt.")

# exact post.php URL (if present)
api_url = extract_post_url_from_line(line)
if not api_url:
    # Fallback: reconstruct from play_server on this line
    m = re.search(r'"play_server"\s*:\s*"([^"]+)"', line) or re.search(r'play_server\s*=\s*([^\s&"\'<>#]+)', line)
    if not m:
        raise Exception("Could not determine post.php URL or play_server from the line.")
    play_server = m.group(1).replace(r"\/", "/")
    if not play_server.endswith("/"):
        play_server += "/"
    api_url = f"{play_server}post.php"

# Parse kv from that single line
kv = parse_kv_from_line(line)

# Required values (last occurrence wins)
user_id = kv.get("user_id") or kv.get("internal_user_id")
hash_val = kv.get("hash") or kv.get("hashh")  # accept "hashh" if present
mcv      = kv.get("mobile_client_version") or "633"

if not user_id or not hash_val:
    raise Exception("user_id or hash not found on the latest getuserdetails line.")

params = {
    "call": "getuserdetails",
    "user_id": user_id,
    "hash": hash_val,
    "instance_key": kv.get("instance_key", "0"),
    "include_free_play_objectives": kv.get("include_free_play_objectives", "true"),
    "timestamp": kv.get("timestamp", "0"),
    "request_id": kv.get("request_id", "0"),
    "language_id": kv.get("language_id", "1"),
    "network_id": kv.get("network_id", "21"),
    "mobile_client_version": mcv,
    "localization_aware": kv.get("localization_aware", "true"),
}
headers = {"User-Agent": "Mozilla/5.0"}

# Console-safe print (no emoji crash on cp1252)
try:
    print("🔍 API:", api_url)
except UnicodeEncodeError:
    print("API:", api_url)

# Use POST (avoid 414; matches post.php semantics)
resp = requests.post(api_url, data=params, headers=headers, timeout=30, verify=certifi.where())
if resp.status_code != 200 or not resp.text.strip().startswith("{"):
    snippet = resp.text[:200].replace("\n", " ")
    raise Exception(f"Invalid API response: {resp.status_code} | {snippet}")
data = resp.json()

# =========================
# VALUES & CONVERSIONS
# =========================
chests = data.get("details", {}).get("chests", {})
gold   = safe_int(chests.get("2", 0))                         # gold chests
silver = safe_int(chests.get("1", 0))                         # silver chests
gems   = safe_int(get_nested(data, "details.red_rubies", 0))  # gems

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
    if not buff_list: return 0, {}
    breakdown = {k: 0 for k in BSC_WEIGHTS.keys()}
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

# Convert current resources into BSC units (for the stacked bar & legend)
bsc_from_gold   = gold               # 1 gold = 1 BSC
bsc_from_silver = silver // 10       # 10 silver = 1 BSC
bsc_from_gems   = gems // 500        # 500 gems = 1 BSC

# Overall remaining BSC after ALL contributions (for the stacked bar)
R_overall = max(GOAL_BSC - (bsc_base + bsc_from_gold + bsc_from_silver + bsc_from_gems), 0)

# Per-resource goals in units: overall remaining + add back own contribution
gold_goal_units   = (R_overall + bsc_from_gold)   * 1
silver_goal_units = (R_overall + bsc_from_silver) * 10
gems_goal_units   = (R_overall + bsc_from_gems)   * 500

# =========================
# DRAW
# =========================
img_h = PADDING*2 + 4*ROW_HEIGHT + 40
img = Image.new("RGBA", (IMG_WIDTH, img_h), (0,0,0,0))
draw = ImageDraw.Draw(img)

font_med   = _load_font(FONT_MED_PATH, 21)
font_small = _load_font(FONT_SMALL_PATH, 15)

# Date only (e.g., "29 September 2025")
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

# Use resource_path so icons load in EXE
icon_gold   = try_icon(resource_path("goldtruhe_icon.png"))
icon_silver = try_icon(resource_path("silbertruhe_icon.png"))
icon_gems   = try_icon(resource_path("gems_icon.png"))
icon_bsc    = try_icon(resource_path("blacksmithcontract_icon.png"))

def draw_progress_block(y, value, goal, icon, bar_color, title="", meta_suffix=""):
    """Generic bar with spacing and outline; title shows %; meta shows Remaining/Goal (localized)."""
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
    pct = percent_str(value, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + BAR_WIDTH - w, title_y), pct, font=font_small, fill=(220, 220, 220))

    # meta line (localized ints)
    remaining_units = max(goal - value, 0)
    meta = f"Remaining: {fmt_int(remaining_units)} • Goal: {fmt_int(goal)}{meta_suffix}"
    draw.text((bar_x, bar_y + BAR_HEIGHT + 4), meta, font=font_small, fill=(210,210,210))

def draw_stacked_bsc_block(y, segments, goal, title, icon=None):
    """Stacked BSC bar; title shows %; legend lists BSC values (localized)."""
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
    pct = percent_str(total_bsc, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + bar_w - w, title_y), pct, font=font_small, fill=(220,220,220))

    # simplified legend (localized BSC values)
    labels = [f"{lbl} {fmt_int(val)}" for lbl, val, _ in segments]
    legend = " | ".join(labels)
    draw.text((bar_x, bar_y + bar_h + LEGEND_GAP), legend, font=font_small, fill=(210,210,210))

    # remaining + goal under legend (localized)
    remaining = max(goal - total_bsc, 0)
    meta = f"Remaining: {fmt_int(remaining)} • Goal: {fmt_int(goal)}"
    draw.text((bar_x, bar_y + bar_h + LEGEND_GAP + 18), meta, font=font_small, fill=(200,200,200))

# Build stacked segments (BSC units)
segments = [
    ("BSC",   bsc_base,        COLOR_BSC_BASE),
    ("Gold",  bsc_from_gold,   COLOR_GOLD),
    ("Silver",bsc_from_silver, COLOR_SILVER),
    ("Gems",  bsc_from_gems,   COLOR_GEMS),
]

# Draw bars
y0 = 26
draw_progress_block(y0 + 0*ROW_HEIGHT, gold,   gold_goal_units,   icon_gold,   COLOR_GOLD,
                    title="Gold-Chests",   meta_suffix=" (1 = 1 BSC)")
draw_progress_block(y0 + 1*ROW_HEIGHT, silver, silver_goal_units, icon_silver, COLOR_SILVER,
                    title="Silver-Chests", meta_suffix=" (10 = 1 BSC)")
draw_progress_block(y0 + 2*ROW_HEIGHT, gems,   gems_goal_units,   icon_gems,   COLOR_GEMS,
                    title="Gems",          meta_suffix=" (500 = 1 BSC)")
draw_stacked_bsc_block(y0 + 3*ROW_HEIGHT, segments, GOAL_BSC, "Blacksmith Contracts", icon=icon_bsc)

# Save
img.save(OUTPUT_PATH)
print(f"✅ Overlay saved as {OUTPUT_PATH}")
