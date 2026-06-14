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

from PIL import Image, ImageDraw, ImageFont as _IF, ImageChops

# ========= Working dir (EXE/script) =========
def _set_cwd_to_app_dir():
    try:
        base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        os.chdir(base)
    except Exception:
        pass


_set_cwd_to_app_dir()
APP_DIR = Path.cwd()
ICON_CACHE_DIR = APP_DIR / "overlay_icon_cache"
SNAPSHOT_FILE = "bsc_snapshot.json"

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


def fmt_float(n: float, digits: int = 1) -> str:
    try:
        s = f"{float(n):.{digits}f}"
        dec = locale.localeconv().get("decimal_point", ".") or "."
        return s.replace(".", dec)
    except Exception:
        return f"{float(n):.{digits}f}"


PERCENT_STYLE = "locale"


def percent_str(value, goal, style=None):
    style = style or PERCENT_STYLE
    p = 100.0 if goal <= 0 else min(1.0, (float(value) / float(goal))) * 100.0
    if style == "int":
        return f"{int(round(p))}%"
    s = f"{p:.2f}"
    if style == "locale":
        dec = locale.localeconv().get("decimal_point", ".") or "."
        s = s.replace(".", dec)
    else:
        s = s.replace(",", ".")
    return s + "%"


# ========= Defaults =========
LOG_PATH = r"C:/IdleChampions/IdleChampions/IdleDragons_Data/StreamingAssets/downloaded_files/webRequestLog.txt"
OUTPUT_PATH = "overlay_extended.png"
GOAL_BSC = 15_360_005

FONT_MED_PATH = "arial.ttf"
FONT_SMALL_PATH = "arial.ttf"

IMG_WIDTH = 950
ROW_HEIGHT = 84
PADDING = 16
ICON_SIZE = (56, 56)
BAR_WIDTH = 520
BAR_HEIGHT = 22

TITLE_BAR_GAP = 10
LEGEND_GAP = 6
BAR_OUTLINE = (58, 58, 58)
SEGMENT_SEPARATOR = (25, 25, 25)
SHOW_SEG_SEPARATORS = False

COLOR_GOLD = (255, 215, 0)
COLOR_SILVER = (192, 192, 192)
COLOR_GEMS = (100, 200, 150)
COLOR_BSC_BASE = (80, 170, 255)
COLOR_EVENT = (180, 120, 255)

MONTHS_EN = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

MOBILE_CLIENT_VERSION = "9999"

# ========= Event chest averages =========
EVENT_SILVER_ILVL_AVG = 2.10887097
EVENT_GOLD_ILVL_AVG_NO_BC = 13.70210250
EVENT_GOLD_ILVL_AVG_WITH_BC = 14.41267674


# ========= CLI =========
def parse_cli_args():
    p = argparse.ArgumentParser(description="IdleChamps BSC overlay")
    p.add_argument("--headless", action="store_true", help="run without GUI dialog")
    p.add_argument("--log-path")
    p.add_argument("--output")
    p.add_argument("--goal-bsc", type=int)
    p.add_argument("--user-id")   # override only
    p.add_argument("--hash")      # override only
    p.add_argument("--api-url")
    p.add_argument("--percent-style", choices=["locale", "dot", "int"])

    # Event overrides
    p.add_argument("--event-enable", action="store_true")
    p.add_argument("--event-name")
    p.add_argument("--event-silver-id", type=int)
    p.add_argument("--event-gold-id", type=int)
    p.add_argument("--event-no-bc-tokens", action="store_true",
                   help="use Gear + BSC only (without BC Tokens) for event gold chest average")

    # ETA overrides
    p.add_argument("--eta-enable", action="store_true")
    p.add_argument("--eta-bsc-per-hour", type=float)
    p.add_argument("--eta-use-snapshot", action="store_true")
    p.add_argument("--save-snapshot", action="store_true")

    return p.parse_args()


# ========= Config =========
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


def load_snapshot():
    try:
        if os.path.exists(SNAPSHOT_FILE):
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_snapshot(total_bsc: int):
    payload = {
        "timestamp": datetime.now().isoformat(),
        "total_bsc": int(total_bsc),
    }
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ========= Log parsing =========
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
    for k, v in re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*"([^"]+)"', line):
        out[k] = v
    for k, v in re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*([A-Za-z0-9_.-]+)', line):
        if k not in out:
            out[k] = v
    for k, v in re.findall(r'([A-Za-z0-9_]+)\s*=\s*([^\s&"\'<>#]+)', line):
        out[k] = v
    for url in re.findall(r'https?://[^\s"\'<>]+', line):
        try:
            q = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
            out.update(q)
        except Exception:
            pass
    return out


# ========= Helpers =========
def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        try:
            return float(str(v).replace(",", "."))
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


# ========= GUI =========
def show_config_dialog(defaults: dict):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        return defaults or {}

    defaults = defaults or {}
    root = tk.Tk()
    root.title("IdleChamps Overlay – Settings")
    root.columnconfigure(1, weight=1)

    def row_label(text, r, c=0):
        tk.Label(root, text=text).grid(row=r, column=c, sticky="w", padx=8, pady=4)

    def row_entry(var, r, c=1, width=60, show=None):
        e = tk.Entry(root, textvariable=var, width=width, show=show)
        e.grid(row=r, column=c, sticky="we", padx=8, pady=4)
        return e

    v_log = tk.StringVar(value=defaults.get("log_path", LOG_PATH))
    v_out = tk.StringVar(value=defaults.get("output_path", OUTPUT_PATH))
    v_goal = tk.StringVar(value=str(defaults.get("goal_bsc", GOAL_BSC)))
    v_api = tk.StringVar(value=defaults.get("api_url_override", ""))

    # creds
    save_creds_prev = bool(defaults.get("save_creds", False))
    v_save_creds = tk.BooleanVar(value=save_creds_prev)
    v_user = tk.StringVar(value=(defaults.get("user_id_override", "") if save_creds_prev else ""))
    v_hash = tk.StringVar(value=(defaults.get("hash_override", "") if save_creds_prev else ""))
    v_show_hash = tk.BooleanVar(value=False)

    # event
    v_event_enable = tk.BooleanVar(value=bool(defaults.get("event_enable", False)))
    v_event_name = tk.StringVar(value=str(defaults.get("event_name", "Briv")))
    v_event_silver = tk.StringVar(value=str(defaults.get("event_silver_id", 174)))
    v_event_gold = tk.StringVar(value=str(defaults.get("event_gold_id", 175)))
    v_event_no_bc_tokens = tk.BooleanVar(value=bool(defaults.get("event_no_bc_tokens", True)))

    # ETA
    v_eta_enable = tk.BooleanVar(value=bool(defaults.get("eta_enable", False)))
    v_eta_bsc_per_hour = tk.StringVar(value=str(defaults.get("eta_bsc_per_hour", "")))
    v_eta_use_snapshot = tk.BooleanVar(value=bool(defaults.get("eta_use_snapshot", False)))
    v_save_snapshot_on_run = tk.BooleanVar(value=False)

    out_cfg = {}

    def browse_log():
        p = filedialog.askopenfilename(
            title="Select webRequestLog.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if p:
            v_log.set(p)

    def browse_out():
        p = filedialog.asksaveasfilename(
            title="Select output PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("All", "*.*")]
        )
        if p:
            v_out.set(p)

    def toggle_hash():
        e_hash.config(show="" if v_show_hash.get() else "•")

    def safe_int_field(s, fallback):
        try:
            return int(str(s).strip())
        except Exception:
            return fallback

    def extract_from_log():
        try:
            with open(v_log.get(), "r", encoding="utf-8") as f:
                txt = f.read()
            ln = find_latest_getuserdetails_line(txt)
            if not ln:
                messagebox.showwarning("Not found", "No getuserdetails line found in the log.")
                return
            kv = parse_kv_from_line(ln)
            api_u = extract_post_url_from_line(ln)

            if not api_u:
                ps = kv.get("play_server") or ""
                if ps:
                    ps = ps.replace(r"\/", "/")
                    if not ps.endswith("/"):
                        ps += "/"
                    api_u = ps + "post.php"

            if api_u:
                v_api.set(api_u)
            if kv.get("user_id") or kv.get("internal_user_id"):
                v_user.set(kv.get("user_id") or kv.get("internal_user_id"))
            if kv.get("hash") or kv.get("hashh"):
                v_hash.set(kv.get("hash") or kv.get("hashh"))

            messagebox.showinfo(
                "Extracted",
                "Extracted values from newest getuserdetails line.\n"
                "Stored only if 'Save user_id/hash' is checked."
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to extract from log:\n{e}")

    def on_save_run():
        nonlocal out_cfg

        run_cfg = {
            "log_path": v_log.get().strip(),
            "output_path": v_out.get().strip(),
            "goal_bsc": safe_int_field(v_goal.get(), GOAL_BSC),
            "api_url_override": v_api.get().strip(),

            # event
            "event_enable": bool(v_event_enable.get()),
            "event_name": (v_event_name.get().strip() or "Briv"),
            "event_silver_id": safe_int_field(v_event_silver.get(), 174),
            "event_gold_id": safe_int_field(v_event_gold.get(), 175),
            "event_no_bc_tokens": bool(v_event_no_bc_tokens.get()),

            # eta
            "eta_enable": bool(v_eta_enable.get()),
            "eta_bsc_per_hour": v_eta_bsc_per_hour.get().strip(),
            "eta_use_snapshot": bool(v_eta_use_snapshot.get()),
            "save_snapshot_on_run": bool(v_save_snapshot_on_run.get()),

            # creds
            "user_id_override": v_user.get().strip(),
            "hash_override": v_hash.get().strip(),
        }

        to_save = dict(run_cfg)
        # don't persist one-shot action
        to_save.pop("save_snapshot_on_run", None)

        if v_save_creds.get():
            to_save["save_creds"] = True
        else:
            to_save["save_creds"] = False
            to_save["user_id_override"] = ""
            to_save["hash_override"] = ""

        try:
            save_config(to_save)
        except Exception:
            pass

        out_cfg = run_cfg
        root.destroy()

    def on_cancel():
        nonlocal out_cfg
        out_cfg = defaults
        root.destroy()

    r = 0
    row_label("Log path (webRequestLog.txt)", r); row_entry(v_log, r)
    tk.Button(root, text="Browse", command=browse_log).grid(row=r, column=2, padx=8, pady=4)

    r += 1
    row_label("Output PNG", r); row_entry(v_out, r)
    tk.Button(root, text="Browse", command=browse_out).grid(row=r, column=2, padx=8, pady=4)

    r += 1
    row_label("Goal (BSC)", r); row_entry(v_goal, r, width=20)

    r += 1
    tk.Button(root, text="Extract from log", command=extract_from_log).grid(row=r, column=0, padx=8, pady=8, sticky="w")

    r += 1
    row_label("API URL override (post.php)", r); row_entry(v_api, r)

    r += 1
    row_label("User ID", r); row_entry(v_user, r, width=30)

    r += 1
    row_label("Hash", r)
    e_hash = row_entry(v_hash, r, width=40, show="•")
    tk.Checkbutton(root, text="Show", variable=v_show_hash, command=toggle_hash).grid(row=r, column=2, padx=8, pady=4)

    r += 1
    tk.Checkbutton(root, text="Save user_id/hash to config (local)", variable=v_save_creds).grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8)
    )

    r += 1
    tk.Label(root, text="— Champion Event Chests (TOTAL bar only) —").grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=(14, 4)
    )

    r += 1
    tk.Checkbutton(root, text="Enable Champion Event Chests", variable=v_event_enable).grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=4
    )

    r += 1
    row_label("Champion Name", r); row_entry(v_event_name, r, width=20)

    r += 1
    row_label("Silver Chest ID", r); row_entry(v_event_silver, r, width=10)

    r += 1
    row_label("Gold Chest ID", r); row_entry(v_event_gold, r, width=10)

    r += 1
    tk.Checkbutton(
        root,
        text="Use Gear + BSC only (without BC Tokens)",
        variable=v_event_no_bc_tokens
    ).grid(row=r, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 4))

    r += 1
    tk.Label(root, text="— ETA / Days remaining —").grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=(14, 4)
    )

    r += 1
    tk.Checkbutton(root, text="Enable ETA", variable=v_eta_enable).grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=4
    )

    r += 1
    row_label("Manual BSC/h", r); row_entry(v_eta_bsc_per_hour, r, width=20)

    r += 1
    tk.Checkbutton(root, text="Use snapshot-derived BSC/h", variable=v_eta_use_snapshot).grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=4
    )

    r += 1
    tk.Checkbutton(root, text="Save snapshot on this run", variable=v_save_snapshot_on_run).grid(
        row=r, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8)
    )

    r += 1
    tk.Button(root, text="Save & Run", command=on_save_run).grid(row=r, column=1, padx=8, pady=12, sticky="e")
    tk.Button(root, text="Cancel", command=on_cancel).grid(row=r, column=2, padx=8, pady=12, sticky="w")

    root.mainloop()
    return out_cfg or defaults


# ========= Apply CLI + GUI/headless =========
_args = parse_cli_args()
if _args.percent_style:
    PERCENT_STYLE = _args.percent_style

_saved = load_config()

if _args.headless:
    _cfg = dict(_saved) if _saved else {}
    if _args.log_path:
        _cfg["log_path"] = _args.log_path
    if _args.output:
        _cfg["output_path"] = _args.output
    if _args.goal_bsc:
        _cfg["goal_bsc"] = _args.goal_bsc
    if _args.api_url:
        _cfg["api_url_override"] = _args.api_url
    if _args.user_id:
        _cfg["user_id_override"] = _args.user_id
    if _args.hash:
        _cfg["hash_override"] = _args.hash

    if _args.event_enable:
        _cfg["event_enable"] = True
    if _args.event_name:
        _cfg["event_name"] = _args.event_name
    if _args.event_silver_id is not None:
        _cfg["event_silver_id"] = _args.event_silver_id
    if _args.event_gold_id is not None:
        _cfg["event_gold_id"] = _args.event_gold_id
    if _args.event_no_bc_tokens:
        _cfg["event_no_bc_tokens"] = True

    if _args.eta_enable:
        _cfg["eta_enable"] = True
    if _args.eta_bsc_per_hour is not None:
        _cfg["eta_bsc_per_hour"] = str(_args.eta_bsc_per_hour)
    if _args.eta_use_snapshot:
        _cfg["eta_use_snapshot"] = True
    _cfg["save_snapshot_on_run"] = bool(_args.save_snapshot)

    _cfg.setdefault("log_path", LOG_PATH)
    _cfg.setdefault("output_path", OUTPUT_PATH)
    _cfg.setdefault("goal_bsc", GOAL_BSC)
else:
    _cfg = show_config_dialog(_saved)

LOG_PATH = _cfg.get("log_path", LOG_PATH)
OUTPUT_PATH = _cfg.get("output_path", OUTPUT_PATH)
GOAL_BSC = int(_cfg.get("goal_bsc", GOAL_BSC))
API_URL_OVERRIDE = (_cfg.get("api_url_override") or "").strip()

save_creds_effective = bool(_cfg.get("save_creds", False))
USER_ID_OVERRIDE = (_cfg.get("user_id_override") or "").strip() if (save_creds_effective or _args.headless) else ""
HASH_OVERRIDE = (_cfg.get("hash_override") or "").strip() if (save_creds_effective or _args.headless) else ""

EVENT_ENABLE = bool(_cfg.get("event_enable", False))
EVENT_NAME = (_cfg.get("event_name") or "Briv").strip() or "Briv"
EVENT_SILVER_ID = str(_cfg.get("event_silver_id", 174))
EVENT_GOLD_ID = str(_cfg.get("event_gold_id", 175))
EVENT_NO_BC_TOKENS = bool(_cfg.get("event_no_bc_tokens", True))
EVENT_GOLD_ILVL_AVG = EVENT_GOLD_ILVL_AVG_NO_BC if EVENT_NO_BC_TOKENS else EVENT_GOLD_ILVL_AVG_WITH_BC

ETA_ENABLE = bool(_cfg.get("eta_enable", False))
ETA_BSC_PER_HOUR_MANUAL = safe_float(_cfg.get("eta_bsc_per_hour", 0.0), 0.0)
ETA_USE_SNAPSHOT = bool(_cfg.get("eta_use_snapshot", False))
SAVE_SNAPSHOT_ON_RUN = bool(_cfg.get("save_snapshot_on_run", False))


# ========= Read log & build API call =========
with open(LOG_PATH, "r", encoding="utf-8") as f:
    log_text = f.read()

line = find_latest_getuserdetails_line(log_text)
if not line and not (USER_ID_OVERRIDE and HASH_OVERRIDE and API_URL_OVERRIDE):
    raise Exception("Could not find a 'getuserdetails' line and no overrides provided.")

api_url = API_URL_OVERRIDE or (extract_post_url_from_line(line) if line else None)
kv = parse_kv_from_line(line) if line else {}

if not api_url and line:
    ps = kv.get("play_server", "")
    if ps:
        ps = ps.replace(r"\/", "/")
        if not ps.endswith("/"):
            ps += "/"
        api_url = ps + "post.php"

if not api_url:
    raise Exception("Could not determine post.php URL (override or log).")

user_id = USER_ID_OVERRIDE or kv.get("user_id") or kv.get("internal_user_id")
hash_val = HASH_OVERRIDE or kv.get("hash") or kv.get("hashh")
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
    "mobile_client_version": MOBILE_CLIENT_VERSION,
    "localization_aware": kv.get("localization_aware", "true"),
}
headers = {"User-Agent": "Mozilla/5.0"}

resp = requests.post(api_url, data=params, headers=headers, timeout=30, verify=certifi.where())
if resp.status_code != 200 or not resp.text.strip().startswith("{"):
    snippet = resp.text[:200].replace("\n", " ")
    raise Exception(f"Invalid API response: {resp.status_code} | {snippet}")
data = resp.json()

# ========= Values =========
chests = data.get("details", {}).get("chests", {})
gold = safe_int(chests.get("2", 0))
silver = safe_int(chests.get("1", 0))
gems = safe_int(get_nested(data, "details.red_rubies", 0))

event_silver_cnt = safe_int(chests.get(EVENT_SILVER_ID, 0)) if EVENT_ENABLE else 0
event_gold_cnt = safe_int(chests.get(EVENT_GOLD_ID, 0)) if EVENT_ENABLE else 0
event_total_bsc = int(round(
    event_silver_cnt * EVENT_SILVER_ILVL_AVG +
    event_gold_cnt * EVENT_GOLD_ILVL_AVG
)) if EVENT_ENABLE else 0

# Base BSC from buffs
BSC_WEIGHTS = {31: 1, 32: 2, 33: 6, 34: 24, 1797: 120}


def find_contract_buffs_anywhere(obj):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and 'buff_id' in obj[0] and 'inventory_amount' in obj[0]:
            return obj
        for item in obj:
            res = find_contract_buffs_anywhere(item)
            if res:
                return res
    elif isinstance(obj, dict):
        for v in obj.values():
            res = find_contract_buffs_anywhere(v)
            if res:
                return res
    return None


def compute_bsc_from_buffs(json_data):
    buff_list = find_contract_buffs_anywhere(json_data)
    total = 0
    breakdown = {k: 0 for k in BSC_WEIGHTS.keys()}
    if not buff_list:
        return 0, breakdown
    for entry in buff_list:
        try:
            b_id = int(entry.get("buff_id", -1))
            amt = int(entry.get("inventory_amount", 0))
        except Exception:
            continue
        if b_id in BSC_WEIGHTS and amt > 0:
            total += amt * BSC_WEIGHTS[b_id]
            breakdown[b_id] += amt
    return total, breakdown


bsc_base, _b = compute_bsc_from_buffs(data)

bsc_from_gold = gold
bsc_from_silver = silver // 10
bsc_from_gems = gems // 500

current_total_bsc = bsc_base + bsc_from_gold + bsc_from_silver + bsc_from_gems + event_total_bsc
R_overall = max(GOAL_BSC - current_total_bsc, 0)

gold_goal_units = (R_overall + bsc_from_gold) * 1
silver_goal_units = (R_overall + bsc_from_silver) * 10
gems_goal_units = (R_overall + bsc_from_gems) * 500


# ========= ETA / snapshot =========
eta_bsc_per_hour = 0.0
eta_source = None
eta_text = None

if ETA_ENABLE:
    if ETA_USE_SNAPSHOT:
        snap = load_snapshot()
        snap_total = safe_int(snap.get("total_bsc", 0), 0)
        snap_ts_raw = snap.get("timestamp")
        try:
            snap_dt = datetime.fromisoformat(snap_ts_raw) if snap_ts_raw else None
        except Exception:
            snap_dt = None

        if snap_dt is not None:
            elapsed_hours = (datetime.now() - snap_dt).total_seconds() / 3600.0
            delta_bsc = current_total_bsc - snap_total
            if elapsed_hours > 0 and delta_bsc > 0:
                eta_bsc_per_hour = delta_bsc / elapsed_hours
                eta_source = "snapshot"

    if eta_bsc_per_hour <= 0 and ETA_BSC_PER_HOUR_MANUAL > 0:
        eta_bsc_per_hour = ETA_BSC_PER_HOUR_MANUAL
        eta_source = "manual"

    if eta_bsc_per_hour > 0:
        eta_hours = R_overall / eta_bsc_per_hour if R_overall > 0 else 0.0
        eta_days = eta_hours / 24.0
        eta_text = f"ETA @ {fmt_float(eta_bsc_per_hour, 1)} BSC/h ({eta_source}): {fmt_float(eta_days, 1)} days"

if SAVE_SNAPSHOT_ON_RUN:
    try:
        save_snapshot(current_total_bsc)
    except Exception:
        pass


# ========= Icons =========
ICON_FILES = {
    "gems": "Icon_GemPile2_0_4.png",
    "bsc": "Icon_BlacksmithContract1_Inv_0_5.png",
    "gold": "Icon_StoreChest_Gold_0_6.png",
    "silver": "Icon_StoreChest_Silver_0_6.png",
}
REMOTE_PATHS = {
    "silver": "Icons/Chests/Icon_StoreChest_Silver",
    "gold": "Icons/Chests/Icon_StoreChest_Gold",
    "gems": "Icons/Inventory/Icon_GemPile2",
    "bsc": "Icons/Inventory/Icon_BlacksmithContract1",
}

try:
    RESAMPLE = Image.Resampling.LANCZOS
except Exception:
    RESAMPLE = Image.LANCZOS

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"


def assets_base_from_api_url(api_url_: str) -> str:
    u = urlparse(api_url_)
    if not u.scheme or not u.netloc:
        return ""
    return f"{u.scheme}://{u.netloc}/~idledragons/mobile_assets/"


def maybe_decompress(blob: bytes, headers: dict) -> bytes:
    enc = (headers or {}).get("Content-Encoding", "").lower()
    if enc == "gzip" or (len(blob) >= 2 and blob[:2] == b"\x1f\x8b"):
        try:
            return gzip.decompress(blob)
        except Exception:
            pass
    return blob


def iter_embedded_pngs(blob: bytes):
    i = 0
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
            ihdr_len = struct.unpack(">I", blob[ihdr_off:ihdr_off + 4])[0]
            ihdr_tag = blob[ihdr_off + 4:ihdr_off + 8]
            if ihdr_tag == b'IHDR' and ihdr_len >= 8:
                width = struct.unpack(">I", blob[ihdr_off + 8: ihdr_off + 12])[0]
                height = struct.unpack(">I", blob[ihdr_off + 12: ihdr_off + 16])[0]
        except Exception:
            pass
        yield (start, end, width, height)
        i = end


def choose_png_for_key(candidates, key: str):
    if not candidates:
        return None
    scored = []
    for (s, e, w, h) in candidates:
        side = max(w or 0, h or 0)
        scored.append((side, w, h, s, e))
    if key in ("gold", "silver"):
        scored.sort(key=lambda t: (0 if (t[0] or 0) >= 200 else 1, -(t[0] or 0)))
        return scored[0]
    if key == "bsc":
        scored.sort(key=lambda t: min(abs((t[0] or 0) - 128), abs((t[0] or 0) - 64)))
        return scored[0]
    if key == "gems":
        scored.sort(key=lambda t: abs((t[0] or 0) - 64))
        return scored[0]
    scored.sort(key=lambda t: -(t[0] or 0))
    return scored[0]


def download_and_extract_icon_raw_png(key: str, api_url_: str):
    base = assets_base_from_api_url(api_url_)
    if not base:
        return None
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


def ensure_icons_in_cache(api_url_: str):
    ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for key, local_name in ICON_FILES.items():
        cache_path = ICON_CACHE_DIR / local_name
        if cache_path.exists():
            continue
        raw = download_and_extract_icon_raw_png(key, api_url_)
        if raw:
            with open(cache_path, "wb") as f:
                f.write(raw)


def crop_top_left(im: Image.Image, crop_w=165, crop_h=165) -> Image.Image:
    w, h = im.size
    return im.crop((0, 0, min(crop_w, w), min(crop_h, h)))


def crop_box(im: Image.Image, left: int, top: int, width: int, height: int) -> Image.Image:
    right = min(left + width, im.size[0])
    lower = min(top + height, im.size[1])
    left = max(0, left)
    top = max(0, top)
    return im.crop((left, top, right, lower))


def load_icon_processed_from_cache(key: str, size=ICON_SIZE):
    cache_path = ICON_CACHE_DIR / ICON_FILES[key]
    if not cache_path.exists():
        return None
    try:
        im = Image.open(str(cache_path)).convert("RGBA")
        w, h = im.size
        if key in ("gold", "silver") and max(w, h) >= 200:
            im = crop_top_left(im, 165, 165)
        elif key == "bsc" and (w, h) == (128, 128):
            im = crop_box(im, 4, 4, 64, 64)
        return im.resize(size, RESAMPLE)
    except Exception:
        return None


ensure_icons_in_cache(api_url)
icon_gems = load_icon_processed_from_cache("gems")
icon_bsc = load_icon_processed_from_cache("bsc")
icon_gold = load_icon_processed_from_cache("gold")
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


font_med = _load_font(FONT_MED_PATH, 21)
font_small = _load_font(FONT_SMALL_PATH, 15)


def _bar_masks(size_xy, bar_rect, radius, fill_w):
    bg = Image.new("L", size_xy, 0)
    ImageDraw.Draw(bg).rounded_rectangle(bar_rect, radius=radius, fill=255)
    fill = Image.new("L", size_xy, 0)
    if fill_w > 0:
        x1, y1, x2, y2 = bar_rect
        ImageDraw.Draw(fill).rectangle((x1, y1, x1 + fill_w, y2), fill=255)
    return bg, fill


def draw_rounded_progress(img, draw, bar_rect, frac, fill_color,
                          bg_color=(40, 40, 40, 200), outline=BAR_OUTLINE, outline_w=1, radius=10):
    x1, y1, x2, y2 = bar_rect
    w = max(0, int(x2 - x1))
    fill_w = int(round(w * max(0.0, min(1.0, frac))))

    draw.rounded_rectangle(bar_rect, radius=radius, fill=bg_color, outline=outline, width=outline_w)
    if fill_w <= 0:
        return

    bg_mask, fill_mask = _bar_masks(img.size, bar_rect, radius, fill_w)
    clip_mask = ImageChops.multiply(bg_mask, fill_mask)

    fill_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(fill_layer).rounded_rectangle(bar_rect, radius=radius, fill=fill_color)
    img.paste(fill_layer, (0, 0), clip_mask)


def draw_progress_block(y, value, goal, icon, bar_color, title="", meta_suffix=""):
    bar_x = PADDING + (ICON_SIZE[0] + 10 if icon else 0)
    if icon:
        img.paste(icon, (PADDING, y + (ROW_HEIGHT - ICON_SIZE[1]) // 2), icon)

    draw.text((bar_x, y), title, font=font_med, fill=(255, 255, 255))
    pct = percent_str(value, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + BAR_WIDTH - w, y), pct, font=font_small, fill=(220, 220, 220))

    bbox = draw.textbbox((0, 0), title, font=font_med)
    title_h = bbox[3] - bbox[1]
    bar_y = y + title_h + TITLE_BAR_GAP

    frac = 0.0 if goal <= 0 else min(float(value) / float(goal), 1.0)
    bar_rect = (bar_x, bar_y, bar_x + BAR_WIDTH, bar_y + BAR_HEIGHT)
    draw_rounded_progress(img, draw, bar_rect, frac, bar_color, radius=10)

    remaining_units = max(int(goal) - int(value), 0)
    meta = f"Remaining: {fmt_int(remaining_units)} • Goal: {fmt_int(goal)}{meta_suffix}"
    draw.text((bar_x, bar_y + BAR_HEIGHT + 4), meta, font=font_small, fill=(210, 210, 210))


def draw_stacked_bsc_block(y, segments, goal, title, icon=None, eta_text=None):
    bar_x = PADDING + (ICON_SIZE[0] + 10 if icon else 0)
    if icon:
        img.paste(icon, (PADDING, y + (ROW_HEIGHT - ICON_SIZE[1]) // 2), icon)

    draw.text((bar_x, y), title, font=font_med, fill=(255, 255, 255))
    total_bsc = sum(v for _, v, _ in segments)
    pct = percent_str(total_bsc, goal)
    w = draw.textlength(pct, font=font_small)
    draw.text((bar_x + BAR_WIDTH - w, y), pct, font=font_small, fill=(220, 220, 220))

    bbox = draw.textbbox((0, 0), title, font=font_med)
    title_h = bbox[3] - bbox[1]
    bar_y = y + title_h + TITLE_BAR_GAP
    bar_rect = (bar_x, bar_y, bar_x + BAR_WIDTH, bar_y + BAR_HEIGHT)

    draw.rounded_rectangle(bar_rect, radius=10, fill=(40, 40, 40, 200), outline=BAR_OUTLINE, width=1)

    bg_mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(bg_mask).rounded_rectangle(bar_rect, radius=10, fill=255)

    used_px = 0
    for _, val, color in segments:
        if goal <= 0 or val <= 0:
            continue
        seg_w = int(round(BAR_WIDTH * (float(val) / float(goal))))
        if seg_w <= 0:
            continue
        seg_w = min(seg_w, BAR_WIDTH - used_px)
        if seg_w <= 0:
            break

        seg_mask = Image.new("L", img.size, 0)
        x1, y1, x2, y2 = bar_rect
        ImageDraw.Draw(seg_mask).rectangle((x1 + used_px, y1, x1 + used_px + seg_w, y2), fill=255)
        clip = ImageChops.multiply(bg_mask, seg_mask)

        seg_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(seg_layer).rectangle((x1 + used_px, y1, x1 + used_px + seg_w, y2), fill=color)
        img.paste(seg_layer, (0, 0), clip)

        used_px += seg_w
        if used_px >= BAR_WIDTH:
            break

    # Legend with colored boxes, constrained to BAR_WIDTH
    legend_y = bar_y + BAR_HEIGHT + LEGEND_GAP
    lx = bar_x
    x_limit = bar_x + BAR_WIDTH
    box = 10
    gap = 4
    pad_after = 16

    for (name, val, col) in segments:
        label = f"{name} {fmt_int(val)}"
        bbox = draw.textbbox((0, 0), label, font=font_small)
        tw = bbox[2] - bbox[0]
        item_w = box + gap + tw + pad_after

        if lx + item_w > x_limit:
            lx = bar_x
            legend_y += 18

        draw.rectangle((lx, legend_y + 4, lx + box, legend_y + 4 + box), fill=col)
        draw.text((lx + box + gap, legend_y), label, font=font_small, fill=(210, 210, 210))
        lx += item_w

    remaining = max(int(goal) - int(total_bsc), 0)
    meta_y = legend_y + 18
    meta = f"Remaining: {fmt_int(remaining)} • Goal: {fmt_int(goal)}"
    draw.text((bar_x, meta_y), meta, font=font_small, fill=(200, 200, 200))

    if eta_text:
        draw.text((bar_x, meta_y + 18), eta_text, font=font_small, fill=(200, 200, 200))


# --- compose image ---
extra_bottom = 120 if ETA_ENABLE else 100
img_h = PADDING * 2 + 4 * ROW_HEIGHT + extra_bottom
img = Image.new("RGBA", (IMG_WIDTH, img_h), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

now = datetime.now()
date_str = f"{now.day} {MONTHS_EN[now.month]} {now.year}"
draw.text((PADDING, 6), date_str, font=font_small, fill=(180, 180, 180))

segments = [
    ("BSC", bsc_base, COLOR_BSC_BASE),
    ("Gold", bsc_from_gold, COLOR_GOLD),
    ("Silver", bsc_from_silver, COLOR_SILVER),
    ("Gems", bsc_from_gems, COLOR_GEMS),
]
if EVENT_ENABLE and event_total_bsc > 0:
    segments.append((EVENT_NAME, event_total_bsc, COLOR_EVENT))

y0 = 26
draw_progress_block(y0 + 0 * ROW_HEIGHT, gold, gold_goal_units, icon_gold, COLOR_GOLD,
                    title="Gold-Chests", meta_suffix=" (1 ≈ 1 BSC)")
draw_progress_block(y0 + 1 * ROW_HEIGHT, silver, silver_goal_units, icon_silver, COLOR_SILVER,
                    title="Silver-Chests", meta_suffix=" (10 ≈ 1 BSC)")
draw_progress_block(y0 + 2 * ROW_HEIGHT, gems, gems_goal_units, icon_gems, COLOR_GEMS,
                    title="Gems", meta_suffix=" (500 = 1 BSC)")
draw_stacked_bsc_block(y0 + 3 * ROW_HEIGHT, segments, GOAL_BSC, "Blacksmith Contracts", icon=icon_bsc, eta_text=eta_text)

img.save(OUTPUT_PATH)
print(f"✅ Overlay saved as {OUTPUT_PATH}")