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
    return "ULTRA PRO MAX RSI & MACD BOT ONLINE 🚀"

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
# TECHNICAL ANALYSIS ENGINE (RSI, MACD, CANDLES)
# =========================================================

def allowed(update):
    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.id) == str(CHAT_ID)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

def get_advanced_analysis(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="60d") # نحتاجو بيانات كافية لحساب RSI و MACD بدقة
        if not hist.empty and len(hist) > 26:
            close_prices = hist["Close"]
            current = hist.iloc[-1]
            
            price = float(current["Close"])
            open_price = float(current["Open"])
            high = float(current["High"])
            low = float(current["Low"])
            change = ((price - open_price) / open_price) * 100
            trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
            
            # حساب المؤشرات الفنية
            rsi_val = calculate_rsi(close_prices)
            macd_val, signal_val = calculate_macd(close_prices)
            
            # تحليل الـ RSI
            if rsi_val > 70:
                rsi_status = f"متشبع شراء ({rsi_val:.1f}) ⚠️🔥"
            elif rsi_val < 30:
                rsi_status = f"متشبع بيع ({rsi_val:.1f}) 💎🟢"
            else:
                rsi_status = f"متوازن ({rsi_val:.1f}) ⚖️"
                
            # تحليل الـ MACD
            if macd_val > signal_val:
                macd_status = "إيجابي / تقاطع صاعد 🟢"
            else:
                macd_status = "سلبي / تقاطع هابط 🔴"

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

            # 🧠 خوارزمية القرار الذكي (تدمج الاتجاه + الشموع + RSI + MACD)
            bullish_score = 0
            bearish_score = 0
            
            if change > 0: bullish_score += 1
            else: bearish_score += 1
            
            if "صاعدة" in candle or "خضراء" in candle or "مطرقة" in candle: bullish_score += 2
            if "هابط" in candle or "حمراء" in candle or "شهاب" in candle: bearish_score += 2
            
            if rsi_val < 40: bullish_score += 1  # فرصة شراء من تحت
            if rsi_val > 60: bearish_score += 1  # تشبع بيع فوق
            
            if macd_val > signal_val: bullish_score += 2
            else: bearish_score += 2

            if bullish_score > bearish_score + 1:
                decision = "🟢 **القرار الأنسب: الدخول LONG (شراء)** 🚀\n*(المؤشرات والـ MACD تدعم الصعود)*"
            elif bearish_score > bullish_score + 1:
                decision = "🔴 **القرار الأنسب: الدخول SHORT (بيع)** 📉\n*(المؤشرات والـ MACD تدعم الهبوط)*"
            else:
                decision = "⚖️ **القرار الأنسب: الانتظار والحياد (Wait)** ⏳\n*(السوق في منطقة تردد بين المؤشرات)*"

            return {
                "symbol": symbol,
                "price": price,
                "change": change,
                "trend": trend,
                "rsi": rsi_status,
                "macd": macd_status,
                "candle": candle,
                "decision": decision
            }
    except Exception as e:
        print(f"Advanced analysis error for {symbol}: {e}")

    # Fallback سريع لو صار ضغط
    return {
        "symbol": symbol,
        "price": 0,
        "change": 0,
        "trend": "غير متوفر",
        "rsi": "غير متوفر",
        "macd": "غير متوفر",
        "candle": "غير متوفر",
        "decision": "❌ حدث خطأ مؤقت في جلب المؤشرات."
    }

def calculate_signal(symbol):
    data = get_advanced_analysis(symbol)
    if data["price"] == 0:
        return "❌ عذراً، حدث ضغط في جلب بيانات التحليل الفني حالياً."
        
    price = data['price']
    
    # حسابات الفيوتشرز
    long_sl = price * 0.985
    long_tp1 = price * 1.015
    long_tp2 = price * 1.03
    
    short_sl = price * 1.015
    short_tp1 = price * 0.985
    short_tp2 = price * 0.97

    return (
        f"🎯 **التحليل الفني الشامل لعملة {data['symbol']}**\n"
        f"💰 السعر الحالي: `{price:,.2f}`\n"
        f"📊 الاتجاه: {data['trend']} ({data['change']:.2f}%)\n"
        f"📉 مؤشر RSI: {data['rsi']}\n"
        f"📈 مؤشر MACD: {data['macd']}\n"
        f"🕯️ الشموع: {data['candle']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{data['decision']}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 **إعدادات الـ LONG:**\n"
        f"▪️ الدخول: `~{price:,.2f}` | 🛑 SL: `~{long_sl:,.2f}`\n"
        f"🎯 TP1: `~{long_tp1:,.2f}` | TP2: `~{long_tp2:,.2f}`\n\n"
        "🔴 **إعدادات الـ SHORT:**\n"
        f"▪️ الدخول: `~{price:,.2f}` | 🛑 SL: `~{short_sl:,.2f}`\n"
        f"🎯 TP1: `~{short_tp1:,.2f}` | TP2: `~{short_tp2:,.2f}`\n"
    )

# =========================================================
# MENU & BUTTONS
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₿ BTC Pro Analysis", callback_data="signal_btc"),
            InlineKeyboardButton("◎ SOL Pro Analysis", callback_data="signal_sol")
        ],
        [
            InlineKeyboardButton("Ξ ETH Pro Analysis", callback_data="signal_eth"),
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
        "🚀 ULTRA PRO MAX V7 (RSI + MACD + Smart Decision)\n\n"
        "مرحباً بك يا ياسين! البوت يحلل الآن بـ RSI و MACD والشموع. اختر العملة:",
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
        await query.edit_message_text("🚀 ULTRA PRO MAX V7\n\nاختار العملة للتحليل الفني الشامل:", reply_markup=main_keyboard())
        return

    if data == "signal_btc":
        await query.edit_message_text("⏳ جاري حساب RSI, MACD والشموع لـ BTC...")
        msg = calculate_signal("BTC-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_btc"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_sol":
        await query.edit_message_text("⏳ جاري حساب RSI, MACD والشموع لـ SOL...")
        msg = calculate_signal("SOL-USD")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_sol"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_eth":
        await query.edit_message_text("⏳ جاري حساب RSI, MACD والشموع لـ ETH...")
        msg = calculate_signal("ETH-USD")
        await query.edit_message_text(
            msg,
            parse_box=None,
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
