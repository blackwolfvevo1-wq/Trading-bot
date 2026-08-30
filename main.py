import os
import asyncio
import logging
import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from cachetools import TTLCache
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================================================
# 1. إعدادات الحماية والتسجيل (CONFIG & LOGGING)
# =========================================================

# تحميل المتغيرات السرية من ملف .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", "8080"))

FEAR_GREED_URL = "https://api.alternative.me/fng/"

# إعداد نظام المراقبة (Logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعداد نظام التخزين المؤقت (Caching) لتفادي حظر Yahoo (يخزن الداتا لـ 120 ثانية)
cache = TTLCache(maxsize=100, ttl=120)

# =========================================================
# 2. نظام التنبيهات (TRADINGVIEW WEBHOOK via AIOHTTP)
# =========================================================

async def handle_webhook(request):
    """استقبال تنبيهات TradingView وإرسالها لتيليغرام"""
    try:
        data = await request.json()
        if not data:
            return web.Response(text="No data", status=400)
        
        msg = "🚨 **تنبيه TradingView** 🚨\n━━━━━━━━━━━━━━━━━━\n\n"
        for key, value in data.items():
            msg += f"▪️ **{key.upper()}**: {value}\n"
        
        # استدعاء البوت لإرسال الرسالة
        bot = request.app['bot']
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
        
        return web.json_response({"status": "success"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text=str(e), status=500)

async def start_web_server(application: Application):
    """تشغيل سيرفر الويب في الخلفية مع البوت"""
    server = web.Application()
    server['bot'] = application.bot
    server.router.add_post('/webhook', handle_webhook)
    server.router.add_get('/', lambda r: web.Response(text="AURA TRADING BOT ONLINE 🚀"))
    
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")

# =========================================================
# 3. محرك التحليل والشموع اليابانية (ANALYSIS ENGINE)
# =========================================================

def allowed(update: Update) -> bool:
    chat = update.effective_chat
    return chat and str(chat.id) == str(CHAT_ID)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).iloc[-1]

def calculate_macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

def analyze_candlesticks(df):
    last, prev = df.iloc[-1], df.iloc[-2]
    o, h, l, c = last['open'], last['high'], last['low'], last['close']
    po, pc = prev['open'], prev['close']
    
    body = abs(c - o)
    upper_shadow, lower_shadow = h - max(o, c), min(o, c) - l
    
    notes, bull, bear = [], 0, 0
    
    if c > o:
        notes.append("▪️ الشمعة الحالية خضراء (زخم إيجابي).")
        bull += 1
    else:
        notes.append("▪️ الشمعة الحالية حمراء (ضغط بيعي).")
        bear += 1

    if lower_shadow > (body * 2) and upper_shadow <= body:
        notes.append("🕯️ شمعة مطرقة (Hammer): دليل على رفض الأسعار ودعم للارتداد.")
        bull += 2
    elif upper_shadow > (body * 2) and lower_shadow <= body:
        notes.append("🕯️ شمعة شهاب (Shooting Star): إشارة ضعف ورفض للصعود.")
        bear += 2

    if c > o and pc < po and c >= po and o <= pc:
        notes.append("🕯️ ابتلاع شرائي (Bullish Engulfing): سيطرة للمشترين.")
        bull += 3
    elif c < o and pc > po and c <= po and o >= pc:
        notes.append("🕯️ ابتلاع بيعي (Bearish Engulfing): سيطرة مطلقة للدببة.")
        bear += 3

    return notes, bull, bear

def process_dataframe(df, symbol, timeframe):
    price, open_price = df['close'].iloc[-1], df['open'].iloc[-1]
    change = ((price - open_price) / open_price) * 100
    trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
    
    rsi_val = calculate_rsi(df['close'])
    macd_val, signal_val = calculate_macd(df['close'])
    
    rsi_status = f"متشبع شراء ({rsi_val:.1f}) ⚠️" if rsi_val > 70 else f"متشبع بيع ({rsi_val:.1f}) 💎" if rsi_val < 30 else f"متوازن ({rsi_val:.1f}) ⚖️"
    macd_status = "إيجابي 🟢" if macd_val > signal_val else "سلبي 🔴"

    notes, bull_score, bear_score = analyze_candlesticks(df)
    
    bullish_score = bull_score + (1 if change > 0 else 0) + (2 if macd_val > signal_val else 0) + (1 if rsi_val < 40 else 0)
    bearish_score = bear_score + (1 if change <= 0 else 0) + (2 if macd_val <= signal_val else 0) + (1 if rsi_val > 60 else 0)

    if bullish_score > bearish_score + 1:
        decision, trap = "🟢 **دخول LONG (شراء)** 🚀", "⚠️ احذر من كاذب الصعود؛ تأكد من ثبات السعر فوق المقاومة."
    elif bearish_score > bullish_score + 1:
        decision, trap = "🔴 **دخول SHORT (بيع)** 📉", "⚠️ احذر من ارتداد مفاجئ (Short Squeeze)."
    else:
        decision, trap = "⚖️ **الانتظار والحياد (Wait)** ⏳", "⚠️ السوق في نطاق عرضي متذبذب."

    reasons = list(notes)
    reasons.append(f"▪️ RSI يدعم الشراء." if rsi_val < 40 else f"▪️ RSI قريب من التشبع." if rsi_val > 60 else "")
    reasons.append("▪️ MACD إيجابي." if macd_val > signal_val else "▪️ MACD سلبي.")

    return {
        "symbol": symbol.upper(), "price": price, "change": change, "trend": trend,
        "rsi": rsi_status, "macd": macd_status, "decision": decision,
        "reasons": "\n".join([r for r in reasons if r]), "trap": trap,
        "timeframe": timeframe, "source": "Yahoo Finance 📊"
    }

def fetch_yf_sync(symbol, timeframe):
    """الدالة المتزامنة لجلب البيانات (تشتغل في Thread منفصل)"""
    yf_symbol = f"{symbol.upper()}-USD"
    period = "60d" if timeframe in ["1d", "4h"] else "5d"
    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period=period, interval=timeframe)
    if not hist.empty and len(hist) > 26:
        df = hist.reset_index()
        df.columns = [c.lower() for c in df.columns]
        return process_dataframe(df, symbol, timeframe)
    return None

async def get_market_data(symbol, timeframe="1d"):
    """دالة Async ذكية تستعمل الكاش والـ Threads"""
    cache_key = f"{symbol}_{timeframe}"
    if cache_key in cache:
        return cache[cache_key] # إرجاع الداتا من الكاش بسرعة الضوء
    
    try:
        # تشغيل الدالة في الخلفية باش البوت ما يتبلوكاش
        data = await asyncio.to_thread(fetch_yf_sync, symbol, timeframe)
        if data:
            cache[cache_key] = data # تخزين الداتا الجديدة
        return data
    except Exception as e:
        logger.error(f"Yahoo Error: {e}")
        return None

async def calculate_signal(symbol, timeframe="1d"):
    data = await get_market_data(symbol, timeframe)
    if not data:
        return f"❌ عذراً، لم أتمكن من جلب بيانات فريم `{timeframe}` لعملة {symbol}."
        
    p = data['price']
    return (
        f"🎯 **تحليل {data['symbol']}** (فريم: `{data['timeframe']}`)\n"
        f"📡 المصدر: {data['source']}\n"
        f"💰 السعر الحالي: `{p:,.2f}`\n"
        f"📊 الاتجاه: {data['trend']} (`{data['change']:.2f}%`)\n"
        f"📉 RSI: {data['rsi']} | 📈 MACD: {data['macd']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{data['decision']}\n\n"
        "🕯️ **الأسباب الفنية:**\n"
        f"{data['reasons']}\n\n"
        f"{data['trap']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🟢 **LONG:** الدخول: `~{p:,.2f}` | 🛑 SL: `~{p*0.985:,.2f}` | 🎯 TP: `~{p*1.02:,.2f}`\n"
        f"🔴 **SHORT:** الدخول: `~{p:,.2f}` | 🛑 SL: `~{p*1.015:,.2f}` | 🎯 TP: `~{p*0.98:,.2f}`"
    )

# =========================================================
# 4. واجهة المستخدم (TELEGRAM HANDLERS)
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿ BTC [1d]", callback_data="sig_BTC_1d"), InlineKeyboardButton("◎ SOL [1d]", callback_data="sig_SOL_1d")],
        [InlineKeyboardButton("Ξ ETH [1d]", callback_data="sig_ETH_1d"), InlineKeyboardButton("⚡ سكالبينج [15m]", callback_data="sig_BTC_15m")],
        [InlineKeyboardButton("⏱️ اختر العملة والفريم", callback_data="select_coin"), InlineKeyboardButton("🔥 Sentiment", callback_data="hype")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text(
        "🚀 **AURA TRADING BOT (PRO)**\n\nاختر من القائمة الرئيسية:",
        reply_markup=main_keyboard(), parse_mode="Markdown"
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.message.chat.id) != str(CHAT_ID):
        return await query.answer("Access Denied.", show_alert=True)
    await query.answer()
    data = query.data

    if data == "home":
        await query.edit_message_text("🚀 **القائمة الرئيسية:**", reply_markup=main_keyboard(), parse_mode="Markdown")
    
    elif data == "select_coin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("₿ BTC", callback_data="tf_BTC"), InlineKeyboardButton("◎ SOL", callback_data="tf_SOL")],
            [InlineKeyboardButton("Ξ ETH", callback_data="tf_ETH"), InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await query.edit_message_text("🪙 **اختر العملة:**", reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("tf_"):
        sym = data.split("_")[1]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("15m", callback_data=f"sig_{sym}_15m"), InlineKeyboardButton("1h", callback_data=f"sig_{sym}_1h")],
            [InlineKeyboardButton("4h", callback_data=f"sig_{sym}_4h"), InlineKeyboardButton("1d", callback_data=f"sig_{sym}_1d")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="select_coin")]
        ])
        await query.edit_message_text(f"📊 **اختر الفريم لـ {sym}:**", reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("sig_"):
        _, sym, tf = data.split("_")
        await query.edit_message_text(f"⏳ جاري تحليل {sym} على فريم {tf} بدقة عالية...")
        msg = await calculate_signal(sym, tf) # <- هنا استعملنا await
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث (Refresh)", callback_data=data), InlineKeyboardButton("🔙 رجوع", callback_data="home")]
        ]))

    elif data == "hype":
        try:
            r = await asyncio.to_thread(requests.get, FEAR_GREED_URL, params={"limit": 1}, timeout=10)
            item = r.json()["data"][0]
            await query.edit_message_text(
                f"🔥 **Market Sentiment**\nFear & Greed: `{item['value']}/100` ({item['value_classification']})",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]])
            )
        except Exception as e:
            logger.error(f"Sentiment Error: {e}")
            await query.edit_message_text("❌ خطأ في جلب البيانات.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]]))

async def post_init(application: Application):
    """يتم تشغيله تلقائياً عند تشغيل البوت لإطلاق الـ Web Server"""
    asyncio.create_task(start_web_server(application))

def main():
    # بناء البوت وإضافة post_init لتشغيل الويب سيرفر
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    
    logger.info("Bot is running...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
