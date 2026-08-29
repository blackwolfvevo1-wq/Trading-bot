import os
import threading
import requests
import pandas as pd
import numpy as np

from flask import Flask

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


# =========================================================
# الإعدادات
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

BINANCE_FUTURES = "https://fapi.binance.com"
COINGECKO_API = "https://api.coingecko.com/api/v3"
FEAR_GREED_API = "https://api.alternative.me/fng/"


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود في Render")

if not CHAT_ID:
    raise RuntimeError("CHAT_ID غير موجود في Render")


# =========================================================
# Render Web Server
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "PRO CRYPTO BOT - ONLINE"


def run_server():
    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# حماية Chat ID
# =========================================================

def مسموح(update: Update):

    if not update.effective_chat:
        return False

    return str(update.effective_chat.id) == str(CHAT_ID)


# =========================================================
# HTTP
# =========================================================

def get_json(url, params=None):

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# سعر العملة
# =========================================================

def get_price(symbol):

    data = get_json(
        f"{BINANCE_FUTURES}/fapi/v1/ticker/price",
        {
            "symbol": symbol
        }
    )

    return float(data["price"])


# =========================================================
# بيانات الشموع
# =========================================================

def get_klines(
    symbol,
    interval="15m",
    limit=250
):

    data = get_json(
        f"{BINANCE_FUTURES}/fapi/v1/klines",
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

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    return df


# =========================================================
# EMA
# =========================================================

def ema(series, length):

    return series.ewm(
        span=length,
        adjust=False
    ).mean()


# =========================================================
# RSI
# =========================================================

def rsi(series, length=14):

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / length,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / length,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    result = 100 - (
        100 / (1 + rs)
    )

    return result.fillna(50)


# =========================================================
# MACD
# =========================================================

def calculate_macd(series):

    fast = ema(
        series,
        12
    )

    slow = ema(
        series,
        26
    )

    macd_line = fast - slow

    signal = ema(
        macd_line,
        9
    )

    histogram = (
        macd_line -
        signal
    )

    return (
        macd_line,
        signal,
        histogram
    )


# =========================================================
# ATR
# =========================================================

def calculate_atr(df, length=14):

    high_low = (
        df["high"] -
        df["low"]
    )

    high_close = (
        df["high"] -
        df["close"].shift()
    ).abs()

    low_close = (
        df["low"] -
        df["close"].shift()
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_close,
            low_close
        ],
        axis=1
    ).max(axis=1)

    return true_range.ewm(
        alpha=1 / length,
        adjust=False
    ).mean()


# =========================================================
# قراءة نموذج الشمعة
# =========================================================

def candle_pattern(df):

    current = df.iloc[-1]
    previous = df.iloc[-2]

    body = abs(
        current["close"] -
        current["open"]
    )

    candle_range = (
        current["high"] -
        current["low"]
    )

    upper_wick = (
        current["high"] -
        max(
            current["open"],
            current["close"]
        )
    )

    lower_wick = (
        min(
            current["open"],
            current["close"]
        ) -
        current["low"]
    )

    # Doji
    if candle_range > 0 and body <= (
        candle_range * 0.10
    ):

        return "دوجي (Doji)"

    # Bullish Engulfing
    if (
        previous["close"] <
        previous["open"]
        and
        current["close"] >
        current["open"]
        and
        current["open"] <=
        previous["close"]
        and
        current["close"] >=
        previous["open"]
    ):

        return "ابتلاع شرائي (Bullish Engulfing)"

    # Bearish Engulfing
    if (
        previous["close"] >
        previous["open"]
        and
        current["close"] <
        current["open"]
        and
        current["open"] >=
        previous["close"]
        and
        current["close"] <=
        previous["open"]
    ):

        return "ابتلاع بيعي (Bearish Engulfing)"

    # Hammer
    if (
        lower_wick > body * 2
        and
        upper_wick < body
    ):

        return "مطرقة (Hammer)"

    # Shooting Star
    if (
        upper_wick > body * 2
        and
        lower_wick < body
    ):

        return "نجمة ساقطة (Shooting Star)"

    return "شمعة عادية"


# =========================================================
# الدعم والمقاومة
# =========================================================

def get_support_resistance(df):

    recent = df.tail(50)

    support = recent["low"].min()

    resistance = recent["high"].max()

    return (
        float(support),
        float(resistance)
    )


# =========================================================
# التحليل الفني
# =========================================================

def technical_analysis(
    symbol,
    interval
):

    df = get_klines(
        symbol,
        interval,
        250
    )

    close = df["close"]

    df["ema20"] = ema(
        close,
        20
    )

    df["ema50"] = ema(
        close,
        50
    )

    df["ema200"] = ema(
        close,
        200
    )

    df["rsi"] = rsi(
        close
    )

    (
        df["macd"],
        df["macd_signal"],
        df["macd_hist"]
    ) = calculate_macd(
        close
    )

    df["atr"] = calculate_atr(
        df
    )

    last = df.iloc[-1]

    score = 0

    reasons = []

    # EMA
    if (
        last["ema20"] >
        last["ema50"] >
        last["ema200"]
    ):

        score += 2

        reasons.append(
            "ترتيب EMA صاعد"
        )

    elif (
        last["ema20"] <
        last["ema50"] <
        last["ema200"]
    ):

        score -= 2

        reasons.append(
            "ترتيب EMA هابط"
        )

    # RSI
    if 50 < last["rsi"] < 70:

        score += 1

        reasons.append(
            "RSI إيجابي"
        )

    elif 30 < last["rsi"] < 50:

        score -= 1

        reasons.append(
            "RSI سلبي"
        )

    elif last["rsi"] >= 70:

        reasons.append(
            "RSI في منطقة تشبع شرائي"
        )

    elif last["rsi"] <= 30:

        reasons.append(
            "RSI في منطقة تشبع بيعي"
        )

    # MACD
    if (
        last["macd"] >
        last["macd_signal"]
    ):

        score += 1

        reasons.append(
            "MACD صاعد"
        )

    else:

        score -= 1

        reasons.append(
            "MACD هابط"
        )

    # Volume
    average_volume = (
        df["volume"]
        .tail(20)
        .mean()
    )

    volume_ratio = (
        last["volume"] /
        average_volume
        if average_volume > 0
        else 1
    )

    if volume_ratio > 1.3:

        if (
            last["close"] >
            last["open"]
        ):

            score += 1

            reasons.append(
                "حجم تداول قوي شرائي"
            )

        else:

            score -= 1

            reasons.append(
                "حجم تداول قوي بيعي"
            )

    # Candle
    pattern = candle_pattern(
        df
    )

    if pattern in [
        "ابتلاع شرائي (Bullish Engulfing)",
        "مطرقة (Hammer)"
    ]:

        score += 1

    elif pattern in [
        "ابتلاع بيعي (Bearish Engulfing)",
        "نجمة ساقطة (Shooting Star)"
    ]:

        score -= 1

    support, resistance = (
        get_support_resistance(df)
    )

    price = float(
        last["close"]
    )

    if score >= 3:

        trend = "صاعد 🟢"

    elif score <= -3:

        trend = "هابط 🔴"

    else:

        trend = "محايد 🟡"

    return {
        "df": df,
        "price": price,
        "score": score,
        "trend": trend,
        "rsi": float(last["rsi"]),
        "macd": float(last["macd"]),
        "macd_signal": float(
            last["macd_signal"]
        ),
        "atr": float(last["atr"]),
        "volume_ratio": float(
            volume_ratio
        ),
        "pattern": pattern,
        "support": support,
        "resistance": resistance,
        "reasons": reasons
    }


# =========================================================
# تحليل متعدد الفريمات
# =========================================================

def multi_timeframe(symbol):

    results = {}

    for interval in [
        "5m",
        "15m",
        "1h",
        "4h"
    ]:

        try:

            results[interval] = (
                technical_analysis(
                    symbol,
                    interval
                )
            )

        except Exception as e:

            print(
                f"MTF ERROR {symbol} {interval}:",
                repr(e)
            )

    return results


# =========================================================
# Funding Rate
# =========================================================

def get_funding(symbol):

    data = get_json(
        f"{BINANCE_FUTURES}/fapi/v1/fundingRate",
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


# =========================================================
# Open Interest
# =========================================================

def get_open_interest(symbol):

    data = get_json(
        f"{BINANCE_FUTURES}/fapi/v1/openInterest",
        {
            "symbol": symbol
        }
    )

    return float(
        data["openInterest"]
    )


# =========================================================
# Long / Short
# =========================================================

def get_long_short_ratio(symbol):

    try:

        data = get_json(
            f"{BINANCE_FUTURES}/futures/data/globalLongShortAccountRatio",
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
# Fear & Greed
# =========================================================

def get_fear_greed():

    data = get_json(
        FEAR_GREED_API,
        {
            "limit": 1
        }
    )

    item = data["data"][0]

    return (
        int(item["value"]),
        item["value_classification"]
    )


# =========================================================
# Market Data
# =========================================================

def get_global_market():

    data = get_json(
        f"{COINGECKO_API}/global"
    )

    return data["data"]


# =========================================================
# Trending Coins
# =========================================================

def get_trending():

    try:

        data = get_json(
            f"{COINGECKO_API}/search/trending"
        )

        result = []

        for coin in data.get(
            "coins",
            []
        )[:10]:

            item = coin.get(
                "item",
                {}
            )

            symbol = item.get(
                "symbol"
            )

            if symbol:
                result.append(
                    symbol.upper()
                )

        return result

    except Exception as e:

        print(
            "TRENDING ERROR:",
            repr(e)
        )

        return []


# =========================================================
# HYPE ENGINE
# =========================================================

def calculate_hype(symbol):

    fear_value, fear_name = (
        get_fear_greed()
    )

    global_market = (
        get_global_market()
    )

    btc_dominance = float(
        global_market
        .get(
            "market_cap_percentage",
            {}
        )
        .get(
            "btc",
            0
        )
    )

    trending = get_trending()

    short_symbol = symbol.replace(
        "USDT",
        ""
    )

    score = 50

    # Fear & Greed
    if fear_value >= 75:

        score += 15

    elif fear_value >= 60:

        score += 8

    elif fear_value <= 25:

        score -= 15

    elif fear_value <= 40:

        score -= 8

    # Trending
    if short_symbol in trending:

        score += 20

    # Altcoin context
    if short_symbol != "BTC":

        if btc_dominance < 50:

            score += 5

        elif btc_dominance > 60:

            score -= 5

    score = max(
        0,
        min(
            100,
            score
        )
    )

    if score >= 80:

        label = "حماس قوي جدًا 🔥🔥"

    elif score >= 65:

        label = "حماس قوي 🔥"

    elif score >= 45:

        label = "محايد 🟡"

    elif score >= 30:

        label = "حماس ضعيف 🟠"

    else:

        label = "خوف 🔴"

    return {
        "score": score,
        "label": label,
        "fear_value": fear_value,
        "fear_name": fear_name,
        "btc_dominance": btc_dominance,
        "trending": trending
    }


# =========================================================
# SIGNAL ENGINE
# =========================================================

def build_signal(
    symbol,
    interval
):

    tech = technical_analysis(
        symbol,
        interval
    )

    mtf = multi_timeframe(
        symbol
    )

    funding = get_funding(
        symbol
    )

    open_interest = (
        get_open_interest(
            symbol
        )
    )

    long_short = (
        get_long_short_ratio(
            symbol
        )
    )

    hype = calculate_hype(
        symbol
    )

    score = tech["score"]

    # 1H confirmation
    if "1h" in mtf:

        if (
            mtf["1h"]["trend"] ==
            "صاعد 🟢"
        ):

            score += 2

        elif (
            mtf["1h"]["trend"] ==
            "هابط 🔴"
        ):

            score -= 2

    # 4H confirmation
    if "4h" in mtf:

        if (
            mtf["4h"]["trend"] ==
            "صاعد 🟢"
        ):

            score += 2

        elif (
            mtf["4h"]["trend"] ==
            "هابط 🔴"
        ):

            score -= 2

    # Funding
    if funding > 0.0005:

        score -= 1

    elif funding < -0.0005:

        score += 1

    # Hype
    if hype["score"] >= 75:

        if score > 0:

            score += 1

    elif hype["score"] <= 25:

        if score < 0:

            score -= 1

    # القرار
    if score >= 5:

        direction = "LONG 🟢"

    elif score <= -5:

        direction = "SHORT 🔴"

    else:

        direction = "WAIT 🟡"

    price = tech["price"]

    atr_value = tech["atr"]

    # Entry / SL / TP
    if direction.startswith("LONG"):

        entry = price

        stop = (
            price -
            atr_value * 1.5
        )

        tp1 = (
            price +
            atr_value * 1.5
        )

        tp2 = (
            price +
            atr_value * 2.5
        )

        tp3 = (
            price +
            atr_value * 4
        )

    elif direction.startswith("SHORT"):

        entry = price

        stop = (
            price +
            atr_value * 1.5
        )

        tp1 = (
            price -
            atr_value * 1.5
        )

        tp2 = (
            price -
            atr_value * 2.5
        )

        tp3 = (
            price -
            atr_value * 4
        )

    else:

        entry = price
        stop = None
        tp1 = None
        tp2 = None
        tp3 = None

    # Risk
    if abs(score) >= 8:

        risk = "منخفض - متوسط"

    elif abs(score) >= 5:

        risk = "متوسط"

    else:

        risk = "مرتفع / انتظار"

    return {
        "symbol": symbol,
        "interval": interval,
        "tech": tech,
        "mtf": mtf,
        "funding": funding,
        "open_interest": open_interest,
        "long_short": long_short,
        "hype": hype,
        "score": score,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": risk
    }


# =========================================================
# تنسيق النتيجة
# =========================================================

def format_signal(data):

    tech = data["tech"]
    hype = data["hype"]

    text = (
        f"🚀 تحليل {data['symbol']} — Futures\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"

        f"🎯 الإشارة: {data['direction']}\n"
        f"📊 قوة الإشارة: {data['score']}\n"
        f"⚠️ المخاطرة: {data['risk']}\n\n"

        f"💰 السعر الحالي:\n"
        f"{tech['price']:.6f}\n\n"

        f"📈 الاتجاه:\n"
        f"5m: {data['mtf'].get('5m', {}).get('trend', '?')}\n"
        f"15m: {data['mtf'].get('15m', {}).get('trend', '?')}\n"
        f"1h: {data['mtf'].get('1h', {}).get('trend', '?')}\n"
        f"4h: {data['mtf'].get('4h', {}).get('trend', '?')}\n\n"

        f"📊 المؤشرات:\n"
        f"RSI: {tech['rsi']:.2f}\n"
        f"MACD: "
        f"{'صاعد 🟢' if tech['macd'] > tech['macd_signal'] else 'هابط 🔴'}\n"
        f"Volume: {tech['volume_ratio']:.2f}x\n\n"

        f"🕯️ نموذج الشموع:\n"
        f"{tech['pattern']}\n\n"

        f"🟢 الدعم:\n"
        f"{tech['support']:.6f}\n\n"

        f"🔴 المقاومة:\n"
        f"{tech['resistance']:.6f}\n\n"

        f"🔥 Crypto Hype:\n"
        f"{hype['score']}/100 — {hype['label']}\n"
        f"Fear & Greed: "
        f"{hype['fear_value']} "
        f"({hype['fear_name']})\n"
        f"BTC Dominance: "
        f"{hype['btc_dominance']:.2f}%\n\n"

        f"⚡ Futures:\n"
        f"Funding: "
        f"{data['funding'] * 100:.4f}%\n"
        f"Open Interest: "
        f"{data['open_interest']:.2f}\n"
        f"Long/Short: "
        f"{data['long_short']:.2f}\n\n"
    )

    if not data["direction"].startswith("WAIT"):

        text += (
            f"🎯 نقطة الدخول:\n"
            f"{data['entry']:.6f}\n\n"

            f"🛑 Stop Loss:\n"
            f"{data['stop']:.6f}\n\n"

            f"💰 TP1:\n"
            f"{data['tp1']:.6f}\n\n"

            f"💰 TP2:\n"
            f"{data['tp2']:.6f}\n\n"

            f"💰 TP3:\n"
            f"{data['tp3']:.6f}\n\n"
        )

    else:

        text += (
            "⏳ لا توجد صفقة واضحة حاليًا.\n"
            "الأفضل انتظار تأكيد أقوى.\n\n"
        )

    text += (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ التحليل مبني على بيانات السوق "
        "والمؤشرات، وليس ضمانًا للربح."
    )

    return text


# =========================================================
# /start
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not مسموح(update):
        return

    await update.message.reply_text(
        "🤖 PRO CRYPTO BOT ONLINE 🔥\n\n"
        "الأوامر المتاحة:\n\n"
        "/btc — تحليل Bitcoin\n"
        "/sol — تحليل Solana\n"
        "/market — حالة السوق\n"
        "/hype — Crypto Hype\n"
        "/analyze BTCUSDT 15m\n"
        "/analyze SOLUSDT 1h"
    )


# =========================================================
# /btc
# =========================================================

async def btc(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not مسموح(update):
        return

    msg = await update.message.reply_text(
        "⏳ جاري تحليل Bitcoin..."
    )

    try:

        result = build_signal(
            "BTCUSDT",
            "15m"
        )

        await msg.edit_text(
            format_signal(result)
        )

    except Exception as e:

        print(
            "BTC ERROR:",
            repr(e)
        )

        await msg.edit_text(
            "❌ صار خطأ في تحليل BTC.\n"
            "شوف Render Logs."
        )


# =========================================================
# /sol
# =========================================================

async def sol(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not مسموح(update):
        return

    msg = await update.message.reply_text(
        "⏳ جاري تحليل Solana..."
    )

    try:

        result = build_signal(
            "SOLUSDT",
            "15m"
        )

        await msg.edit_text(
            format_signal(result)
        )

    except Exception as e:

        print(
            "SOL ERROR:",
            repr(e)
        )

        await msg.edit_text(
            "❌ صار خطأ في تحليل SOL.\n"
            "شوف Render Logs."
        )


# =========================================================
# /analyze
# =========================================================

async def analyze(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not مسموح(update):
        return

    args = context.args

    if not args:

        await update.message.reply_text(
            "مثال:\n\n"
            "/analyze BTCUSDT 15m\n"
            "/analyze SOLUSDT 1h"
        )

        return

    symbol = args[0].upper()

    interval = (
        args[1]
        if len(args) > 1
        else "15m"
    )

    valid_intervals = [
        "5m",
        "15m",
        "1h",
        "4h"
    ]

    if interval not in valid_intervals:

        await update.message.reply_text(
            "الفريمات المتاحة:\n"
            "5m / 15m / 1h / 4h"
        )

        return

    msg = await update.message.reply_text(
        f"⏳ جاري تحليل {symbol} على {interval}..."
    )

    try:

        result = build_signal(
            symbol,
            interval
        )

        await msg.edit_text(
            format_signal(result)
        )

    except Exception as e:

        print(
            "ANALYZE ERROR:",
            repr(e)
        )

        await msg.edit_text(
            "❌ ما نجمتش نحلل العملة.\n"
            "تأكد من اسمها على Binance Futures."
        )


# =========================================================
# /hype
# =========================================================

async def hype(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not مسموح(update):
        return

    try:

        btc_hype = calculate_hype(
            "BTCUSDT"
        )

        sol_hype = calculate_hype(
            "SOLUSDT"
        )

        trending = ", ".join(
            btc_hype["trending"][:10]
        )

        text = (
            "🔥 CRYPTO HYPE DASHBOARD\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"🌍 Fear & Greed:\n"
            f"{btc_hype['fear_value']} "
            f"— {btc_hype['fear_name']}\n\n"

            f"₿ Bitcoin Hype:\n"
            f"{btc_hype['score']}/100 "
            f"— {btc_hype['label']}\n\n"

            f"◎ Solana Hype:\n"
            f"{sol_hype['score']}/100 "
            f"— {sol_hype['label']}\n\n"

            f"₿ BTC Dominance:\n"
            f"{btc_hype['btc_dominance']:.2f}%\n\n"

            f"🔥 Trending:\n"
            f"{trending or 'لا توجد بيانات'}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "الـHype عامل مساعد للتحليل "
            "وليس إشارة دخول وحده."
        )

        await update.message.reply_text(
            text
        )

    except Exception as e:

        print(
            "HYPE ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ تعذر جلب بيانات الـHype."
        )


# =========================================================
# /market
# =========================================================

async def market(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not مسموح(update):
        return

    msg = await update.message.reply_text(
        "⏳ جاري تحليل السوق..."
    )

    try:

        btc_result = build_signal(
            "BTCUSDT",
            "15m"
        )

        sol_result = build_signal(
            "SOLUSDT",
            "15m"
        )

        text = (
            "🌍 PRO CRYPTO MARKET\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"₿ BTC:\n"
            f"{btc_result['direction']}\n"
            f"Score: {btc_result['score']}\n"
            f"Hype: "
            f"{btc_result['hype']['score']}/100\n\n"

            f"◎ SOL:\n"
            f"{sol_result['direction']}\n"
            f"Score: {sol_result['score']}\n"
            f"Hype: "
            f"{sol_result['hype']['score']}/100\n\n"

            f"🌡 Fear & Greed:\n"
            f"{btc_result['hype']['fear_value']} "
            f"— {btc_result['hype']['fear_name']}\n\n"

            f"₿ BTC Dominance:\n"
            f"{btc_result['hype']['btc_dominance']:.2f}%\n\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "استعمل /btc أو /sol للتحليل الكامل."
        )

        await msg.edit_text(
            text
        )

    except Exception as e:

        print(
            "MARKET ERROR:",
            repr(e)
        )

        await msg.edit_text(
            "❌ تعذر جلب بيانات السوق."
        )


# =========================================================
# Error Handler
# =========================================================

async def error_handler(
    update,
    context
):

    print(
        "TELEGRAM ERROR:",
        repr(context.error)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    server_thread = threading.Thread(
        target=run_server,
        daemon=True
    )

    server_thread.start()

    print(
        "🚀 Starting PRO Crypto Bot..."
    )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "btc",
            btc
        )
    )

    application.add_handler(
        CommandHandler(
            "sol",
            sol
        )
    )

    application.add_handler(
        CommandHandler(
            "analyze",
            analyze
        )
    )

    application.add_handler(
        CommandHandler(
            "hype",
            hype
        )
    )

    application.add_handler(
        CommandHandler(
            "market",
            market
        )
    )

    application.add_error_handler(
        error_handler
    )

    print(
        "🔥 PRO BOT IS RUNNING..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
