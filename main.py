import os
import asyncio
import threading
import requests
import pandas as pd
import yfinance as yf

from flask import Flask, request, jsonify
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

BOT_TOKEN = "8829847415:AAGoiHSjaSfZ_Bjm1kC7uGh0BQ7FCcDMhHU"
CHAT_ID = "6937661753"

COINGECKO_URL = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/"

# =========================================================
# RENDER WEB SERVER & TRADINGVIEW WEBHOOK
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "ULTRA PRO MAX BOT ONLINE 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    """يستقبل تنبيهات TradingView (Long / Short) ويبعثها لتيلجرام"""
    try:
        data = request.json
        if not data:
            return "No data", 400

        msg = "🚨 **تنبيه TradingView (Futures)** 🚨\n━━━━━━━━━━━━━━━━━━\n\n"
        for key, value in data.items():
            msg += f"▪️ **{key.upper()}**: {value}\n"
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("Webhook Error:", e)
        return str(e), 500

def run_web():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# SECURITY & DATA ENGINE
# =========================================================

def allowed(update):
    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.id) == str(CHAT_ID)

def get_yfinance_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d") # نجيبو آخر يومين لتحليل الشموع بدقة
        
        if hist.empty or len(hist) < 2:
            return None
            
        current = hist.iloc[-1]
        prev = hist.iloc[-2]
        
        price = float(current["Close"])
        open_price = float(current["Open"])
        high = float(current["High"])
        low = float(current["Low"])
        volume = float(current["Volume"])
        
        change = ((price - open_price) / open_price) * 100
        trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
        
        # تحليل الشموع اليابانية (Candlestick Pattern Analysis)
        body = abs(price - open_price)
        total_range = high - low
        upper_shadow = high - max(price, open_price)
        lower_shadow = min(price, open_price) - low
        
        candlestick_pattern = "شمعة عادية مستقرة ⚖️"
        
        if total_range > 0:
            if lower_shadow > (body * 2) and upper_shadow < body:
                candlestick_pattern = "مطرقة انعكاسية صاعدة (Hammer) 🔨🟢"
            elif upper_shadow > (body * 2) and lower_shadow < body:
                candlestick_pattern = "شهاب ساقط انعكاسي هابط (Shooting Star) 🌠🔴"
            elif price > open_price and body > (total_range * 0.6):
                candlestick_pattern = "شمعة خضراء قوية (Bullish Marubozu) 🟢💪"
            elif price < open_price and body > (total_range * 0.6):
                candlestick_pattern = "شمعة حمراء قوية (Bearish Marubozu) 🔴⚠️"
            elif body < (total_range * 0.15):
                candlestick_pattern = "شمعة دوجي ترددية (Doji) ⏳"

        return {
            "symbol": symbol,
            "price": price,
            "open": open_price,
            "high": high,
            "low": low,
            "volume": volume,
            "change": change,
            "trend": trend,
            "candle": candlestick_pattern
        }
    except Exception as e:
        print(f"YFINANCE ERROR {symbol}:", e)
        return None

def calculate_signal(symbol):
    data = get_yfinance_data(symbol)
    if not data:
        return "❌ خطأ في جلب البيانات وتحليل الشموع."
        
    price = data['price']
    
    # حسابات الفيوتشرز (Long & Short)
    long_sl = price * 0.985
    long_tp1 = price * 1.015
    long_tp2 = price * 1.03
    
    short_sl = price * 1.015
    short_tp1 = price * 0.985
    short_tp2 = price * 0.97

    return (
        f"🎯 **تحليل وشموع لعملة {data['symbol']}**\n"
        f"💰 السعر الحالي: `{price:.4f}`\n"
        f"🕯️ **الشموع اليابانية:** {data['candle']}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 **فرصة شراء (LONG SETUP):**\n"
        f"▪️ الدخول: `~{price:.4f}`\n"
        f"🛑 الوقف (SL): `~{long_sl:.4f}`\n"
        f"🎯 الهدف 1 (TP1): `~{long_tp1:.4f}` | الهدف 2: `~{long_tp2:.4f}`\n\n"
        "🔴 **فرصة بيع (SHORT SETUP):**\n"
        f"▪️ الدخول: `~{price:.4f}`\n"
        f"🛑 الوقف (SL): `~{short_sl:.4f}`\n"
        f"🎯 الهدف 1 (TP1): `~{short_tp1:.4f}` | الهدف 2: `~{short_tp2:.4f}`\n\n"
        f"📊 التغير اليومي: {data['trend']} ({data['change']:.2f}%)"
    )

# =========================================================
# MENU & BUTTONS
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₿ BTC Analysis", callback_data="signal_btc"),
            InlineKeyboardButton("◎ SOL Analysis", callback_data="signal_sol")
        ],
        [
            InlineKeyboardButton("Ξ ETH Analysis", callback_data="signal_eth"),
        ],
        [
            InlineKeyboardButton("🔥 Market Sentiment", callback_data="hype"),
            InlineKeyboardButton("🚨 Webhook Info", callback_data="webhook_info")
        ]
    ])

async def start(update, context):
    if not allowed(update):
        return
    await update.message.reply_text(
        "🚀 ULTRA PRO MAX V4 (Candlesticks & Signals)\n\n"
        "مرحباً بك يا ياسين! اختر العملة اللي تحب تحلل الشموع والصفقات متاعها:",
        reply_markup=main_keyboard()
    )

async def buttons(update, context):
    query = update.callback_query
    if str(query.message.chat.id) != str(CHAT_ID):
        await query.answer()
        return
    await query.answer()
    data = query.data

    if data == "home":
        await query.edit_message_text("🚀 ULTRA PRO MAX V4\n\nاختار العملة للتحليل:", reply_markup=main_keyboard())
        return

    if data == "signal_btc":
        await query.edit_message_text("⏳ جاري تحليل الشموع وحساب الصفقات لـ BTC...")
        msg = calculate_signal("BTC-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_btc"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_sol":
        await query.edit_message_text("⏳ جاري تحليل الشموع وحساب الصفقات لـ SOL...")
        msg = calculate_signal("SOL-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_sol"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_eth":
        await query.edit_message_text("⏳ جاري تحليل الشموع وحساب الصفقات لـ ETH...")
        msg = calculate_signal("ETH-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_eth"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "hype":
        try:
            r = requests.get(FEAR_GREED_URL, params={"limit": 1}, timeout=20).json()
            item = r["data"][0]
            await query.edit_message_text(
                f"🔥 Market Sentiment\nFear & Greed: {item['value']}/100 ({item['value_classification']})",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]])
            )
        except:
            await query.edit_message_text("❌ Error.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]]))
        return

    if data == "webhook_info":
        await query.edit_message_text(
            "🚨 Webhook URL:\n`https://your-app.onrender.com/webhook`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

def main():
    threading.Thread(target=run_web, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
