import io
import zipfile
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
import random

import storage
from config import (
    INTEREST_INTERVAL,
    INTEREST_RATE,
    DIVIDEND_INTERVAL,
    DIVIDEND_RATE,
    MARKET_ANNOUNCE_CHANNEL_ID,
    STOCKS,
    PACKAGE_USER_ID,
    PACKAGE_FILES,
    DEFAULT_STOCK_CONFIG,
    DIVIDEND_YIELD,
    MAX_NORMAL_MOVE,
    MAX_EVENT_MOVE,
    PRICE_FLOOR,
)
from storage import load_coins, save_coins, load_stocks, save_stocks


from ui_utils import C, E
EMBED_COLOR = C.ECONOMY


def make_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=EMBED_COLOR)


# =========================================================
# Generic helpers
# =========================================================
def _utc_now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _today_utc_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _data_root() -> Path:
    root = getattr(storage, "DATA_PATH", ".")
    return Path(root)


def _existing_files(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        try:
            pp = Path(p)
            if pp.exists() and pp.is_file():
                out.append(str(pp))
        except Exception:
            pass
    return out


# =========================================================
# Coins / portfolio helpers
# =========================================================
def _ensure_stock_fields(user: dict):
    user.setdefault("portfolio", {s: 0 for s in STOCKS})
    if not isinstance(user.get("portfolio"), dict):
        user["portfolio"] = {s: 0 for s in STOCKS}
    for s in STOCKS:
        user["portfolio"].setdefault(s, 0)

    user.setdefault("pending_portfolio", [])
    if not isinstance(user.get("pending_portfolio"), list):
        user["pending_portfolio"] = []

    user.setdefault("trade_meta", {})
    tm = user["trade_meta"]
    if not isinstance(tm, dict):
        tm = {}
        user["trade_meta"] = tm

    tm.setdefault("last_trade_ts", {})
    if not isinstance(tm.get("last_trade_ts"), dict):
        tm["last_trade_ts"] = {}

    tm.setdefault("daily", {"day": _today_utc_key(), "count": 0})
    if not isinstance(tm.get("daily"), dict):
        tm["daily"] = {"day": _today_utc_key(), "count": 0}
    tm["daily"].setdefault("day", _today_utc_key())
    tm["daily"].setdefault("count", 0)


def _settle_pending_for_user(user: dict) -> int:
    _ensure_stock_fields(user)
    now = _utc_now_ts()
    pending = user.get("pending_portfolio", [])
    if not pending:
        return 0

    still_pending = []
    settled_total = 0

    for lot in pending:
        try:
            settles_at = float(lot.get("settles_at", 0))
            stock = lot.get("stock")
            shares = int(lot.get("shares", 0))

            if settles_at <= now and stock in STOCKS and shares > 0:
                user["portfolio"][stock] = int(user["portfolio"].get(stock, 0)) + shares
                settled_total += shares
            else:
                still_pending.append(lot)
        except Exception:
            still_pending.append(lot)

    user["pending_portfolio"] = still_pending
    return settled_total


# =========================================================
# Stock DB helpers
# =========================================================
def _default_stock_entry(stock_name: str) -> dict:
    template = DEFAULT_STOCK_CONFIG.get(stock_name)
    if template:
        return {
            "price": int(template["price"]),
            "fair_value": float(template["fair_value"]),
            "volatility": float(template["volatility"]),
            "drift": float(template["drift"]),
            "liquidity": int(template["liquidity"]),
            "history": list(template["history"]),
        }

    return {
        "price": 100,
        "fair_value": 100.0,
        "volatility": 0.03,
        "drift": 0.002,
        "liquidity": 1200,
        "history": [100],
    }


def _ensure_stock_db() -> dict:
    data = load_stocks()
    if not isinstance(data, dict):
        data = {}

    fixed = {}
    changed = False

    for stock_name in STOCKS:
        entry = data.get(stock_name)

        if entry is None:
            for k, v in data.items():
                if str(k).lower() == stock_name.lower():
                    entry = v
                    changed = True
                    break

        if not isinstance(entry, dict):
            fixed[stock_name] = _default_stock_entry(stock_name)
            changed = True
            continue

        default = _default_stock_entry(stock_name)

        price = int(entry.get("price", default["price"]) or default["price"])
        fair_value = float(entry.get("fair_value", price))
        volatility = float(entry.get("volatility", default["volatility"]))
        drift = float(entry.get("drift", default["drift"]))
        liquidity = int(entry.get("liquidity", default["liquidity"]) or default["liquidity"])
        history = entry.get("history", default["history"])

        if not isinstance(history, list) or not history:
            history = [price]
            changed = True

        fixed[stock_name] = {
            "price": max(PRICE_FLOOR, price),
            "fair_value": max(float(PRICE_FLOOR), fair_value),
            "volatility": max(0.005, volatility),
            "drift": drift,
            "liquidity": max(1, liquidity),
            "history": [
                max(PRICE_FLOOR, int(x))
                for x in history[-240:]
                if isinstance(x, (int, float))
            ] or [price],
        }

        for key in ("fair_value", "volatility", "drift", "liquidity"):
            if key not in entry:
                changed = True

    if changed:
        save_stocks(fixed)

    return fixed


# =========================================================
# Backup helpers
# =========================================================
async def build_data_zip_bytes() -> tuple[io.BytesIO, list[str]]:
    included = _existing_files([str(_data_root() / f) for f in PACKAGE_FILES])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in included:
            zf.write(path, arcname=f"bot_backup/{Path(path).name}")

    buf.seek(0)
    return buf, included


async def dm_package_to_user(
    bot: commands.Bot,
    user_id: int,
    *,
    reason: str = "Scheduled backup"
) -> bool:
    try:
        user = await bot.fetch_user(int(user_id))
    except Exception as e:
        print(f"[Package] Failed to fetch user {user_id}: {e}")
        return False

    try:
        zip_buf, included = await build_data_zip_bytes()

        if not included:
            try:
                await user.send(
                    embed=make_embed(
                        "📦  Backup",
                        f"⚠️ Backup attempt ({reason}) — no files found to package."
                    )
                )
            except Exception:
                pass
            return True

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")
        file = discord.File(zip_buf, filename=f"qmul_bot_backup_{ts}.zip")

        embed = make_embed(
            "Bot Backup",
            f"Reason: **{reason}**\n"
            f"Included: {', '.join(Path(x).name for x in included)}"
        )

        await user.send(embed=embed, file=file)
        print(f"[Package] Sent backup zip to {user_id} ({len(included)} files).")
        return True

    except discord.Forbidden:
        print(f"[Package] DM failed: user {user_id} has DMs closed or bot blocked.")
        return False
    except Exception as e:
        print(f"[Package] Error building/sending zip: {e}")
        return False


# =========================================================
# Background tasks cog
# =========================================================
class BackgroundTasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.market_flow = {s: {"buy": 0, "sell": 0} for s in STOCKS}

        self.apply_bank_interest.start()
        self.update_stock_prices.start()
        self.pay_dividends.start()
        self.settle_all_pending.start()
        self.send_backup_zip_every_5h.start()

    def cog_unload(self):
        self.apply_bank_interest.cancel()
        self.update_stock_prices.cancel()
        self.pay_dividends.cancel()
        self.settle_all_pending.cancel()
        self.send_backup_zip_every_5h.cancel()

    def record_trade(self, stock_name: str, side: str, qty: int):
        if stock_name not in STOCKS:
            return
        if side not in ("buy", "sell"):
            return

        try:
            qty = max(0, int(qty))
        except Exception:
            return

        self.market_flow.setdefault(stock_name, {"buy": 0, "sell": 0})
        self.market_flow[stock_name][side] += qty

    @tasks.loop(seconds=INTEREST_INTERVAL)
    async def apply_bank_interest(self):
        try:
            coins = load_coins()
            changed = False

            for _uid, balances in (coins or {}).items():
                try:
                    bank_balance = int(balances.get("bank", 0) or 0)
                    if bank_balance <= 0:
                        continue

                    interest = int(bank_balance * INTEREST_RATE)
                    if interest > 0:
                        balances["bank"] = bank_balance + interest
                        changed = True
                except Exception:
                    continue

            if changed:
                save_coins(coins)
                print("[Interest] Applied interest to bank balances.")

        except Exception as e:
            print(f"[Interest] failed: {type(e).__name__}: {e}")

    @tasks.loop(minutes=5)
    async def update_stock_prices(self):
        try:
            stocks = _ensure_stock_db()
            changed = False

            crashed = []
            boomed = []

            for stock_name in STOCKS:
                stock = stocks.get(stock_name, _default_stock_entry(stock_name))

                current_price = max(PRICE_FLOOR, int(stock.get("price", 100)))
                fair_value = max(float(PRICE_FLOOR), float(stock.get("fair_value", current_price)))
                volatility = max(0.005, float(stock.get("volatility", 0.03)))
                drift = float(stock.get("drift", 0.002))
                liquidity = max(1, int(stock.get("liquidity", 1200)))

                flow = self.market_flow.get(stock_name, {"buy": 0, "sell": 0})
                buys  = int(flow.get("buy",  0))
                sells = int(flow.get("sell", 0))
                net_flow = buys - sells

                # Trade pressure: capped so large buy waves don't rocket prices
                pressure = max(-0.025, min(0.025, net_flow / max(liquidity, 1)))

                # Mean-reversion: pulls price back toward fair_value each tick
                reversion = ((fair_value - current_price) / max(fair_value, 1.0)) * 0.15

                # Random noise scaled to volatility
                noise = random.uniform(-volatility, volatility)

                # Events: 1% chance of crash, 1% chance of boom
                event_move = 0.0
                event_kind = None
                roll = random.random()
                if roll < 0.010:
                    event_move = -random.uniform(0.04, 0.09)
                    event_kind = "crash"
                elif roll > 0.990:
                    event_move = random.uniform(0.04, 0.09)
                    event_kind = "boom"

                # Drift excluded intentionally — even small positive drift compounds
                # exponentially over hundreds of 5-min ticks
                pct_change = reversion + pressure + noise + event_move
                move_cap   = MAX_EVENT_MOVE if event_kind else MAX_NORMAL_MOVE
                pct_change = max(-move_cap, min(move_cap, pct_change))

                new_price = max(PRICE_FLOOR, int(round(current_price * (1 + pct_change))))

                # Fair value is pinned to the configured baseline — never drifts.
                # This is critical: if fair_value creeps up, mean-reversion actively
                # pulls prices up with it, causing long-term inflation.
                configured_fair = float(
                    (DEFAULT_STOCK_CONFIG.get(stock_name) or {}).get("fair_value", fair_value)
                )
                new_fair_value = configured_fair

                stock["price"]      = new_price
                stock["fair_value"] = round(new_fair_value, 2)
                stock["history"]    = (stock.get("history") or []) + [new_price]
                stock["history"]    = stock["history"][-240:]

                stocks[stock_name] = stock
                changed = True

                if event_kind == "crash":
                    crashed.append((stock_name, current_price, new_price))
                elif event_kind == "boom":
                    boomed.append((stock_name, current_price, new_price))

            if changed:
                save_stocks(stocks)

            self.market_flow = {s: {"buy": 0, "sell": 0} for s in STOCKS}

            channel = self.bot.get_channel(MARKET_ANNOUNCE_CHANNEL_ID)
            if not channel:
                return

            if crashed:
                desc = "\n".join(
                    f"🔻 **{s}** fell from **{old}** → **{new}**"
                    for s, old, new in crashed
                )
                await channel.send(embed=make_embed("📉 Market Shock", desc))

            if boomed:
                desc = "\n".join(
                    f"📈 **{s}** rose from **{old}** → **{new}**"
                    for s, old, new in boomed
                )
                await channel.send(embed=make_embed("📈 Market Rally", desc))

        except Exception as e:
            print(f"[Stocks] update failed: {type(e).__name__}: {e}")

    @tasks.loop(seconds=DIVIDEND_INTERVAL)
    async def pay_dividends(self):
        try:
            coins = load_coins()
            stocks = _ensure_stock_db()
            any_payout = False

            for _uid, data in (coins or {}).items():
                try:
                    _ensure_stock_fields(data)
                    _settle_pending_for_user(data)

                    pf = data.get("portfolio", {}) or {}
                    payout_total = 0

                    for stock_name in STOCKS:
                        qty = int(pf.get(stock_name, 0) or 0)
                        if qty <= 0:
                            continue

                        price = int(stocks[stock_name]["price"])
                        stock_yield = float(DIVIDEND_YIELD.get(stock_name, DIVIDEND_RATE))
                        payout_total += int(qty * price * stock_yield)

                    if payout_total > 0:
                        data["wallet"] = int(data.get("wallet", 0) or 0) + payout_total
                        any_payout = True
                except Exception:
                    continue

            if any_payout:
                save_coins(coins)
                channel = self.bot.get_channel(MARKET_ANNOUNCE_CHANNEL_ID)
                if channel:
                    await channel.send(
                        embed=make_embed(
                            "💸 Dividends Paid",
                            "Dividends have been paid out to all shareholders."
                        )
                    )

        except Exception as e:
            print(f"[Dividends] failed: {type(e).__name__}: {e}")

    @tasks.loop(minutes=2)
    async def settle_all_pending(self):
        try:
            coins = load_coins()
            changed = False

            for _uid, user in (coins or {}).items():
                try:
                    _ensure_stock_fields(user)
                    if _settle_pending_for_user(user) > 0:
                        changed = True
                except Exception:
                    continue

            if changed:
                save_coins(coins)

        except Exception as e:
            print(f"[Settlement] failed: {type(e).__name__}: {e}")

    @tasks.loop(hours=5)
    async def send_backup_zip_every_5h(self):
        try:
            await dm_package_to_user(self.bot, PACKAGE_USER_ID, reason="Every 5 hours")
        except Exception as e:
            print(f"[BackupLoop] failed: {type(e).__name__}: {e}")

    @apply_bank_interest.before_loop
    @update_stock_prices.before_loop
    @pay_dividends.before_loop
    @settle_all_pending.before_loop
    @send_backup_zip_every_5h.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(BackgroundTasks(bot))
