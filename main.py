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
    return "AURA TRADING BOT (Yahoo + Candlesticks) ONLINE 🚀"

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
# TECHNICAL & CANDLESTICK ANALYSIS ENGINE
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

def analyze_candlesticks(df):
    """دالة قراءة وتحليل الشموع اليابانية للعملة"""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    o, h, l, c = last['open'], last['high'], last['low'], last['close']
    po, pc = prev['open'], prev['close']
    
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    
    candle_notes = []
    bull_score = 0
    bear_score = 0
    
    # 1. لون الشمعة
    if c > o:
        candle_notes.append("▪️ الشمعة الحالية خضراء (زخم إيجابي للإغلاق).")
        bull_score += 1
    else:
        candle_notes.append("▪️ الشمعة الحالية حمراء (ضغط بيعي وإغلاق سلبي).")
        bear_score += 1

    # 2. فحص النماذج الشهيرة (Hammer / Shooting Star)
    if lower_shadow > (body * 2) and upper_shadow <= body:
        candle_notes.append("🕯️ ظهور شمعة مطرقة (Hammer) سفلية: دليل على رفض الأسعار ودعم احتمال الارتداد صعوداً.")
        bull_score += 2
    elif upper_shadow > (body * 2) and lower_shadow <= body:
        candle_notes.append("🕯️ ظهور شمعة شهاب (Shooting Star) علوية: إشارة ضعف ورفض للصعود.")
        bear_score += 2

    # 3. فحص الابتلاع (Engulfing)
    if c > o and pc < po and c >= po and o <= pc:
        candle_notes.append("🕯️ نموذج ابتلاع شرائي قوي (Bullish Engulfing): الشمعة الحالية ابتلعت السابقة بالكامل.")
        bull_score += 3
    elif c < o and pc > po and c <= po and o >= pc:
        candle_notes.append("🕯️ نموذج ابتلاع بيعي قوي (Bearish Engulfing): سيطرة مطلقة للدببة.")
        bear_score += 3

    return candle_notes, bull_score, bear_score

def process_dataframe(df, symbol, timeframe, source_name):
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

    # دمج نقاط الشموع اليابانية
    candle_notes, bull_c_score, bear_c_score = analyze_candlesticks(df)

    bullish_score = bull_c_score + (1 if change > 0 else 0) + (2 if macd_val > signal_val else 0)
    bearish_score = bear_c_score + (1 if change <= 0 else 0) + (2 if macd_val <= signal_val else 0)

    if rsi_val < 40:
        bullish_score += 1
    elif rsi_val > 60:
        bearish_score += 1

    if bullish_score > bearish_score + 1:
        decision = "🟢 **القرار الأنسب: الدخول LONG (شراء)** 🚀"
        trap = "⚠️ **ثغرة الحكاية (تنبيه):** احذر من كاذب الصعود (Fakeout)؛ تأكد من ثبات السعر فوق مستويات المقاومة."
    elif bearish_score > bullish_score + 1:
        decision = "🔴 **القرار الأنسب: الدخول SHORT (بيع)** 📉"
        trap = "⚠️ **ثغرة الحكاية (تنبيه):** احذر من ارتداد مفاجئ (Short Squeeze) في حال ظهرت سيولة شرائية قوية."
    else:
        decision = "⚖️ **القرار الأنسب: الانتظار والحياد (Wait)** ⏳"
        trap = "⚠️ **ثغرة الحكاية (تنبيه):** السوق في نطاق عرضي متذبذب، التداول في هذه المناطق مغامرة."

    reasons_list = list(candle_notes)
    if rsi_val < 40:
        reasons_list.append(f"▪️ مؤشر RSI منخفض ({rsi_val:.1f}) ويدعم الشراء.")
    elif rsi_val > 60:
        reasons_list.append(f"▪️ مؤشر RSI مرتفع ({rsi_val:.1f}) وقريب من التشبع.")
        
    if macd_val > signal_val:
        reasons_list.append("▪️ تقاطع الـ MACD إيجابي فوق خط الإشارة.")
    else:
        reasons_list.append("▪️ الـ MACD سلبي وتحت خط الإشارة.")

    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "trend": trend,
        "rsi": rsi_status,
        "macd": macd_status,
        "decision": decision,
        "reasons": "\n".join(reasons_list),
        "trap": trap,
        "timeframe": timeframe,
        "source": source_name
    }

def get_market_data(symbol, timeframe="1d"):
    try:
        yf_symbol = f"{symbol.upper()}-USD"
        period = "60d" if timeframe in ["1d", "4h"] else "5d"
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period=period, interval=timeframe)
        if not hist.empty and len(hist) > 26:
            df = hist.reset_index()
            df.columns = [c.lower() for c in df.columns]
            return process_dataframe(df, symbol, timeframe, "Yahoo Finance 📊")
    except Exception as e:
        print(f"Yahoo Error: {e}")
    return None

def calculate_signal(symbol, timeframe="1d"):
    data = get_market_data(symbol, timeframe)
    if not data:
        return f"❌ عذراً، لم أتمكن من جلب بيانات فريم `{timeframe}` لعملة {symbol}."
        
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
        f"{data['decision']}\n\n"
        "🕯️ **قراءة الشموع اليابانية والأسباب الفنية:**\n"
        f"{data['reasons']}\n\n"
        f"{data['trap']}\n"
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
        [InlineKeyboardButton("Ξ ETH [1d]", callback_data="sig_ETH_1d"), InlineKeyboardButton("⚡ سكالبينج [15m]", callback_data="sig_BTC_15m")],
        [InlineKeyboardButton("⏱️ اختر العملة والفريم", callback_data="select_coin"), InlineKeyboardButton("🔥 Sentiment", callback_data="hype")]
    ])

async def start(update, context):
    if not allowed(update): return
    await update.message.reply_text(
        "🚀 **AURA TRADING BOT (Yahoo + Candlesticks)**\n\nاختر من القائمة الرئيسية:",
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

    if data == "select_coin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("₿ Bitcoin (BTC)", callback_data="tf_BTC"), InlineKeyboardButton("◎ Solana (SOL)", callback_data="tf_SOL")],
            [InlineKeyboardButton("Ξ Ethereum (ETH)", callback_data="tf_ETH"), InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await query.edit_message_text("🪙 **اختر العملة اللي تحب تحللها:**", reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("tf_"):
        sym = data.split("_")[1]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 دقائق [5m]", callback_data=f"sig_{sym}_5m"), InlineKeyboardButton("15 دقيقة [15m]", callback_data=f"sig_{sym}_15m")],
            [InlineKeyboardButton("ساعة [1h]", callback_data=f"sig_{sym}_1h"), InlineKeyboardButton("4 ساعات [4h]", callback_data=f"sig_{sym}_4h")],
            [InlineKeyboardButton("يومي [1d]", callback_data=f"sig_{sym}_1d")],
            [InlineKeyboardButton("🔙 رجوع للعملات", callback_data="select_coin")]
        ])
        await query.edit_message_text(f"📊 **اختر الفريم الزمني لـ {sym}:**", reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("sig_"):
        _, sym, tf = data.split("_")
        await query.edit_message_text(f"⏳ جاري تحليل {sym} على فريم {tf} مع قراءة الشموع اليابانية...")
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
