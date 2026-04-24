# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# Core
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")

# Railway:
# If you add a Railway Volume mounted at /data,
# set DATA_DIR=/data in Railway variables.
DATA_DIR = os.getenv("DATA_DIR", "./data")

# =========================
# Aternos
# =========================
AT_USER = os.getenv("ATERNOS_USERNAME")
AT_PASS = os.getenv("ATERNOS_PASSWORD")
ATERNOS_SUBDOMAIN = os.getenv("ATERNOS_SUBDOMAIN")

# =========================
# Guild / Channels / Roles
# =========================
COVER_BOT_ID = 684773505157431347
COVER_INVITE_URL = "https://top.gg/bot/684773505157431347/invite?campaign=210-3"
RESTRICT_GUILD_NAME = "QMUL - Unofficial"

ANNOUNCEMENT_CHANNEL_ID = 1433248053665726547
WELCOME_CHANNEL_ID = 1433248053665726546
MARKET_ANNOUNCE_CHANNEL_ID = 1433412796531347586
SUGGESTION_CHANNEL_ID = 1433413006842396682
LEVEL_ANNOUNCE_CHANNEL_ID = 1433417692320239666

TOP_ROLE_NAME = "🌟 EXP Top"

# =========================
# Economy / XP
# =========================
XP_PER_MESSAGE = 10

INTEREST_RATE = 0.02
INTEREST_INTERVAL = 3600  # hourly

DIVIDEND_RATE = 0.01
DIVIDEND_INTERVAL = 86400  # daily

# =========================
# Gambling
# =========================
GAMBLE_FEE_FLAT = 25
GAMBLE_FEE_RATE = 0.00
GAMBLE_TIMEOUT_RAKE_RATE = 0.10

# =========================
# Zip backup
# =========================
PACKAGE_USER_ID = 734468552903360594
PACKAGE_FILES = [
    "data.json",
    "coins.json",
    "trivia_stats.json",
    "trivia_streaks.json",
    "beg_stats.json",
    "prayer_notif_state.json",
    "ramadan_post_state.json",
    "swear_jar.json",
    "sticker.json",
]

# =========================
# Shop / Items
# =========================
SHOP_ITEMS = [
    "Anime body pillow",
    "Oreo plush",
    "Rtx5090",
    "Crash token",
    "Imran's nose",
]

ITEM_PRICES = {
    "Anime body pillow": 30000,
    "Oreo plush": 15000,
    "Rtx5090": 150000,
    "Crash token": 175000,
    "Imran's nose": 999999,
}

CRASH_TOKEN_NAME = "Crash token"
SHOP_SELLBACK_RATE = 0.50

# =========================
# Stocks
# =========================
STOCKS = ["Oreobux", "QMkoin", "Seelsterling", "Fwizfinance", "BingBux"]

# These are still safe to keep for future expansion,
# even if your current market cog is simpler.
STOCK_TRADE_COOLDOWN_SECONDS = 5 * 60
STOCK_DAILY_TRADE_LIMIT = 20
STOCK_SPREAD_BPS = 200
STOCK_FEE_FLAT = 10
STOCK_FEE_RATE = 0.01
STOCK_MAX_IMPACT = 0.05

STOCK_LIQUIDITY = {
    "Oreobux": 2000,
    "QMkoin": 1600,
    "Seelsterling": 1200,
    "Fwizfinance": 1000,
    "BingBux": 1800,
}

# Fairer long-term market behaviour
DEFAULT_STOCK_CONFIG = {
    # Drift is near-zero so prices don't inflate automatically every tick.
    # Volatility is halved so moves are more gradual.
    # Fair value acts as a magnet — prices revert toward it over time.
    "Oreobux": {
        "price": 100,
        "fair_value": 100.0,
        "volatility": 0.012,   # was 0.025
        "drift": 0.0001,       # was 0.002
        "liquidity": 1400,
        "history": [100],
    },
    "QMkoin": {
        "price": 150,
        "fair_value": 150.0,
        "volatility": 0.015,   # was 0.035
        "drift": 0.0001,       # was 0.003
        "liquidity": 1200,
        "history": [150],
    },
    "Seelsterling": {
        "price": 200,
        "fair_value": 200.0,
        "volatility": 0.010,   # was 0.020
        "drift": 0.0001,       # was 0.0015
        "liquidity": 1800,
        "history": [200],
    },
    "Fwizfinance": {
        "price": 250,
        "fair_value": 250.0,
        "volatility": 0.020,   # was 0.050
        "drift": 0.0001,       # was 0.0035
        "liquidity": 900,
        "history": [250],
    },
    "BingBux": {
        "price": 120,
        "fair_value": 120.0,
        "volatility": 0.013,   # was 0.030
        "drift": 0.0001,       # was 0.002
        "liquidity": 1300,
        "history": [120],
    },
}

DIVIDEND_YIELD = {
    "Oreobux": 0.008,
    "QMkoin": 0.006,
    "Seelsterling": 0.010,
    "Fwizfinance": 0.004,
    "BingBux": 0.007,
}

MAX_NORMAL_MOVE = 0.04   # was 0.08 — halved
MAX_EVENT_MOVE  = 0.09   # was 0.18 — halved
PRICE_FLOOR = 1

# =========================
# Rob / Bankrob
# =========================
ALWAYS_BANKROB_USER_ID = 734468552903360594
BANKROB_STEAL_MIN_PCT = 0.12
BANKROB_STEAL_MAX_PCT = 0.28
BANKROB_MIN_STEAL = 100
BANKROB_MAX_STEAL_PCT_CAP = 0.40

# =========================
# Swear jar
# =========================
SWEAR_FINE_ENABLED = True
SWEAR_FINE_AMOUNT = 10

# =========================
# Minecraft
# =========================
MC_NAME = "QMUL Survival"
MC_ADDRESS = "185.206.150.153"
MC_JAVA_PORT = None

MC_MODRINTH_URL = ""
MC_MAP_URL = ""
MC_RULES_URL = ""
MC_DISCORD_URL = "https://discord.gg/6PxXwS7c"

MC_VERSION = "1.20.10"
MC_LOADER = "Fabric"
MC_MODPACK_NAME = "QMUL Survival Pack"
MC_WHITELISTED = False
MC_REGION = "UK / London"

MC_NOTES = [
    "Be respectful — no griefing.",
    "No x-ray / cheating clients.",
    "Ask an admin if you need help.",
]

MC_SHOW_BEDROCK = False
MC_BEDROCK_PORT = 22165
