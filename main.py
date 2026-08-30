import os
import asyncio
import threading
import io
import requests
import pandas as pd
import ccxt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = "8829847415:AAGoiHSjaSfZ_Bjm1kC7uGh0BQ7FCcDMhHU"
CHAT_ID = "6937661753"
FEAR_GREED_URL = "https://api.alternative.me/fng/"

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

app = Flask(__name__)

@app.route("/")
def home():
    return "ULTRA PRO MAX TRADING BOT V12 ONLINE 🚀"

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
        return str(e), 500

def run_web():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# INDICATORS & ANALYSIS ENGINE
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

def get_binance_data(symbol, interval="1d", limit=60):
    try:
        pair = f"{symbol.upper()}/USDT"
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=interval, limit=limit)
        if ohlcv and len(ohlcv) > 26:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
    except Exception as e:
        print(f"CCXT Error: {e}")
    return None

def get_funding_rate(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol.upper()}USDT"
        res = requests.get(url, timeout=5).json()
        rate = float(res.get("lastFundingRate", 0)) * 100
        return f"{rate:.4f}%"
    except:
        return "غير متوفر"

def generate_chart_image(df, symbol, interval):
    plt.figure(figsize=(8, 4))
    plt.plot(df['close'], label='Price', color='#00ffcc', linewidth=1.5)
    plt.title(f"{symbol} - Timeframe: {interval}", color='white')
    plt.gca().set_facecolor('#1e1e1e')
    plt.gcf().patch.set_facecolor('#121212')
    plt.tick_params(colors='white')
    plt.grid(True, linestyle='--', alpha=0.3)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def analyze_market(symbol, interval="1d"):
    df = get_binance_data(symbol, interval)
    if df is None:
        return None

    price = df['close'].iloc[-1]
    open_price = df['open'].iloc[-1]
    change = ((price - open_price) / open_price) * 100
    trend = "🟢 صاعد" if change > 0 else "🔴 هابط"

    rsi_val = calculate_rsi(df['close'])
    macd_val, signal_val = calculate_macd(df['close'])
    funding = get_funding_rate(symbol)

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

    chart_buf = generate_chart_image(df, symbol, interval)

    msg = (
        f"🎯 **التحليل الفني الشامل لـ {symbol.upper()}** (فريم: `{interval}`)\n"
        f"💰 السعر: `{price:,.2f}` | التغيير: {trend} (`{change:.2f}%`)\n"
        f"📉 RSI: {rsi_status}\n"
        f"📈 MACD: {macd_status}\n"
        f"💸 نسبة التمويل (Funding Rate): `{funding}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{decision}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🛑 SL مقترح: `~{price * 0.985:,.2f}`\n"
        f"🎯 TP1 مقترح: `~{price * 1.015:,.2f}`"
    )
    return msg, chart_buf

# =========================================================
# TELEGRAM BOT HANDLERS
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿ BTC [1d]", callback_data="an_btc"), InlineKeyboardButton("◎ SOL [1d]", callback_data="an_sol")],
        [InlineKeyboardButton("Ξ ETH [1d]", callback_data="an_eth"), InlineKeyboardButton("⏱️ اختر الفريم (1h / 4h / غيره)", callback_data="tf_select_coin")],
        [InlineKeyboardButton("🔥 Market Sentiment", callback_data="hype"), InlineKeyboardButton("🔍 بحث عن عملة", callback_data="search_prompt")]
    ])

async def start(update, context):
    if not allowed(update): return
    await update.message.reply_text(
        "🚀 **AURA TRADING BOT V12 (PRO MAX)**\n\nاختر العملة أو الفريم المطلوب:",
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

    if data.startswith("an_"):
        sym = data.split("_")[1]
        await query.edit_message_text(f"⏳ جاري تحليل {sym.upper()} على فريم اليوم (1d)...")
        res = analyze_market(sym, "1d")
        if res:
            msg, chart = res
            await query.message.reply_photo(photo=chart, caption=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="home")]]))
        else:
            await query.edit_message_text("❌ حدث خطأ في جلب البيانات.", reply_markup=main_keyboard())
        return

    if data == "tf_select_coin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("₿ BTC (اختر الفريم)", callback_data="coin_tf_BTC"), InlineKeyboardButton("◎ SOL (اختر الفريم)", callback_data="coin_tf_SOL")],
            [InlineKeyboardButton("Ξ ETH (اختر الفريم)", callback_data="coin_tf_ETH")],
            [InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await query.edit_message_text("📊 **اختر العملة باش تختار بعدها الفريم المناسب:**", reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("coin_tf_"):
        sym = data.split("_")[2]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 دقائق [5m]", callback_data=f"tf_{sym}_5m"), InlineKeyboardButton("15 دقيقة [15m]", callback_data=f"tf_{sym}_15m")],
            [InlineKeyboardButton("ساعة [1h]", callback_data=f"tf_{sym}_1h"), InlineKeyboardButton("4 ساعات [4h]", callback_data=f"tf_{sym}_4h")],
            [InlineKeyboardButton("يومي [1d]", callback_data=f"tf_{sym}_1d")],
            [InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await query.edit_message_text(f"🕒 **اختر الفريم الزمني لـ {sym}:**", reply_markup=kb, parse_mode="Markdown")
        return

    if data.startswith("tf_"):
        _, sym, tf = data.split("_")
        await query.edit_message_text(f"⏳ جاري تحليل {sym} على فريم {tf} مع توليد الشارت...")
        res = analyze_market(sym, tf)
        if res:
            msg, chart = res
            await query.message.reply_photo(photo=chart, caption=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="home")]]))
        else:
            await query.edit_message_text("❌ حدث خطأ.", reply_markup=main_keyboard())
        return

    if data == "search_prompt":
        context.user_data['waiting_for_coin'] = True
        await query.edit_message_text("✍️ **اكتب رمز العملة الآن في الرسائل (مثلاً: ADA, XRP, DOGE):**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="home")]]))
        return

    if data == "hype":
        try:
            r = requests.get(FEAR_GREED_URL, params={"limit": 1}, timeout=10).json()
            item = r["data"][0]
            await query.edit_message_text(f"🔥 **مؤشر الخوف والطمع (Fear & Greed):**\n`{item['value']}/100` ({item['value_classification']})", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="home")]]))
        except:
            await query.edit_message_text("❌ خطأ.", reply_markup=main_keyboard())

async def handle_message(update, context):
    if not allowed(update): return
    if context.user_data.get('waiting_for_coin'):
        coin = update.message.text.strip().upper()
        context.user_data['waiting_for_coin'] = False
        await update.message.reply_text(f"⏳ جاري تحليل العملة {coin} على فريم اليوم...")
        res = analyze_market(coin, "1d")
        if res:
            msg, chart = res
            await update.message.reply_photo(photo=chart, caption=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="home")]]))
        else:
            await update.message.reply_text(f"❌ لم أتمكن من العثور على العملة {coin}.", reply_markup=main_keyboard())

def main():
    threading.Thread(target=run_web, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
