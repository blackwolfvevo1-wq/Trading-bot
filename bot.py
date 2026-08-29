import os
import asyncio
import threading
import time
import requests
import pandas as pd
import numpy as np

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================================================
# CONFIG
# =========================================================

# التوكن والـ ID محطوطين ديركت باش نتجاوزو مشكلة Render
BOT_TOKEN = "8829847415:AAGoiHSjaSfZ_Bjm1kC7uGh0BQ7FCcDMhHU"
CHAT_ID = "6937661753"

BINANCE_URL = "https://fapi.binance.com"
COINGECKO_URL = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/"

ALERT_INTERVAL = 300
ALERT_COOLDOWN = 1800

# =========================================================
# RENDER WEB SERVER
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "ULTRA PRO MAX BOT ONLINE 🚀"

def run_web():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# SECURITY
# =========================================================

def allowed(update):
    chat = update.effective_chat

    if not chat:
        return False

    return str(chat.id) == str(CHAT_ID)

# =========================================================
# HTTP
# =========================================================

def get_json(url, params=None):
    r = requests.get(
        url,
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()

# =========================================================
# BINANCE
# =========================================================

def get_klines(symbol, interval, limit=250):

    data = get_json(
        f"{BINANCE_URL}/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )

    columns = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore"
    ]

    df = pd.DataFrame(
        data,
        columns=columns
    )

    for c in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:
        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

    return df


def get_funding(symbol):

    data = get_json(
        f"{BINANCE_URL}/fapi/v1/fundingRate",
        {
            "symbol": symbol,
            "limit": 1
        }
    )

    if not data:
        return 0

    return float(
        data[-1]["fundingRate"]
    )


def get_open_interest(symbol):

    data = get_json(
        f"{BINANCE_URL}/fapi/v1/openInterest",
        {
            "symbol": symbol
        }
    )

    return float(
        data["openInterest"]
    )


def get_long_short(symbol):

    try:

        data = get_json(
            f"{BINANCE_URL}/futures/data/globalLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": "5m",
                "limit": 1
            }
        )

        if not data:
            return 1

        return float(
            data[-1]["longShortRatio"]
        )

    except Exception:
        return 1

# =========================================================
# INDICATORS
# =========================================================

def ema(series, period):

    return series.ewm(
        span=period,
        adjust=False
    ).mean()


def rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    return (
        100 -
        100 / (1 + rs)
    ).fillna(50)


def macd(series):

    fast = ema(series, 12)
    slow = ema(series, 26)

    line = fast - slow
    signal = ema(line, 9)

    return line, signal, line - signal


def atr(df, period=14):

    hl = (
        df["high"] -
        df["low"]
    )

    hc = (
        df["high"] -
        df["close"].shift()
    ).abs()

    lc = (
        df["low"] -
        df["close"].shift()
    ).abs()

    tr = pd.concat(
        [hl, hc, lc],
        axis=1
    ).max(axis=1)

    return tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

# =========================================================
# CANDLE
# =========================================================

def candle_pattern(df):

    c = df.iloc[-1]
    p = df.iloc[-2]

    body = abs(
        c["close"] -
        c["open"]
    )

    rng = (
        c["high"] -
        c["low"]
    )

    if rng <= 0:
        return "غير واضحة"

    upper = (
        c["high"] -
        max(c["open"], c["close"])
    )

    lower = (
        min(c["open"], c["close"]) -
        c["low"]
    )

    if body <= rng * 0.1:
        return "Doji"

    if (
        p["close"] < p["open"]
        and
        c["close"] > c["open"]
        and
        c["open"] <= p["close"]
        and
        c["close"] >= p["open"]
    ):
        return "Bullish Engulfing 🟢"

    if (
        p["close"] > p["open"]
        and
        c["close"] < c["open"]
        and
        c["open"] >= p["close"]
        and
        c["close"] <= p["open"]
    ):
        return "Bearish Engulfing 🔴"

    if lower > body * 2 and upper < body:
        return "Hammer 🟢"

    if upper > body * 2 and lower < body:
        return "Shooting Star 🔴"

    return (
        "Bullish Candle 🟢"
        if c["close"] > c["open"]
        else
        "Bearish Candle 🔴"
    )

# =========================================================
# TECHNICAL ANALYSIS
# =========================================================

def technical(symbol, interval):

    df = get_klines(
        symbol,
        interval
    )

    close = df["close"]

    df["ema20"] = ema(close, 20)
    df["ema50"] = ema(close, 50)
    df["ema200"] = ema(close, 200)
    df["rsi"] = rsi(close)

    (
        df["macd"],
        df["signal"],
        df["hist"]
    ) = macd(close)

    df["atr"] = atr(df)

    last = df.iloc[-1]

    score = 0
    reasons = []

    if (
        last["ema20"] >
        last["ema50"] >
        last["ema200"]
    ):
        score += 2
        reasons.append("EMA صاعد")

    elif (
        last["ema20"] <
        last["ema50"] <
        last["ema200"]
    ):
        score -= 2
        reasons.append("EMA هابط")

    if 50 < last["rsi"] < 70:
        score += 1
        reasons.append("RSI إيجابي")

    elif 30 < last["rsi"] < 50:
        score -= 1
        reasons.append("RSI سلبي")

    if last["macd"] > last["signal"]:
        score += 1
        reasons.append("MACD صاعد")
    else:
        score -= 1
        reasons.append("MACD هابط")

    avg_volume = (
        df["volume"]
        .tail(20)
        .mean()
    )

    volume_ratio = (
        last["volume"] / avg_volume
        if avg_volume
        else 1
    )

    if volume_ratio > 1.3:

        if last["close"] > last["open"]:
            score += 1
            reasons.append("Volume شرائي قوي")
        else:
            score -= 1
            reasons.append("Volume بيعي قوي")

    recent = df.tail(50)

    support = float(
        recent["low"].min()
    )

    resistance = float(
        recent["high"].max()
    )

    if score >= 3:
        trend = "صاعد 🟢"
    elif score <= -3:
        trend = "هابط 🔴"
    else:
        trend = "محايد 🟡"

    return {
        "price": float(last["close"]),
        "rsi": float(last["rsi"]),
        "macd": float(last["macd"]),
        "signal": float(last["signal"]),
        "atr": float(last["atr"]),
        "volume": float(volume_ratio),
        "pattern": candle_pattern(df),
        "support": support,
        "resistance": resistance,
        "score": score,
        "trend": trend,
        "reasons": reasons
    }

# =========================================================
# MULTI TIMEFRAME
# =========================================================

def multi_timeframe(symbol):

    result = {}

    for tf in [
        "5m",
        "15m",
        "1h",
        "4h"
    ]:

        try:
            result[tf] = technical(
                symbol,
                tf
            )
        except Exception as e:
            print(
                f"MTF ERROR {symbol} {tf}:",
                repr(e)
            )

    return result

# =========================================================
# HYPE
# =========================================================

def fear_greed():

    try:

        data = get_json(
            FEAR_GREED_URL,
            {"limit": 1}
        )

        item = data["data"][0]

        return (
            int(item["value"]),
            item["value_classification"]
        )

    except Exception:
        return 50, "Neutral"


def trending():

    try:

        data = get_json(
            f"{COINGECKO_URL}/search/trending"
        )

        result = []

        for item in data.get(
            "coins",
            []
        )[:10]:

            coin = item.get(
                "item",
                {}
            )

            symbol = coin.get(
                "symbol"
            )

            if symbol:
                result.append(
                    symbol.upper()
                )

        return result

    except Exception:
        return []


def hype():

    fear, name = fear_greed()
    coins = trending()

    score = 50

    if fear >= 75:
        score += 15
    elif fear >= 60:
        score += 8
    elif fear <= 25:
        score -= 15
    elif fear <= 40:
        score -= 8

    if "BTC" in coins:
        score += 10

    if "SOL" in coins:
        score += 10

    score = max(
        0,
        min(100, score)
    )

    if score >= 80:
        label = "🔥🔥 قوي جدًا"
    elif score >= 65:
        label = "🔥 قوي"
    elif score >= 45:
        label = "🟡 محايد"
    elif score >= 30:
        label = "🟠 ضعيف"
    else:
        label = "🔴 خوف"

    return {
        "score": score,
        "label": label,
        "fear": fear,
        "fear_name": name,
        "trending": coins
    }

# =========================================================
# WHALES
# =========================================================

def whales(symbol):

    try:

        data = get_json(
            f"{BINANCE_URL}/fapi/v1/aggTrades",
            {
                "symbol": symbol,
                "limit": 100
            }
        )

        buys = 0
        sells = 0
        largest = 0

        threshold = (
            500000
            if symbol == "BTCUSDT"
            else 100000
        )

        for trade in data:

            value = (
                float(trade["p"]) *
                float(trade["q"])
            )

            if value < threshold:
                continue

            largest = max(
                largest,
                value
            )

            if trade.get("m"):
                sells += value
            else:
                buys += value

        net = buys - sells

        if net > threshold:
            direction = "🐋 شراء كبير 🟢"
        elif net < -threshold:
            direction = "🐋 بيع كبير 🔴"
        else:
            direction = "🐋 محايد 🟡"

        return {
            "buy": buys,
            "sell": sells,
            "largest": largest,
            "direction": direction
        }

    except Exception as e:

        print(
            "WHALES ERROR:",
            repr(e)
        )

        return {
            "buy": 0,
            "sell": 0,
            "largest": 0,
            "direction": "غير متوفر"
        }

# =========================================================
# LIQUIDATIONS
# =========================================================

def liquidations(symbol):

    try:

        data = get_json(
            f"{BINANCE_URL}/fapi/v1/allForceOrders",
            {
                "symbol": symbol,
                "limit": 100
            }
        )

        long_liq = 0
        short_liq = 0

        for order in data:

            value = (
                float(order["price"]) *
                float(order["origQty"])
            )

            if order["side"] == "SELL":
                long_liq += value
            else:
                short_liq += value

        if short_liq > long_liq * 1.5:
            direction = "💥 Short Liquidations قوية 🟢"
        elif long_liq > short_liq * 1.5:
            direction = "💥 Long Liquidations قوية 🔴"
        else:
            direction = "💥 متوازنة 🟡"

        return {
            "long": long_liq,
            "short": short_liq,
            "direction": direction
        }

    except Exception as e:

        print(
            "LIQ ERROR:",
            repr(e)
        )

        return {
            "long": 0,
            "short": 0,
            "direction": "غير متوفر"
        }

# =========================================================
# SIGNAL ENGINE
# =========================================================

def signal(symbol, interval):

    tech = technical(
        symbol,
        interval
    )

    mtf = multi_timeframe(
        symbol
    )

    funding = get_funding(symbol)
    oi = get_open_interest(symbol)
    ls = get_long_short(symbol)
    hp = hype()
    wh = whales(symbol)

    score = tech["score"]

    for tf, weight in [
        ("1h", 2),
        ("4h", 2)
    ]:

        if tf in mtf:

            if mtf[tf]["trend"] == "صاعد 🟢":
                score += weight

            elif mtf[tf]["trend"] == "هابط 🔴":
                score -= weight

    if funding > 0.0005:
        score -= 1

    elif funding < -0.0005:
        score += 1

    if wh["direction"] == "🐋 شراء كبير 🟢":
        score += 1

    elif wh["direction"] == "🐋 بيع كبير 🔴":
        score -= 1

    if score >= 6:
        direction = "LONG 🟢"
    elif score <= -6:
        direction = "SHORT 🔴"
    else:
        direction = "WAIT 🟡"

    price = tech["price"]
    atr_value = tech["atr"]

    entry = price
    stop = None
    tp1 = None
    tp2 = None
    tp3 = None

    if direction.startswith("LONG"):

        stop = price - atr_value * 1.5
        tp1 = price + atr_value * 1.5
        tp2 = price + atr_value * 2.5
        tp3 = price + atr_value * 4

    elif direction.startswith("SHORT"):

        stop = price + atr_value * 1.5
        tp1 = price - atr_value * 1.5
        tp2 = price - atr_value * 2.5
        tp3 = price - atr_value * 4

    return {
        "symbol": symbol,
        "interval": interval,
        "tech": tech,
        "mtf": mtf,
        "funding": funding,
        "oi": oi,
        "long_short": ls,
        "hype": hp,
        "whales": wh,
        "score": score,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3
    }

# =========================================================
# FORMAT
# =========================================================

def format_signal(data):

    t = data["tech"]
    h = data["hype"]
    w = data["whales"]

    text = (
        "🚀 ULTRA PRO MAX\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"📊 {data['symbol']} FUTURES\n"
        f"⏱️ {data['interval']}\n\n"

        f"🎯 SIGNAL: {data['direction']}\n"
        f"🔥 SCORE: {data['score']}\n\n"

        f"💰 PRICE: {t['price']:.6f}\n\n"

        "📈 MULTI TIMEFRAME\n"
        f"5m: {data['mtf'].get('5m', {}).get('trend', '?')}\n"
        f"15m: {data['mtf'].get('15m', {}).get('trend', '?')}\n"
        f"1H: {data['mtf'].get('1h', {}).get('trend', '?')}\n"
        f"4H: {data['mtf'].get('4h', {}).get('trend', '?')}\n\n"

        "📊 INDICATORS\n"
        f"RSI: {t['rsi']:.2f}\n"
        f"MACD: "
        f"{'Bullish 🟢' if t['macd'] > t['signal'] else 'Bearish 🔴'}\n"
        f"Volume: {t['volume']:.2f}x\n"
        f"Candle: {t['pattern']}\n\n"

        f"🟢 Support: {t['support']:.6f}\n"
        f"🔴 Resistance: {t['resistance']:.6f}\n\n"

        "🔥 HYPE\n"
        f"Score: {h['score']}/100\n"
        f"{h['label']}\n"
        f"Fear & Greed: {h['fear']}/100\n\n"

        "🐋 WHALES\n"
        f"{w['direction']}\n"
        f"Buy: ${w['buy']:,.0f}\n"
        f"Sell: ${w['sell']:,.0f}\n"
        f"Largest: ${w['largest']:,.0f}\n\n"

        "⚡ FUTURES\n"
        f"Funding: {data['funding'] * 100:.4f}%\n"
        f"Long/Short: {data['long_short']:.2f}\n"
        f"Open Interest: {data['oi']:.2f}\n\n"
    )

    if data["stop"]:

        text += (
            "🎯 TRADE PLAN\n"
            f"Entry: {data['entry']:.6f}\n"
            f"SL: {data['stop']:.6f}\n"
            f"TP1: {data['tp1']:.6f}\n"
            f"TP2: {data['tp2']:.6f}\n"
            f"TP3: {data['tp3']:.6f}\n\n"
        )

    else:

        text += (
            "⏳ WAIT\n"
            "Confirmation موش كافية للدخول.\n\n"
        )

    text += (
        "⚠️ تحليل آلي وليس ضمان ربح.\n"
        "استعمل Risk Management."
    )

    return text

# =========================================================
# MENU
# =========================================================

def main_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "₿ BTC",
                callback_data="btc_menu"
            ),
            InlineKeyboardButton(
                "◎ SOL",
                callback_data="sol_menu"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Market",
                callback_data="market"
            ),
            InlineKeyboardButton(
                "🔥 Hype",
                callback_data="hype"
            )
        ],
        [
            InlineKeyboardButton(
                "🐋 Whales",
                callback_data="whales"
            ),
            InlineKeyboardButton(
                "💥 Liquidations",
                callback_data="liquidations"
            )
        ],
        [
            InlineKeyboardButton(
                "⚡ Futures",
                callback_data="futures"
            ),
            InlineKeyboardButton(
                "🚨 Alerts",
                callback_data="alerts"
            )
        ]
    ])


def timeframe_keyboard(prefix):

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "5m",
                callback_data=f"{prefix}_5m"
            ),
            InlineKeyboardButton(
                "15m",
                callback_data=f"{prefix}_15m"
            )
        ],
        [
            InlineKeyboardButton(
                "1H",
                callback_data=f"{prefix}_1h"
            ),
            InlineKeyboardButton(
                "4H",
                callback_data=f"{prefix}_4h"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Menu",
                callback_data="home"
            )
        ]
    ])

# =========================================================
# START
# =========================================================

async def start(update, context):

    if not allowed(update):
        return

    await update.message.reply_text(
        "🚀 ULTRA PRO MAX\n\n"
        "اختار شنوّة تحب تشوف:",
        reply_markup=main_keyboard()
    )

# =========================================================
# BUTTONS
# =========================================================

async def buttons(update, context):

    query = update.callback_query

    if str(query.message.chat.id) != str(CHAT_ID):
        await query.answer()
        return

    await query.answer()

    data = query.data

    if data == "home":

        await query.edit_message_text(
            "🚀 ULTRA PRO MAX\n\n"
            "اختار شنوّة تحب تشوف:",
            reply_markup=main_keyboard()
        )

        return

    if data == "btc_menu":

        await query.edit_message_text(
            "₿ BTC ANALYSIS\n\n"
            "اختار الـTimeframe:",
            reply_markup=timeframe_keyboard("btc")
        )

        return

    if data == "sol_menu":

        await query.edit_message_text(
            "◎ SOL ANALYSIS\n\n"
            "اختار الـTimeframe:",
            reply_markup=timeframe_keyboard("sol")
        )

        return

    if data.startswith("btc_") or data.startswith("sol_"):

        coin, tf = data.split("_")

        symbol = (
            "BTCUSDT"
            if coin == "btc"
            else "SOLUSDT"
        )

        await query.edit_message_text(
            f"⏳ جاري تحليل {symbol} {tf}..."
        )

        try:

            result = signal(
                symbol,
                tf
            )

            await query.edit_message_text(
                format_signal(result),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data=data
                        ),
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        except Exception as e:

            print(
                "ANALYSIS ERROR:",
                repr(e)
            )

            await query.edit_message_text(
                "❌ صار خطأ في جلب البيانات.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        return

    if data == "hype":

        try:

            h = hype()

            await query.edit_message_text(
                "🔥 CRYPTO HYPE\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🔥 Score: {h['score']}/100\n"
                f"{h['label']}\n\n"
                f"🌡 Fear & Greed: "
                f"{h['fear']}/100\n"
                f"{h['fear_name']}\n\n"
                "📈 Trending:\n"
                f"{', '.join(h['trending']) or 'No data'}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data="hype"
                        ),
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        except Exception as e:

            print(
                "HYPE ERROR:",
                repr(e)
            )

            await query.edit_message_text(
                "❌ Hype API error.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        return

    if data == "market":

        await query.edit_message_text(
            "⏳ جاري فحص السوق..."
        )

        try:

            btc = signal(
                "BTCUSDT",
                "15m"
            )

            sol = signal(
                "SOLUSDT",
                "15m"
            )

            await query.edit_message_text(
                "🌍 MARKET DASHBOARD\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"₿ BTC\n"
                f"{btc['direction']}\n"
                f"Score: {btc['score']}\n"
                f"Price: {btc['tech']['price']:.2f}\n\n"

                f"◎ SOL\n"
                f"{sol['direction']}\n"
                f"Score: {sol['score']}\n"
                f"Price: {sol['tech']['price']:.4f}\n\n"

                f"🔥 Hype: "
                f"{btc['hype']['score']}/100\n"
                f"🌡 Fear & Greed: "
                f"{btc['hype']['fear']}/100",

                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data="market"
                        ),
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        except Exception as e:

            print(
                "MARKET ERROR:",
                repr(e)
            )

            await query.edit_message_text(
                "❌ Market data error.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        return

    if data == "whales":

        await query.edit_message_text(
            "⏳ جاري فحص Whale Activity..."
        )

        try:

            btc = whales("BTCUSDT")
            sol = whales("SOLUSDT")

            await query.edit_message_text(
                "🐋 WHALE ACTIVITY\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                "₿ BTC\n"
                f"{btc['direction']}\n"
                f"Buy: ${btc['buy']:,.0f}\n"
                f"Sell: ${btc['sell']:,.0f}\n\n"

                "◎ SOL\n"
                f"{sol['direction']}\n"
                f"Buy: ${sol['buy']:,.0f}\n"
                f"Sell: ${sol['sell']:,.0f}",

                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data="whales"
                        ),
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        except Exception as e:

            print(
                "WHALE BUTTON ERROR:",
                repr(e)
            )

            await query.edit_message_text(
                "❌ Whale data error."
            )

        return

    if data == "liquidations":

        await query.edit_message_text(
            "⏳ جاري فحص Liquidations..."
        )

        try:

            btc = liquidations(
                "BTCUSDT"
            )

            sol = liquidations(
                "SOLUSDT"
            )

            await query.edit_message_text(
                "💥 LIQUIDATIONS\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                "₿ BTC\n"
                f"{btc['direction']}\n"
                f"Long Liq: ${btc['long']:,.0f}\n"
                f"Short Liq: ${btc['short']:,.0f}\n\n"

                "◎ SOL\n"
                f"{sol['direction']}\n"
                f"Long Liq: ${sol['long']:,.0f}\n"
                f"Short Liq: ${sol['short']:,.0f}",

                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data="liquidations"
                        ),
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        except Exception as e:

            print(
                "LIQ BUTTON ERROR:",
                repr(e)
            )

            await query.edit_message_text(
                "❌ Liquidation data error."
            )

        return

    if data == "futures":

        await query.edit_message_text(
            "⏳ جاري جلب Futures Data..."
        )

        try:

            btc_f = get_funding(
                "BTCUSDT"
            )

            sol_f = get_funding(
                "SOLUSDT"
            )

            btc_ls = get_long_short(
                "BTCUSDT"
            )

            sol_ls = get_long_short(
                "SOLUSDT"
            )

            await query.edit_message_text(
                "⚡ FUTURES DATA\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                "₿ BTC\n"
                f"Funding: {btc_f * 100:.4f}%\n"
                f"Long/Short: {btc_ls:.2f}\n\n"

                "◎ SOL\n"
                f"Funding: {sol_f * 100:.4f}%\n"
                f"Long/Short: {sol_ls:.2f}",

                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data="futures"
                        ),
                        InlineKeyboardButton(
                            "🔙 Menu",
                            callback_data="home"
                        )
                    ]
                ])
            )

        except Exception as e:

            print(
                "FUTURES ERROR:",
                repr(e)
            )

            await query.edit_message_text(
                "❌ Futures API error."
            )

        return

    if data == "alerts":

        await query.edit_message_text(
            "🚨 ALERT SYSTEM\n\n"
            "Alerts تعمل تلقائيًا على:\n"
            "₿ BTCUSDT\n"
            "◎ SOLUSDT\n\n"
            "الفحص كل 5 دقائق.\n"
            "التنبيه فقط وقت signal قوي.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Menu",
                        callback_data="home"
                    )
                ]
            ])
        )

# =========================================================
# AUTOMATIC ALERTS
# =========================================================

async def alert_loop(application):

    last_alert = {}

    while True:

        try:

            for symbol in [
                "BTCUSDT",
                "SOLUSDT"
            ]:

                result = signal(
                    symbol,
                    "15m"
                )

                direction = result["direction"]
                score = result["score"]

                if (
                    direction in [
                        "LONG 🟢",
                        "SHORT 🔴"
                    ]
                    and
                    abs(score) >= 7
                ):

                    key = (
                        symbol,
                        direction
                    )

                    now = time.time()

                    if (
                        key not in last_alert
                        or
                        now -
                        last_alert[key]
                        >=
                        ALERT_COOLDOWN
                    ):

                        await application.bot.send_message(
                            chat_id=CHAT_ID,
                            text=(
                                "🚨 ULTRA PRO ALERT 🚨\n\n"
                                +
                                format_signal(
                                    result
                                )
                            )
                        )

                        last_alert[key] = now

        except Exception as e:

            print(
                "ALERT ERROR:",
                repr(e)
            )

        await asyncio.sleep(
            ALERT_INTERVAL
        )

# =========================================================
# STARTUP
# =========================================================

async def post_init(application):

    asyncio.create_task(
        alert_loop(application)
    )


async def error_handler(
    update,
    context
):

    print(
        "TELEGRAM ERROR:",
        repr(context.error)
    )


def main():

    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            buttons
        )
    )

    application.add_error_handler(
        error_handler
    )

    print(
        "🚀 ULTRA PRO MAX BOT STARTED"
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
