import os
import asyncio
import threading
import requests
import pandas as pd
import yfinance as yf
from binance.spot import Spot

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

# حط مفاتيح الـ Binance API متاعك هنا (للقراءة فقط - آمنة 100%)
BINANCE_API_KEY = "jHTRrHkYChfdxVJ0M7dIT7HEFRslsHpKHpekHzphWcUivEd7jjsAfktM3QqKJv"
BINANCE_SECRET_KEY = "ItjVu541aNZF6GTbWVDsp7m5Jx2gegb0Mr0VROZJJvWQs7aRp8E8hvl8rYeEZLU"

FEAR_GREED_URL = "https://api.alternative.me/fng/"

# =========================================================
# RENDER WEB SERVER & TRADINGVIEW WEBHOOK
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "ULTRA PRO MAX BINANCE + YFINANCE BOT ONLINE 🚀"

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
# TECHNICAL ANALYSIS ENGINE (BINANCE + YFINANCE + RSI + MACD)
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

def get_market_data(symbol_yahoo, symbol_binance):
    # محاولة أولى عبر Binance API الرسمي
    try:
        client = Spot(api_key=BINANCE_API_KEY, secret=BINANCE_SECRET_KEY)
        klines = client.klines(symbol_binance, "1d", limit=60)
        
        if klines and len(klines) > 26:
            df = pd.DataFrame(klines, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            
            price = df['close'].iloc[-1]
            open_price = df['open'].iloc[-1]
            high = df['high'].iloc[-1]
            low = df['low'].iloc[-1]
            change = ((price - open_price) / open_price) * 100
            trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
            
            rsi_val = calculate_rsi(df['close'])
            macd_val, signal_val = calculate_macd(df['close'])
            
            return process_indicators(symbol_yahoo, price, high, low, open_price, change, trend, rsi_val, macd_val, signal_val, "Binance API الرسمي 🟢")
    except Exception as e:
        print(f"Binance API error for {symbol_binance}: {e}")

    # محاولة ثانية عبر Yahoo Finance (Fallback)
    try:
        ticker = yf.Ticker(symbol_yahoo)
        hist = ticker.history(period="60d")
        if not hist.empty and len(hist) > 26:
            close_prices = hist["Close"]
            current = hist.iloc[-1]
            price = float(current["Close"])
            open_price = float(current["Open"])
            high = float(current["High"])
            low = float(current["Low"])
            change = ((price - open_price) / open_price) * 100
            trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
            
            rsi_val = calculate_rsi(close_prices)
            macd_val, signal_val = calculate_macd(close_prices)
            
            return process_indicators(symbol_yahoo, price, high, low, open_price, change, trend, rsi_val, macd_val, signal_val, "Yahoo Finance 📊")
    except Exception as e:
        print(f"Yfinance failed for {symbol_yahoo}: {e}")

    return None

def process_indicators(symbol, price, high, low, open_price, change, trend, rsi_val, macd_val, signal_val, source):
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

    # 🧠 خوارزمية القرار الذكي
    bullish_score = 0
    bearish_score = 0
    
    if change > 0: bullish_score += 1
    else: bearish_score += 1
    
    if "صاعدة" in candle or "خضراء" in candle or "مطرقة" in candle: bullish_score += 2
    if "هابط" in candle or "حمراء" in candle or "شهاب" in candle: bearish_score += 2
    
    if rsi_val < 40: bullish_score += 1
    if rsi_val > 60: bearish_score += 1
    
    if macd_val > signal_val: bullish_score += 2
    else: bearish_score += 2

    if bullish_score > bearish_score + 1:
        decision = "🟢 **القرار الأنسب: الدخول LONG (شراء)** 🚀\n*(المؤشرات والـ MACD تدعم الصعود)*"
    elif bearish_score > bullish_score + 1:
        decision = "🔴 **القرار الأنسب: الدخول SHORT (بيع)** 📉\n*(المؤشرات والـ MACD تدعم الهبوط)*"
    else:
        decision = "⚖️ **القرار الأنسب: الانتظار والحياد (Wait)** ⏳\n*(السوق في منطقة تردد بين المؤشرات)*"

    return {
        "symbol": symbol.replace("-USD", ""),
        "price": price,
        "change": change,
        "trend": trend,
        "rsi": rsi_status,
        "macd": macd_status,
        "candle": candle,
        "decision": decision,
        "source": source
    }

def calculate_signal(symbol_yahoo, symbol_binance):
    data = get_market_data(symbol_yahoo, symbol_binance)
    if not data:
        return "❌ عذراً، حدث ضغط في جلب البيانات من المنصات حالياً."
        
    price = data['price']
    
    long_sl = price * 0.985
    long_tp1 = price * 1.015
    long_tp2 = price * 1.03
    
    short_sl = price * 1.015
    short_tp1 = price * 0.985
    short_tp2 = price * 0.97

    return (
        f"🎯 **التحليل الشامل لعملة {data['symbol']}**\n"
        f"📡 المصدر: {data['source']}\n"
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
        "🚀 ULTRA PRO MAX V8 (Binance API + Yahoo + RSI + MACD)\n\n"
        "مرحباً بك يا ياسين! البوت يربط الآن بين Binance و Yahoo لضمان دقة الأسعار. اختر العملة:",
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
        await query.edit_message_text("🚀 ULTRA PRO MAX V8\n\nاختار العملة للتحليل الشامل:", reply_markup=main_keyboard())
        return

    if data == "signal_btc":
        await query.edit_message_text("⏳ جاري جلب البيانات من Binance لـ BTC...")
        msg = calculate_signal("BTC-USD", "BTCUSDT")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_btc"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_sol":
        await query.edit_message_text("⏳ جاري جلب البيانات من Binance لـ SOL...")
        msg = calculate_signal("SOL-USD", "SOLUSDT")
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="signal_sol"), InlineKeyboardButton("🔙 Menu", callback_data="home")]])
        )
        return

    if data == "signal_eth":
        await query.edit_message_text("⏳ جاري جلب البيانات من Binance لـ ETH...")
        msg = calculate_signal("ETH-USD", "ETHUSDT")
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
