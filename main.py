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
# SECURITY & DATA ENGINE (WITH FALLBACK)
# =========================================================

def allowed(update):
    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.id) == str(CHAT_ID)

def get_market_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if not hist.empty:
            current = hist.iloc[-1]
            price = float(current["Close"])
            open_price = float(current["Open"])
            high = float(current["High"])
            low = float(current["Low"])
            change = ((price - open_price) / open_price) * 100
            trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
            
            # تحليل الشموع
            body = abs(price - open_price)
            total_range = high - low
            upper_shadow = high - max(price, open_price)
            lower_shadow = min(price, open_price) - low
            
            candle = "شمعة مستقرة ⚖️"
            if total_range > 0:
                if lower_shadow > (body * 2):
                    candle = "مطرقة انعكاسية صاعدة 🔨🟢"
                elif upper_shadow > (body * 2):
                    candle = "شهاب ساقط انعكاسي هابط 🌠🔴"
                elif price > open_price and body > (total_range * 0.5):
                    candle = "شمعة خضراء قوية 🟢💪"
                elif price < open_price and body > (total_range * 0.5):
                    candle = "شمعة حمراء قوية 🔴⚠️"

            return {
                "symbol": symbol,
                "price": price,
                "high": high,
                "low": low,
                "change": change,
                "trend": trend,
                "candle": candle
            }
    except Exception as e:
        print(f"Yfinance failed for {symbol}: {e}")

    try:
        coin_id = "bitcoin" if "BTC" in symbol else ("solana" if "SOL" in symbol else "ethereum")
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        res = requests.get(url, timeout=10).json()
        price = float(res[coin_id]["usd"])
        change = float(res[coin_id]["usd_24h_change"])
        trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
        return {
            "symbol": symbol,
            "price": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "change": change,
            "trend": trend,
            "candle": "بيانات سريعة (CoinGecko) ⚡"
        }
    except Exception as err:
        print(f"Fallback failed too: {err}")
        return None

def calculate_signal(symbol):
    data = get_market_data(symbol)
    if not data:
        return "❌ عذراً، حدث ضغط في جلب البيانات حالياً. حاول بعد لحظات."
        
    price = data['price']
    trend = data['trend']
    candle = data['candle']
    
    # 🧠 خوارزمية تحديد القرار الأنسب (Smart Decision)
    if "صاعد" in trend and ("خضراء" in candle or "صاعدة" in candle or "مطرقة" in candle):
        decision = "🟢 **القرار الأنسب الآن: الدخول LONG (شراء)** 🚀\n*(السوق إيجابي والشموع تدعم الصعود)*"
    elif "هابط" in trend and ("حمراء" in candle or "هابط" in candle or "شهاب" in candle):
        decision = "🔴 **القرار الأنسب الآن: الدخول SHORT (بيع)** 📉\n*(السوق سلبي والشموع تدعم الهبوط)*"
    elif "صاعد" in trend:
        decision = "🟡 **القرار الأنسب الآن: الميل للـ LONG بحذر** ⚠️\n*(الاتجاه صاعد لكن الشموع مترددة)*"
    elif "هابط" in trend:
        decision = "🟡 **القرار الأنسب الآن: الميل للـ SHORT بحذر** ⚠️\n*(الاتجاه هابط لكن الشموع مترددة)*"
    else:
        decision = "⚖️ **القرار الأنسب الآن: الانتظار (Wait)** ⏳\n*(السوق متذبذب وغير واضح حالياً)*"

    # حسابات الفيوتشرز (Long & Short)
    long_sl = price * 0.985
    long_tp1 = price * 1.015
    long_tp2 = price * 1.03
    
    short_sl = price * 1.015
    short_tp1 = price * 0.985
    short_tp2 = price * 0.97

    return (
        f"🎯 **تحليل وشموع لعملة {data['symbol']}**\n"
        f"💰 السعر الحالي: `{price:,.2f}`\n"
        f"📊 التغير اليومي: {trend} ({data['change']:.2f}%)\n"
        f"🕯️ **الشموع اليابانية:** {candle}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{decision}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 **إعدادات الـ LONG:**\n"
        f"▪️ الدخول: `~{price:,.2f}`\n"
        f"🛑 الوقف (SL): `~{long_sl:,.2f}`\n"
        f"🎯 هدف 1: `~{long_tp1:,.2f}` | هدف 2: `~{long_tp2:,.2f}`\n\n"
        "🔴 **إعدادات الـ SHORT:**\n"
        f"▪️ الدخول: `~{price:,.2f}`\n"
        f"🛑 الوقف (SL): `~{short_sl:,.2f}`\n"
        f"🎯 هدف 1: `~{short_tp1:,.2f}` | هدف 2: `~{short_tp2:,.2f}`\n"
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
        "🚀 ULTRA PRO MAX V6 (Smart AI Decisions)\n\n"
        "مرحباً بك يا ياسين! اختر العملة للتحليل:",
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
        await query.edit_message_text("🚀 ULTRA PRO MAX V6\n\nاختار العملة للتحليل:", reply_markup=main_keyboard())
        return

    if data == "signal_btc":
        await query.edit_message_text("⏳ جاري تحليل السوق واستخراج القرار لـ BTC...")
        msg = calculate_signal("BTC-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_btc"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_sol":
        await query.edit_message_text("⏳ جاري تحليل السوق واستخراج القرار لـ SOL...")
        msg = calculate_signal("SOL-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_sol"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_eth":
        await query.edit_message_text("⏳ جاري تحليل السوق واستخراج القرار لـ ETH...")
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
