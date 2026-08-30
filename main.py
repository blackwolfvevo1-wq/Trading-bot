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

app = Flask(__name__)

@app.route("/")
def home():
    return "ULTRA PRO MAX YFINANCE TRADING BOT ONLINE 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            return "No data", 400
        msg = "🚨 **تنبيه TradingView** 🚨\n━━━━━━━━━━━━━━━━━━\n\n"
        for key, value in data.items():
            msg += f"▪️ **{key.upper()}**: {value}\n"
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return str(e), 500

def run_web():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# TECHNICAL ANALYSIS ENGINE (YFINANCE PURE)
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
        yf_symbol = f"{symbol.upper()}-USD"
        
        # تحديد الـ period المناسب لكل فريم باش Yahoo ما يرفضش الطلب
        period = "60d"
        if timeframe in ["1m", "5m", "15m"]:
            period = "5d"  # الفريمات القصيرة يعطيها Yahoo آخر 5 أيام فقط
        elif timeframe in ["1h", "90m"]:
            period = "30d"

        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period=period, interval=timeframe)
        
        if not hist.empty and len(hist) > 26:
            df = hist.reset_index()
            df.columns = [c.lower() for c in df.columns]
            
            price = df['close'].iloc[-1]
            open_price = df['open'].iloc[-1]
            change = ((price - open_price) / open_price) * 100
            trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
            
            rsi_val = calculate_rsi(df['close'])
            macd_val, signal_val = calculate_macd(df['close'])
            
            if rsi_val > 70:
                rsi_status = f"متشبع شراء ({rsi_val:.1f}) ⚠️🔥"
            elif rsi_val < 30:
                rsi_status = f"متشبع بيع ({rsi_val:.1f}) 💎🟢"
            else:
                rsi_status = f"متوازن ({rsi_val:.1f}) ⚖️"
                
            macd_status = "إيجابي / تقاطع صاعد 🟢" if macd_val > signal_val else "سلبي / تقاطع هابط 🔴"

            bullish, bearish = (1 if change > 0 else 0), (0 if change > 0 else 1)
            if macd_val > signal_val: bullish += 2
            else: bearish += 2

            if bullish > bearish:
                decision = "🟢 **القرار الأنسب: LONG (شراء)** 🚀"
            else:
                decision = "🔴 **القرار الأنسب: SHORT (بيع)** 📉"

            return {
                "symbol": symbol.upper(),
                "price": price,
                "change": change,
                "trend": trend,
                "rsi": rsi_status,
                "macd": macd_status,
                "decision": decision,
                "timeframe": timeframe,
                "source": "Yahoo Finance 📊"
            }
    except Exception as e:
        print(f"Yahoo Error for {symbol} ({timeframe}): {e}")

    return None

def calculate_signal(symbol, timeframe="1d"):
    data = get_market_data(symbol, timeframe)
    if not data:
        return f"❌ عذراً، لم أتمكن من جلب بيانات فريم `{timeframe}` لعملة {symbol} من Yahoo."
        
    price = data['price']
    long_sl = price * 0.985
    long_tp1 = price * 1.015
    long_tp2 = price * 1.03
    
    short_sl = price * 1.015
    short_tp1 = price * 0.985
    short_tp2 = price * 0.97

    return (
        f"🎯 **التحليل الشامل لعملة {data['symbol']}** (فريم: `{data['timeframe']}`)\n"
        f"📡 المصدر: {data['source']}\n"
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
# TELEGRAM HANDLERS
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿ BTC [1d]", callback_data="sig_BTC_1d"), InlineKeyboardButton("◎ SOL [1d]", callback_data="sig_SOL_1d")],
        [InlineKeyboardButton("Ξ ETH [1h]", callback_data="sig_ETH_1h"), InlineKeyboardButton("⚡ BTC [15m]", callback_data="sig_BTC_15m")],
        [InlineKeyboardButton("⏱️ اختر العملة والفريم", callback_data="select_custom"), InlineKeyboardButton("🔥 Sentiment", callback_data="hype")]
    ])

async def start(update, context):
    if not allowed(update): return
    await update.message.reply_text(
        "🚀 **AURA TRADING BOT (Yahoo Finance Pure)**\n\nيدعم جميع الفريمات (5m, 15m, 1h, 4h, 1d) بدقة وسهولة. اختر من القائمة:",
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

    if data == "select_custom":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("BTC [5m]", callback_data="sig_BTC_5m"), InlineKeyboardButton("BTC [15m]", callback_data="sig_BTC_15m")],
            [InlineKeyboardButton("BTC [1h]", callback_data="sig_BTC_1h"), InlineKeyboardButton("BTC [4h]", callback_data="sig_BTC_4h")],
            [InlineKeyboardButton("BTC [1d]", callback_data="sig_BTC_1d"), InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await query.edit_message_text("📊 **اختر الفريم المطلوب لـ BTC:**", reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("sig_"):
        _, sym, tf = data.split("_")
        await query.edit_message_text(f"⏳ جاري تحليل {sym} على فريم {tf} عبر Yahoo...")
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

def main():
    threading.Thread(target=run_web, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
