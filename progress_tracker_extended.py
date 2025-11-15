#!/usr/bin/env python3
# coding: utf-8

import os
import re
import sys
import json
import gzip
import struct
import locale
import argparse
import requests
import certifi
from pathlib import Path
from urllib.parse import urlparse, parse_qsl
from datetime import datetime
from typing import Optional
from PIL import Image, ImageDraw, ImageFont as _IF

# ========= Working dir (EXE/script) =========
def _set_cwd_to_app_dir():
    try:
        base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        os.chdir(base)
    except Exception:
        pass
_set_cwd_to_app_dir()

# App dir + local cache dir (next to script/exe)
from pathlib import Path as _PathAlias
APP_DIR = _PathAlias.cwd()
ICON_CACHE_DIR = APP_DIR / "overlay_icon_cache"

# ========= Locale formatting =========
try:
    locale.setlocale(locale.LC_ALL, "")
except Exception:
    pass

def fmt_int(n: int) -> str:
    try:
        return locale.format_string("%d", int(n), grouping=True)
    except Exception:
        return f"{int(n)}"

# Percent display style: "locale" | "dot" | "int"
PERCENT_STYLE = "locale"

def percent_str(value, goal, style=PERCENT_STYLE):
    p = 100.0 if goal <= 0 else min(1.0, (value / goal)) * 100.0
    if style == "int":
        return f"{int(round(p))}%"
    s = f"{p:.2f}"  # two decimals
    if style == "locale":
        dec = locale.localeconv().get("decimal_point", ".") or "."
        s = s.replace(".", dec)
    else:  # "dot"
        s = s.replace(",", ".")
    return s + "%"

# ========= Defaults =========
LOG_PATH    = r"C:/IdleChampions/IdleChampions/IdleDragons_Data/StreamingAssets/downloaded_files/webRequestLog.txt"
OUTPUT_PATH = "overlay_extended.png"
GOAL_BSC    = 15_360_005

FONT_MED_PATH   = "arial.ttf"
FONT_SMALL_PATH = "arial.ttf"

IMG_WIDTH   = 950
ROW_HEIGHT  = 84
PADDING     = 16
ICON_SIZE   = (56, 56)
BAR_WIDTH   = 520
BAR_HEIGHT  = 22

TITLE_BAR_GAP = 10
LEGEND_GAP    = 6
BAR_OUTLINE   = (58, 58, 58)
SEGMENT_SEPARATOR = (25, 25, 25)
SHOW_SEG_SEPARATORS = False

# Colors
COLOR_GOLD      = (255, 215,   0)
COLOR_SILVER    = (192, 192, 192)
COLOR_GEMS      = (100, 200, 150)
COLOR_BSC_BASE  = ( 80, 170, 255)

MONTHS_EN = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

# ========= CLI (headless etc.) =========
def parse_cli_args():
    p = argparse.ArgumentParser(description="IdleChamps BSC overlay")
    p.add_argument("--headless", action="store_true", help="run without GUI dialog")
    p.add_argument("--log-path")
    p.add_argument("--output")
    p.add_argument("--goal-bsc", type=int)
    p.add_argument("--user-id")
    p.add_argument("--hash")
    p.add_argument("--mcv")
    p.add_argument("--api-url")
    p.add_argument("--percent-style", choices=["locale","dot","int"])
    return p.parse_args()

# ========= Config file =========
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

# ========= Log-line parsing =========
def find_latest_getuserdetails_line(text: str) -> Optional[str]:
    for line in reversed(text.splitlines()):
        if "getuserdetails" in line.lower():
            return line
    return None

def extract_post_url_from_line(line: str) -> Optional[str]:
    m = re.search(r'(https?://[^\s"\'<>]+/post\.php)', line, flags=re.I)
    return m.group(1) if m else None

def parse_kv_from_line(line: str) -> dict:
    out = {}
    # JSON-ish "k":"v"
    for k, v in re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*"([^"]+)"', line):
        out[k] = v
    # JSON-ish "k":123
    for k, v in re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*([A-Za-z0-9_.-]+)', line):
        out[k] = v
    # key=value pairs
    for k, v in re.findall(r'([A-Za-z0-9_]+)\s*=\s*([^\s&"\'<>#]+)', line):
        out[k] = v
    # query params inside URLs
    for url in re.findall(r'https?://[^\s"\'<>]+', line):
        try:
            q = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
            out.update(q)
        except Exception:
            pass
    return out

# ========= GUI (unless headless) =========
def show_config_dialog(defaults: dict):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        return defaults or {}

    root = tk.Tk()
    root.title("IdleChamps Overlay – Settings")
    root.resizable(False, False)

    v_log   = tk.StringVar(value=defaults.get("log_path", LOG_PATH))
    v_goal  = tk.StringVar(value=str(defaults.get("goal_bsc", GOAL_BSC)))
    v_out   = tk.StringVar(value=defaults.get("output_path", OUTPUT_PATH))
    v_uid   = tk.StringVar(value=defaults.get("user_id_override", ""))
    v_hash  = tk.StringVar(value=defaults.get("hash_override", ""))
    v_mcv   = tk.StringVar(value=defaults.get("mcv_override", ""))
    v_api   = tk.StringVar(value=defaults.get("api_url_override", ""))
    v_rem   = tk.BooleanVar(value=True)
    v_save_creds = tk.BooleanVar(value=False)
    v_show_hash  = tk.BooleanVar(value=False)

    def pick_log():
        p = filedialog.askopenfilename(
            title="Select webRequestLog.txt",
            filetypes=[("webRequestLog.txt","webRequestLog.txt"), ("Text files","*.txt"), ("All files","*.*")]
        )
        if p: v_log.set(p)

    def pick_out():
        d = filedialog.askdirectory(title="Select output folder")
        if d: v_out.set(os.path.join(d, "overlay_extended.png"))

    def extract_from_log():
        try:
            with open(v_log.get().strip(), "r", encoding="utf-8") as f:
                text = f.read()
            line = find_latest_getuserdetails_line(text)
            if not line:
                messagebox.showerror("Not found", "No 'getuserdetails' entry found.")
                return
            kv = parse_kv_from_line(line)
            api = extract_post_url_from_line(line)
            if not api:
                m = re.search(r'"play_server"\s*:\s*"([^"]+)"', line) or re.search(r'play_server\s*=\s*([^\s&"\'<>#]+)', line)
                if m:
                    ps = m.group(1).replace(r"\/", "/")
                    if not ps.endswith("/"):
                        ps += "/"
                    api = f"{ps}post.php"
            if kv.get("user_id") or kv.get("internal_user_id"):
                v_uid.set(kv.get("user_id") or kv.get("internal_user_id"))
            if kv.get("hash") or kv.get("hashh"):
                v_hash.set(kv.get("hash") or kv.get("hashh"))
            if kv.get("mobile_client_version"):
                v_mcv.set(kv.get("mobile_client_version"))
            if api:
                v_api.set(api)
            messagebox.showinfo("Extracted", "Values extracted from latest getuserdetails line.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to extract:\n{e}")

    def validate_goal(text):
        try:
            return int(text.replace("_","").strip()) > 0
        except Exception:
            return False

    result = {}

    def do_run(save_it: bool):
        g = v_goal.get().strip()
        if not validate_goal(g):
            from tkinter import messagebox
            messagebox.showerror("Invalid goal", "Please enter a positive integer for BSC goal.")
            return
        cfg = {
            "log_path": v_log.get().strip(),
            "goal_bsc": int(g.replace("_","")),
            "output_path": v_out.get().strip(),
            "user_id_override": v_uid.get().strip(),
            "hash_override": v_hash.get().strip(),
            "mcv_override": v_mcv.get().strip(),
            "api_url_override": v_api.get().strip(),
        }
        if save_it and v_rem.get():
            to_save = cfg.copy()
            if not v_save_creds.get():
                to_save["user_id_override"] = ""
                to_save["hash_override"] = ""
            save_config(to_save)
        result["cfg"] = cfg
        root.destroy()

    def do_skip():
        if not defaults:
            from tkinter import messagebox
            messagebox.showinfo("No saved settings", "No saved settings found yet.")
            return
        result["cfg"] = defaults
        root.destroy()

    def toggle_hash_show():
        e_hash.configure(show="" if v_show_hash.get() else "•")

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

    tk.Label(root, text="— Overrides (optional) —").grid(row=3, column=0, columnspan=2, sticky="w", padx=10)

    tk.Label(root, text="user_id:").grid(row=4, column=0, sticky="w", **pad)
    tk.Entry(root, textvariable=v_uid, width=28).grid(row=4, column=1, sticky="w", **pad)

    tk.Label(root, text="hash:").grid(row=5, column=0, sticky="w", **pad)
    e_hash = tk.Entry(root, textvariable=v_hash, width=28, show="•")
    e_hash.grid(row=5, column=1, sticky="w", **pad)
    tk.Checkbutton(root, text="show", variable=v_show_hash, command=toggle_hash_show).grid(row=5, column=1, sticky="e", padx=10)

    tk.Label(root, text="mobile_client_version:").grid(row=6, column=0, sticky="w", **pad)
    tk.Entry(root, textvariable=v_mcv, width=28).grid(row=6, column=1, sticky="w", **pad)

    tk.Label(root, text="post.php URL:").grid(row=7, column=0, sticky="w", **pad)
    tk.Entry(root, textvariable=v_api, width=48).grid(row=7, column=1, sticky="w", **pad)

    f8 = tk.Frame(root); f8.grid(row=8, column=0, columnspan=2, sticky="we", padx=10, pady=4)
    tk.Button(f8, text="Extract from log", command=extract_from_log).pack(side="left")
    tk.Checkbutton(f8, text="Remember settings", variable=v_rem).pack(side="left", padx=12)
    tk.Checkbutton(f8, text="Save user_id/hash to config", variable=v_save_creds).pack(side="left", padx=12)

    bf = tk.Frame(root); bf.grid(row=9, column=0, columnspan=2, sticky="e", padx=10, pady=10)
    btn_skip = tk.Button(bf, text="Skip (use saved)", command=do_skip, state=("normal" if defaults else "disabled"))
    btn_skip.pack(side="left", padx=4)
    tk.Button(bf, text="Run", command=lambda: do_run(save_it=False)).pack(side="left", padx=4)
    tk.Button(bf, text="Save & Run", command=lambda: do_run(save_it=True)).pack(side="left", padx=4)
    tk.Button(bf, text="Cancel", command=root.destroy).pack(side="left", padx=4)

    e0.focus_set()
    root.mainloop()
    return result.get("cfg", defaults or {})

# ========= Apply CLI + GUI/headless =========
_args = parse_cli_args()
if _args.percent_style:
    PERCENT_STYLE = _args.percent_style

_saved = load_config()

if _args.headless:
    _cfg = dict(_saved) if _saved else {}
    if _args.log_path:  _cfg["log_path"]     = _args.log_path
    if _args.output:    _cfg["output_path"]  = _args.output
    if _args.goal_bsc:  _cfg["goal_bsc"]     = _args.goal_bsc
    if _args.user_id:   _cfg["user_id_override"] = _args.user_id
    if _args.hash:      _cfg["hash_override"]    = _args.hash
    if _args.mcv:       _cfg["mcv_override"]     = _args.mcv
    if _args.api_url:   _cfg["api_url_override"] = _args.api_url
    _cfg.setdefault("log_path", LOG_PATH)
    _cfg.setdefault("output_path", OUTPUT_PATH)
    _cfg.setdefault("goal_bsc", GOAL_BSC)
else:
    _cfg = show_config_dialog(_saved)

LOG_PATH    = _cfg.get("log_path", LOG_PATH)
OUTPUT_PATH = _cfg.get("output_path", OUTPUT_PATH)
GOAL_BSC    = int(_cfg.get("goal_bsc", GOAL_BSC))
USER_ID_OVERRIDE = (_cfg.get("user_id_override") or "").strip()
HASH_OVERRIDE    = (_cfg.get("hash_override") or "").strip()
MCV_OVERRIDE     = (_cfg.get("mcv_override") or "").strip()
API_URL_OVERRIDE = (_cfg.get("api_url_override") or "").strip()

# ========= Read log & build API call =========
with open(LOG_PATH, "r", encoding="utf-8") as f:
    log_text = f.read()

line = find_latest_getuserdetails_line(log_text)
if not line and not (USER_ID_OVERRIDE and HASH_OVERRIDE and API_URL_OVERRIDE):
    raise Exception("Could not find a 'getuserdetails' line and no overrides provided.")

api_url = API_URL_OVERRIDE or (extract_post_url_from_line(line) if line else None)
if not api_url and line:
    m = re.search(r'"play_server"\s*:\s*"([^"]+)"', line) or re.search(r'play_server\s*=\s*([^\s&"\'<>#]+)', line)
    if m:
        ps = m.group(1).replace(r"\/", "/")
        if not ps.endswith("/"):
            ps += "/"
        api_url = f"{ps}post.php"
if not api_url:
    raise Exception("Could not determine post.php URL (override or log).")

kv = parse_kv_from_line(line) if line else {}
user_id = USER_ID_OVERRIDE or kv.get("user_id") or kv.get("internal_user_id")
hash_val = HASH_OVERRIDE or kv.get("hash") or kv.get("hashh")
mcv      = MCV_OVERRIDE or kv.get("mobile_client_version") or "633"
if not user_id or not hash_val:
    raise Exception("user_id or hash missing (override or log).")

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

try:
    print("🔍 API:", api_url)
except UnicodeEncodeError:
    print("API:", api_url)

resp = requests.post(api_url, data=params, headers=headers, timeout=30, verify=certifi.where())
if resp.status_code != 200 or not resp.text.strip().startswith("{"):
    snippet = resp.text[:200].replace("\n", " ")
    raise Exception(f"Invalid API response: {resp.status_code} | {snippet}")
data = resp.json()

# ========= Values & conversions =========
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

chests = data.get("details", {}).get("chests", {})
gold   = safe_int(chests.get("2", 0))
silver = safe_int(chests.get("1", 0))
gems   = safe_int(get_nested(data, "details.red_rubies", 0))

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

# Convert current resources into BSC
bsc_from_gold   = gold            # 1 gold chest = 1 BSC
bsc_from_silver = silver // 10    # 10 silver = 1 BSC
bsc_from_gems   = gems // 500     # 500 gems = 1 BSC

# Overall remaining
R_overall = max(GOAL_BSC - (bsc_base + bsc_from_gold + bsc_from_silver + bsc_from_gems), 0)

# Per-resource goals in units: overall remaining + add back own contribution
gold_goal_units   = (R_overall + bsc_from_gold)   * 1
silver_goal_units = (R_overall + bsc_from_silver) * 10
gems_goal_units   = (R_overall + bsc_from_gems)   * 500

# ========= SAFE ICONS (cache raw PNGs in app dir; crop/resize only in memory) =========
# Canonical filenames we’ll use *inside the cache*
ICON_FILES = {
    "gems":   "Icon_GemPile2_0_4.png",
    "bsc":    "Icon_BlacksmithContract1_Inv_0_5.png",
    "gold":   "Icon_StoreChest_Gold_0_6.png",
    "silver": "Icon_StoreChest_Silver_0_6.png",
}

# Exact remote paths to request
REMOTE_PATHS = {
    "silver": "Icons/Chests/Icon_StoreChest_Silver",
    "gold":   "Icons/Chests/Icon_StoreChest_Gold",
    "gems":   "Icons/Inventory/Icon_GemPile2",
    "bsc":    "Icons/Inventory/Icon_BlacksmithContract1",
}

# Pillow resample compatibility
try:
    RESAMPLE = Image.Resampling.LANCZOS
except Exception:
    RESAMPLE = Image.LANCZOS

PNG_SIG  = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"

def assets_base_from_api_url(api_url: str) -> str:
    u = urlparse(api_url)
    return f"{u.scheme}://{u.netloc}/~idledragons/mobile_assets/"

def maybe_decompress(data: bytes, headers: dict) -> bytes:
    enc = (headers or {}).get("Content-Encoding", "").lower()
    if enc == "gzip" or (len(data) >= 2 and data[:2] == b"\x1f\x8b"):
        try:
            return gzip.decompress(data)
        except Exception:
            pass
    return data

def iter_embedded_pngs(blob: bytes):
    """Yield (start, end, width, height) for each embedded PNG found."""
    i = 0
    n = len(blob)
    while True:
        start = blob.find(PNG_SIG, i)
        if start == -1:
            return
        end = blob.find(PNG_IEND, start)
        if end == -1:
            return
        end += len(PNG_IEND)
        width = height = None
        try:
            ihdr_off = start + 8
            ihdr_len = struct.unpack(">I", blob[ihdr_off:ihdr_off+4])[0]
            ihdr_tag = blob[ihdr_off+4:ihdr_off+8]
            if ihdr_tag == b'IHDR' and ihdr_len >= 8:
                width  = struct.unpack(">I", blob[ihdr_off+8: ihdr_off+12])[0]
                height = struct.unpack(">I", blob[ihdr_off+12: ihdr_off+16])[0]
        except Exception:
            pass
        yield (start, end, width, height)
        i = end

def choose_png_for_key(candidates, key: str):
    """Pick best embedded PNG by size for each icon type (raw bytes saved; no disk edits)."""
    if not candidates:
        return None
    scored = []
    for (s, e, w, h) in candidates:
        side = max(w or 0, h or 0)
        scored.append((side, w, h, s, e))
    if key in ("gold", "silver"):
        scored.sort(key=lambda t: (0 if t[0] >= 200 else 1, -t[0]))  # prefer 256-ish chest art
        return scored[0]
    if key == "bsc":
        scored.sort(key=lambda t: min(abs((t[0] or 0)-128), abs((t[0] or 0)-64)))  # prefer 128 then 64
        return scored[0]
    if key == "gems":
        scored.sort(key=lambda t: abs((t[0] or 0) - 64))  # prefer 64
        return scored[0]
    scored.sort(key=lambda t: -t[0])
    return scored[0]

def download_and_extract_icon_raw_png(key: str, api_url: str) -> bytes | None:
    """Download from exact path; return the RAW PNG bytes (no crop/resize when saving)."""
    base = assets_base_from_api_url(api_url)
    path = REMOTE_PATHS[key]
    for suffix in ("", ".png"):
        url = base + path + suffix
        try:
            r = requests.get(url, timeout=25, verify=certifi.where())
            if r.status_code != 200 or not r.content:
                continue
            content = maybe_decompress(r.content, r.headers or {})
            if content.startswith(PNG_SIG):
                return content
            cands = list(iter_embedded_pngs(content))
            if not cands:
                continue
            best = choose_png_for_key(cands, key)
            if not best:
                continue
            _, _, _, s, e = best
            return content[s:e]
        except Exception:
            continue
    return None

def ensure_icons_in_cache(api_url: str):
    ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for key, local_name in ICON_FILES.items():
        cache_path = ICON_CACHE_DIR / local_name
        if cache_path.exists():
            continue
        raw = download_and_extract_icon_raw_png(key, api_url)
        if raw:
            with open(cache_path, "wb") as f:
                f.write(raw)
        # If download fails we render without an icon (non-fatal).

def crop_top_left(img: Image.Image, crop_w=165, crop_h=165) -> Image.Image:
    """Crop top-left area (used for 256x256 chest art to make it fill better)."""
    w, h = img.size
    cw = min(crop_w, w)
    ch = min(crop_h, h)
    return img.crop((0, 0, cw, ch))

def crop_box(img: Image.Image, left: int, top: int, width: int, height: int) -> Image.Image:
    right = min(left + width, img.size[0])
    lower = min(top + height, img.size[1])
    left = max(0, left); top = max(0, top)
    return img.crop((left, top, right, lower))

def load_icon_processed_from_cache(key: str, size=ICON_SIZE):
    """Open cached RAW PNG (no disk edits), crop/resize only in memory for rendering."""
    cache_path = ICON_CACHE_DIR / ICON_FILES[key]
    if not cache_path.exists():
        return None
    try:
        img = Image.open(str(cache_path)).convert("RGBA")
        w, h = img.size
        if key in ("gold", "silver"):
            if max(w, h) >= 200:
                img = crop_top_left(img, 165, 165)
        elif key == "bsc":
            if (w, h) == (128, 128):
                img = crop_box(img, 4, 4, 64, 64)
        # gems likely 64x64 → no crop
        return img.resize(size, RESAMPLE)
    except Exception:
        return None

# 1) Ensure raw PNGs exist in our cache (next to script/exe)
ensure_icons_in_cache(api_url)

# 2) Load for drawing (crop/resize only in memory)
icon_gems   = load_icon_processed_from_cache("gems")
icon_bsc    = load_icon_processed_from_cache("bsc")
icon_gold   = load_icon_processed_from_cache("gold")
icon_silver = load_icon_processed_from_cache("silver")

# ========= Draw =========
def _load_font(path, size):
    try:
        if path and os.path.exists(path):
            return _IF.truetype(path, size)
        for p in (r"C:\Windows\Fonts\arial.ttf",
                  "/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.exists(p):
                return _IF.truetype(p, size)
    except Exception:
        pass
    return _IF.load_default()

img_h = PADDING*2 + 4*ROW_HEIGHT + 40
img = Image.new("RGBA", (IMG_WIDTH, img_h), (0,0,0,0))
draw = ImageDraw.Draw(img)

font_med   = _load_font(FONT_MED_PATH, 21)
font_small = _load_font(FONT_SMALL_PATH, 15)

now = datetime.now()
date_str = f"{now.day} {MONTHS_EN[now.month]} {now.year}"
draw.text((PADDING, 6), date_str, font=font_small, fill=(180, 180, 180))

def draw_progress_block(y, value, goal, icon, bar_color, title="", meta_suffix=""):
    bar_x = PADDING + (ICON_SIZE[0] + 10 if icon else 0)
    title_y = y
    title_h = 0
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_med)
        title_h = bbox[3] - bbox[1]
    bar_y = y + title_h + TITLE_BAR_GAP

    draw.rectangle([bar_x, bar_y, bar_x + BAR_WIDTH, bar_y + BAR_HEIGHT], fill=(40, 40, 40))
    draw.rectangle([bar_x, bar_y, bar_x + BAR_WIDTH - 1, bar_y + BAR_HEIGHT - 1], outline=BAR_OUTLINE, width=1)

    frac = 0 if goal <= 0 else min(value / goal, 1.0)
    fill_w = int(BAR_WIDTH * frac)
    if fill_w > 0:
        draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + BAR_HEIGHT], fill=bar_color)

    if icon:
        img.paste(icon, (PADDING, y + (ROW_HEIGHT - ICON_SIZE[1]) // 2), icon)

    if title:
        draw.text((bar_x, title_y), title, font=font_med, fill=(255, 255, 255))
    pct = percent_str(value, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + BAR_WIDTH - w, title_y), pct, font=font_small, fill=(220, 220, 220))

    remaining_units = max(goal - value, 0)
    meta = f"Remaining: {fmt_int(remaining_units)} • Goal: {fmt_int(goal)}{meta_suffix}"
    draw.text((bar_x, bar_y + BAR_HEIGHT + 4), meta, font=font_small, fill=(210,210,210))

def draw_stacked_bsc_block(y, segments, goal, title, icon=None):
    bar_x = PADDING + (ICON_SIZE[0] + 10 if icon else 0)
    title_y = y
    title_h = 0
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_med)
        title_h = bbox[3] - bbox[1]
    bar_y = y + title_h + TITLE_BAR_GAP
    bar_w, bar_h = BAR_WIDTH, BAR_HEIGHT

    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(40,40,40))
    draw.rectangle([bar_x, bar_y, bar_x + bar_w - 1, bar_y + bar_h - 1], outline=BAR_OUTLINE, width=1)

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

    if icon:
        img.paste(icon, (PADDING, y + (ROW_HEIGHT - ICON_SIZE[1]) // 2), icon)

    if title:
        draw.text((bar_x, title_y), title, font=font_med, fill=(255,255,255))
    pct = percent_str(total_bsc, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + bar_w - w, title_y), pct, font=font_small, fill=(220,220,220))

    labels = [f"{lbl} {fmt_int(val)}" for lbl, val, _ in segments]
    legend = " | ".join(labels)
    draw.text((bar_x, bar_y + bar_h + LEGEND_GAP), legend, font=font_small, fill=(210,210,210))

    remaining = max(goal - total_bsc, 0)
    meta = f"Remaining: {fmt_int(remaining)} • Goal: {fmt_int(goal)}"
    draw.text((bar_x, bar_y + bar_h + LEGEND_GAP + 18), meta, font=font_small, fill=(200,200,200))

# Segments (BSC units)
segments = [
    ("BSC",   bsc_base,        COLOR_BSC_BASE),
    ("Gold",  bsc_from_gold,   COLOR_GOLD),
    ("Silver",bsc_from_silver, COLOR_SILVER),
    ("Gems",  bsc_from_gems,   COLOR_GEMS),
]

# Draw
y0 = 26
draw_progress_block(y0 + 0*ROW_HEIGHT, gold,   gold_goal_units,   icon_gold,   COLOR_GOLD,
                    title="Gold-Chests",   meta_suffix=" (1 ≈ 1 BSC)")
draw_progress_block(y0 + 1*ROW_HEIGHT, silver, silver_goal_units, icon_silver, COLOR_SILVER,
                    title="Silver-Chests", meta_suffix=" (10 ≈ 1 BSC)")
draw_progress_block(y0 + 2*ROW_HEIGHT, gems,   gems_goal_units,   icon_gems,   COLOR_GEMS,
                    title="Gems",          meta_suffix=" (500 = 1 BSC)")
draw_stacked_bsc_block(y0 + 3*ROW_HEIGHT, segments, GOAL_BSC, "Blacksmith Contracts", icon=icon_bsc)

# Save
img.save(OUTPUT_PATH)
print(f"✅ Overlay saved as {OUTPUT_PATH}")
