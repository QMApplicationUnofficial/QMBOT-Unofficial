import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from config import DATA_DIR

# =========================
# Data directory (Railway safe)
# =========================

DATA_PATH = Path(DATA_DIR).resolve()
DATA_PATH.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = DATA_PATH / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# File paths
# =========================

DATA_FILE = DATA_PATH / "data.json"
COOLDOWN_FILE = DATA_PATH / "cooldowns.json"
COIN_DATA_FILE = DATA_PATH / "coins.json"
SHOP_FILE = DATA_PATH / "shop_stock.json"
INVENTORY_FILE = DATA_PATH / "inventories.json"
MARRIAGE_FILE = DATA_PATH / "marriages.json"
PLAYLIST_FILE = DATA_PATH / "playlists.json"
QUEST_FILE = DATA_PATH / "quests.json"
EVENT_FILE = DATA_PATH / "events.json"
STOCK_FILE = DATA_PATH / "stocks.json"
SUGGESTION_FILE = DATA_PATH / "suggestions.json"

TRIVIA_STATS_FILE = DATA_PATH / "trivia_stats.json"
TRIVIA_STREAKS_FILE = DATA_PATH / "trivia_streaks.json"

BEG_STATS_FILE = DATA_PATH / "beg_stats.json"

SWEAR_JAR_FILE = DATA_PATH / "swear_jar.json"
STICKER_FILE = DATA_PATH / "sticker.json"

ACTIONS_FILE = DATA_PATH / "actions.json"

print("[storage] ===========================")
print(f"[storage] DATA_DIR = {DATA_PATH}")
print(f"[storage] BACKUP_DIR = {BACKUP_DIR}")
print(f"[storage] DATA_DIR exists: {DATA_PATH.exists()}")
try:
    print(f"[storage] DATA_DIR entries: {[p.name for p in DATA_PATH.iterdir()]}")
except Exception as e:
    print(f"[storage] Could not list DATA_DIR: {e}")
print(f"[storage] COIN_DATA_FILE = {COIN_DATA_FILE}")
print(f"[storage] DATA_FILE = {DATA_FILE}")
print("[storage] ===========================")

# =========================
# Core JSON helpers
# =========================

def _load_json(path: Path, default: Any):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, obj: Any):
    """
    Atomic save so Railway crashes cannot corrupt files.
    Also keeps a backup copy of the old version.
    """
    temp = path.with_suffix(path.suffix + ".tmp")

    if path.exists():
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"{path.stem}.{ts}{path.suffix}.bak"
            shutil.copy2(path, backup_path)
        except Exception:
            pass

    with temp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=4, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    temp.replace(path)


# =========================
# Core bot data
# =========================

def load_data():
    return _load_json(DATA_FILE, {})

def save_data(d):
    _save_json(DATA_FILE, d)


def load_cooldowns():
    return _load_json(COOLDOWN_FILE, {})

def save_cooldowns(d):
    _save_json(COOLDOWN_FILE, d)


# =========================
# Economy
# =========================

def load_coins():
    return _load_json(COIN_DATA_FILE, {})

def save_coins(d):
    _save_json(COIN_DATA_FILE, d)


# =========================
# Marriages
# =========================

def load_marriages():
    return _load_json(MARRIAGE_FILE, {})

def save_marriages(d):
    _save_json(MARRIAGE_FILE, d)


# =========================
# Shop / inventory
# =========================

def load_shop_stock():
    return _load_json(SHOP_FILE, {})

def save_shop_stock(d):
    _save_json(SHOP_FILE, d)


def load_inventory():
    return _load_json(INVENTORY_FILE, {})

def save_inventory(d):
    _save_json(INVENTORY_FILE, d)


# =========================
# Music / misc systems
# =========================

def load_playlists():
    return _load_json(PLAYLIST_FILE, {})

def save_playlists(d):
    _save_json(PLAYLIST_FILE, d)


def load_quests():
    return _load_json(QUEST_FILE, {})

def save_quests(d):
    _save_json(QUEST_FILE, d)


def load_event():
    return _load_json(EVENT_FILE, {})

def save_event(d):
    _save_json(EVENT_FILE, d)


# =========================
# Stocks
# =========================

def load_stocks():
    return _load_json(STOCK_FILE, {})

def save_stocks(d):
    _save_json(STOCK_FILE, d)


# =========================
# Suggestions
# =========================

def load_suggestions():
    return _load_json(SUGGESTION_FILE, [])

def save_suggestions(d):
    _save_json(SUGGESTION_FILE, d)


# =========================
# Trivia
# =========================

def load_trivia_stats():
    return _load_json(TRIVIA_STATS_FILE, {})

def save_trivia_stats(d):
    _save_json(TRIVIA_STATS_FILE, d)


def load_trivia_streaks():
    return _load_json(TRIVIA_STREAKS_FILE, {})

def save_trivia_streaks(d):
    _save_json(TRIVIA_STREAKS_FILE, d)


# =========================
# Beg stats
# =========================

def load_beg_stats():
    return _load_json(BEG_STATS_FILE, {})

def save_beg_stats(d):
    _save_json(BEG_STATS_FILE, d)


# =========================
# Swear jar
# =========================

def load_swear_jar():
    jar = _load_json(SWEAR_JAR_FILE, {"total": 0, "users": {}})

    if not isinstance(jar, dict):
        jar = {"total": 0, "users": {}}

    jar.setdefault("total", 0)
    jar.setdefault("users", {})

    jar["total"] = int(jar.get("total", 0) or 0)

    if not isinstance(jar["users"], dict):
        jar["users"] = {}

    return jar


def save_swear_jar(d):
    _save_json(SWEAR_JAR_FILE, d)


# =========================
# Sticker tracking
# =========================

def load_stickers():
    data = _load_json(STICKER_FILE, {"total": 0, "users": {}, "daily": {}})

    if not isinstance(data, dict):
        data = {"total": 0, "users": {}, "daily": {}}

    data.setdefault("total", 0)
    data.setdefault("users", {})
    data.setdefault("daily", {})

    data["total"] = int(data.get("total", 0) or 0)

    if not isinstance(data["users"], dict):
        data["users"] = {}

    if not isinstance(data["daily"], dict):
        data["daily"] = {}

    return data


def save_stickers(d):
    _save_json(STICKER_FILE, d)


# =========================
# Actions
# =========================

def load_actions():
    return _load_json(ACTIONS_FILE, {})

def save_actions(d):
    _save_json(ACTIONS_FILE, d)
