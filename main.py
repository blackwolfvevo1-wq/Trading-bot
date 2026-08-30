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
    """هنا يستقبل البوت إشعارات TradingView ويبعثها لتيلجرام"""
    try:
        data = request.json
        if not data:
            return "No data", 400

        # صياغة الرسالة اللي باش توصلك في تيلجرام
        msg = "🚨 **تنبيه TradingView** 🚨\n━━━━━━━━━━━━━━━━━━\n\n"
        for key, value in data.items():
            msg += f"▪️ **{key.upper()}**: {value}\n"
        
        # نبعثوها لتيلجرام مباشرة بالـ API باش ما تتعارضش مع Asyncio
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
# SECURITY & HTTP
# =========================================================

def allowed(update):
    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.id) == str(CHAT_ID)

def get_json(url, params=None):
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# =========================================================
# YAHOO FINANCE ENGINE
# =========================================================

def get_yfinance_data(symbol):
    """جلب بيانات العملة أو السهم من ياهو فاينانس"""
    try:
        ticker = yf.Ticker(symbol)
        # نجبدو بيانات اليوم باش نشوفو التغير
        hist = ticker.history(period="1d")
        
        if hist.empty:
            return None
            
        price = float(hist["Close"].iloc[-1])
        open_price = float(hist["Open"].iloc[-1])
        high = float(hist["High"].iloc[-1])
        low = float(hist["Low"].iloc[-1])
        volume = float(hist["Volume"].iloc[-1])
        
        # حساب نسبة التغير
        change = ((price - open_price) / open_price) * 100
        
        trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
        
        return {
            "symbol": symbol,
            "price": price,
            "high": high,
            "low": low,
            "volume": volume,
            "change": change,
            "trend": trend
        }
    except Exception as e:
        print(f"YFINANCE ERROR {symbol}:", e)
        return None

def format_yahoo_data(data):
    if not data:
        return "❌ خطأ: البيانات غير متوفرة أو الرمز غالط."
        
    return (
        "📊 YAHOO FINANCE DATA\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ الأصول: {data['symbol']}\n"
        f"💰 السعر الحالي: {data['price']:.4f}\n"
        f"📈 الاتجاه اليومي: {data['trend']} ({data['change']:.2f}%)\n\n"
        f"🔼 أعلى سعر: {data['high']:.4f}\n"
        f"🔽 أقل سعر: {data['low']:.4f}\n"
        f"📊 حجم التداول: {data['volume']:,.0f}\n\n"
        "💡 المصدر: Yahoo Finance"
    )

# =========================================================
# HYPE & MARKET SENTIMENT
# =========================================================

def fear_greed():
    try:
        data = get_json(FEAR_GREED_URL, {"limit": 1})
        item = data["data"][0]
        return int(item["value"]), item["value_classification"]
    except:
        return 50, "Neutral"

def trending():
    try:
        data = get_json(f"{COINGECKO_URL}/search/trending")
        result = [item.get("item", {}).get("symbol").upper() for item in data.get("coins", [])[:10]]
        return result
    except:
        return []

def hype():
    fear, name = fear_greed()
    coins = trending()
    score = 50
    if fear >= 75: score += 15
    elif fear >= 60: score += 8
    elif fear <= 25: score -= 15
    elif fear <= 40: score -= 8
    if "BTC" in coins: score += 10
    if "SOL" in coins: score += 10
    
    score = max(0, min(100, score))
    
    if score >= 80: label = "🔥🔥 قوي جدًا"
    elif score >= 65: label = "🔥 قوي"
    elif score >= 45: label = "🟡 محايد"
    elif score >= 30: label = "🟠 ضعيف"
    else: label = "🔴 خوف"
    
    return {"score": score, "label": label, "fear": fear, "fear_name": name, "trending": coins}

# =========================================================
# MENU & BUTTONS
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₿ BTC Data", callback_data="check_btc"),
            InlineKeyboardButton("◎ SOL Data", callback_data="check_sol")
        ],
        [
            InlineKeyboardButton("🔥 Hype & Sentiment", callback_data="hype"),
        ],
        [
            InlineKeyboardButton("🚨 Webhook Info", callback_data="webhook_info")
        ]
    ])

async def start(update, context):
    if not allowed(update):
        return
    await update.message.reply_text(
        "🚀 ULTRA PRO MAX V2\n\n"
        "مرحباً بك! البوت مربوط الآن بـ Yahoo Finance و TradingView.\n"
        "اختار شنوّة تحب تشوف:",
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
        await query.edit_message_text("🚀 ULTRA PRO MAX V2\n\nاختار شنوّة تحب تشوف:", reply_markup=main_keyboard())
        return

    if data == "check_btc":
        await query.edit_message_text("⏳ جاري جلب البيانات من Yahoo Finance...")
        # ياهو فاينانس يستعمل BTC-USD للكريبتو
        yf_data = get_yfinance_data("BTC-USD")
        await query.edit_message_text(
            format_yahoo_data(yf_data),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="check_btc"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "check_sol":
        await query.edit_message_text("⏳ جاري جلب البيانات من Yahoo Finance...")
        yf_data = get_yfinance_data("SOL-USD")
        await query.edit_message_text(
            format_yahoo_data(yf_data),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="check_sol"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "hype":
        try:
            h = hype()
            await query.edit_message_text(
                "🔥 CRYPTO HYPE\n━━━━━━━━━━━━━━━━━━\n\n"
                f"🔥 Score: {h['score']}/100\n{h['label']}\n\n"
                f"🌡 Fear & Greed: {h['fear']}/100\n{h['fear_name']}\n\n"
                "📈 Trending on CoinGecko:\n" + (", ".join(h['trending']) or "No data"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="hype"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
            )
        except:
            await query.edit_message_text("❌ Hype API error.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]]))
        return

    if data == "webhook_info":
        info_text = (
            "🚨 **كيفاش تربط TradingView:**\n\n"
            "1. امشي لـ TradingView واعمل Alert.\n"
            "2. في خانة Webhook URL حط الرابط متاع الـ Render متاعك مع كلمة /webhook هكا:\n"
            "`https://your-render-app-name.onrender.com/webhook`\n\n"
            "3. في الـ Message حط الكود هذا بصيغة JSON:\n"
            "{\n"
            '  "symbol": "{{ticker}}",\n'
            '  "price": "{{close}}",\n'
            '  "signal": "شراء قوي 🟢",\n'
            '  "time": "{{timenow}}"\n'
            "}"
        )
        await query.edit_message_text(
            info_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

# =========================================================
# STARTUP
# =========================================================

async def error_handler(update, context):
    print("TELEGRAM ERROR:", repr(context.error))

def main():
    # تشغيل سيرفر الويب في الخلفية باش يقبل الـ Webhooks
    threading.Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    application.add_error_handler(error_handler)

    print("🚀 ULTRA PRO MAX V2 STARTED")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
