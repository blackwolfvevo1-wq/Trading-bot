import os
import asyncio
import threading
import requests
import pandas as pd
import ccxt

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================================================
# CONFIG & BINANCE API KEYS
# =========================================================

BOT_TOKEN = "8829847415:AAGoiHSjaSfZ_Bjm1kC7uGh0BQ7FCcDMhHU"
CHAT_ID = "6937661753"

FEAR_GREED_URL = "https://api.alternative.me/fng/"

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# =========================================================
# RENDER WEB SERVER & TRADINGVIEW WEBHOOK
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "ULTRA PRO MAX BINANCE FUTURES BOT ONLINE 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
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
# TECHNICAL ANALYSIS ENGINE
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

def get_market_data(symbol, timeframe="1d"):
    try:
        pair = f"{symbol.upper()}/USDT"
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=60)
        
        if ohlcv and len(ohlcv) > 26:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            price = df['close'].iloc[-1]
            open_price = df['open'].iloc[-1]
            high = df['high'].iloc[-1]
            low = df['low'].iloc[-1]
            change = ((price - open_price) / open_price) * 100
            trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
            
            rsi_val = calculate_rsi(df['close'])
            macd_val, signal_val = calculate_macd(df['close'])
            
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

            # خوارزمية القرار
            bullish_score = 0
            bearish_score = 0
            if change > 0: bullish_score += 1
            else: bearish_score += 1
            if rsi_val < 40: bullish_score += 1
            if rsi_val > 60: bearish_score += 1
            if macd_val > signal_val: bullish_score += 2
            else: bearish_score += 2

            if bullish_score > bearish_score + 1:
                decision = "🟢 **القرار الأنسب: الدخول LONG (شراء)** 🚀"
            elif bearish_score > bullish_score + 1:
                decision = "🔴 **القرار الأنسب: الدخول SHORT (بيع)** 📉"
            else:
                decision = "⚖️ **القرار الأنسب: الانتظار والحياد (Wait)** ⏳"

            return {
                "symbol": symbol.upper(),
                "price": price,
                "change": change,
                "trend": trend,
                "rsi": rsi_status,
                "macd": macd_status,
                "decision": decision,
                "timeframe": timeframe
            }
    except Exception as e:
        print(f"CCXT Error for {symbol}: {e}")
    return None

def calculate_signal(symbol, timeframe="1d"):
    data = get_market_data(symbol, timeframe)
    if not data:
        return "❌ عذراً، حدث خطأ في جلب البيانات من Binance Futures."
        
    price = data['price']
    
    long_sl = price * 0.985
    long_tp1 = price * 1.015
    long_tp2 = price * 1.03
    
    short_sl = price * 1.015
    short_tp1 = price * 0.985
    short_tp2 = price * 0.97

    return (
        f"🎯 **التحليل الشامل لعملة {data['symbol']}** (فريم: `{data['timeframe']}`)\n"
        f"📡 المصدر: Binance Futures اللحظي 🟢\n"
        f"💰 السعر الحالي: `{price:,.2f}`\n"
        f"📊 الاتجاه: {data['trend']} (`{data['change']:.2f}%`)\n"
        f"📉 مؤشر RSI: {data['rsi']}\n"
        f"📈 مؤشر MACD: {data['macd']}\n"
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
        [InlineKeyboardButton("₿ BTC [1d]", callback_data="sig_BTC_1d"), InlineKeyboardButton("◎ SOL [1d]", callback_data="sig_SOL_1d")],
        [InlineKeyboardButton("Ξ ETH [1d]", callback_data="sig_ETH_1d"), InlineKeyboardButton("⚡ سكالبينج (15m)", callback_data="sig_BTC_15m")],
        [InlineKeyboardButton("🔥 Market Sentiment", callback_data="hype"), InlineKeyboardButton("🚨 Webhook Info", callback_data="webhook_info")]
    ])

async def start(update, context):
    if not allowed(update): return
    await update.message.reply_text(
        "🚀 **AURA TRADING BOT (Binance Futures)**\n\nمرحباً بك يا ياسين! الأسعار الآن مربوطة مباشرة بـ Binance Futures بدقة تامة. اختر الطلب:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

async def buttons(update, context):
    query = update.callback_query
    if str(query.message.chat.id) != str(CHAT_ID):
        await query.answer()
        return
    await query.answer()
    data = query.data

    if data == "home":
        await query.edit_message_text("🚀 **القائمة الرئيسية:**", reply_markup=main_keyboard(), parse_mode="Markdown")
        return

    if data.startswith("sig_"):
        _, sym, tf = data.split("_")
        await query.edit_message_text(f"⏳ جاري تحليل {sym} على فريم {tf}...")
        msg = calculate_signal(sym, tf)
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data=data), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "hype":
        try:
            r = requests.get(FEAR_GREED_URL, params={"limit": 1}, timeout=20).json()
            item = r["data"][0]
            await query.edit_message_text(
                f"🔥 **Market Sentiment**\nFear & Greed: `{item['value']}/100` ({item['value_classification']})",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]])
            )
        except:
            await query.edit_message_text("❌ Error.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]]) )
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
