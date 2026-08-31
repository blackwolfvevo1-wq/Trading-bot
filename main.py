import os
import io
import asyncio
import logging
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import mplfinance as mpf
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
# 1. إعدادات البوت 
# =========================================================

BOT_TOKEN = "8829847415:AAGoiHSjaSfZ_Bjm1kC7uGh0BQ7FCcDMhHU"
CHAT_ID = "6937661753"

PORT = int(os.getenv("PORT", "8080"))
FEAR_GREED_URL = "https://api.alternative.me/fng/"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
cache = TTLCache(maxsize=100, ttl=120)

# =========================================================
# 2. نظام التنبيهات (TRADINGVIEW WEBHOOK)
# =========================================================

async def handle_webhook(request):
    try:
        data = await request.json()
        if not data:
            return web.Response(text="No data", status=400)
        
        msg = "🚨 **تنبيه TradingView** 🚨\n━━━━━━━━━━━━━━━━━━\n\n"
        for key, value in data.items():
            msg += f"▪️ **{key.upper()}**: {value}\n"
        
        bot = request.app['bot']
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
        return web.json_response({"status": "success"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text=str(e), status=500)

async def start_web_server(application: Application):
    server = web.Application()
    server['bot'] = application.bot
    server.router.add_post('/webhook', handle_webhook)
    server.router.add_get('/', lambda r: web.Response(text="AURA TRADING BOT ONLINE 🚀"))
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

# =========================================================
# 3. محركات البيانات (News & DexScreener)
# =========================================================

def fetch_news_sync(symbol):
    try:
        yf_symbol = f"{symbol.upper()}-USD"
        ticker = yf.Ticker(yf_symbol)
        news_list = ticker.news
        if not news_list:
            return f"ℹ️ لا توجد أخبار حديثة لعملة {symbol.upper()}."
            
        msg = f"📰 **آخر أخبار عملة {symbol.upper()}** 📡\n━━━━━━━━━━━━━━━━━━\n\n"
        for item in news_list[:4]:
            title = item.get("title", "بدون عنوان")
            publisher = item.get("publisher", "Yahoo Finance")
            link = item.get("link", "")
            if "content" in item:
                title = item["content"].get("title", title)
                publisher = item["content"].get("provider", {}).get("displayName", publisher)
                link = item["content"].get("canonicalUrl", {}).get("url", link)
            msg += f"🔹 **{title}**\n🏢 المصدر: `{publisher}`\n"
            if link: msg += f"🔗 [المقال كامل]({link})\n"
            msg += "──────────────────\n"
        msg += "\n**إن شاء الله 🤲**"
        return msg
    except Exception as e:
        return f"❌ تعذر جلب الأخبار لعملة {symbol.upper()}."

def fetch_dex_sync(symbol):
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    try:
        resp = requests.get(url, timeout=10).json()
        if "pairs" in resp and len(resp["pairs"]) > 0:
            pair = resp["pairs"][0]
            price = float(pair.get("priceUsd", 0))
            change = float(pair.get("priceChange", {}).get("h24", 0))
            liquidity = pair.get("liquidity", {}).get("usd", 0)
            vol = pair.get("volume", {}).get("h24", 0)
            dex = pair.get("dexId", "Unknown").upper()
            network = pair.get("chainId", "Unknown").upper()
            
            msg = (
                f"💎 **تحليل منصات اللامركزية (DEX)**\n"
                f"🪙 العملة: **{symbol.upper()}**\n"
                f"🔗 الشبكة: `{network}` | المنصة: `{dex}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"💰 السعر الحالي: `${price:,.6f}`\n"
                f"📊 التغير (24س): `{change}%` {'🟢' if change > 0 else '🔴'}\n"
                f"💧 السيولة: `${liquidity:,.0f}`\n"
                f"📈 حجم التداول (24س): `${vol:,.0f}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ *ملاحظة: لا يتوفر شارت عبر Yahoo حالياً.*\n\n**إن شاء الله 🤲**"
            )
            return msg
        else:
            return f"❌ لم أتمكن من العثور على {symbol} في DexScreener."
    except Exception as e:
        return f"❌ خطأ في الاتصال: {e}"

# =========================================================
# 4. محرك التحليل والتوقعات والشارت (Yahoo Finance)
# =========================================================

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

# -----------------------------------------------------
# الدالة الجديدة الخاصة بـ "فازة التوقعات" فقط (مستقلة)
# -----------------------------------------------------
def generate_forecast_sync(symbol):
    tfs = ["15m", "1h", "4h", "1d"]
    results = {}
    for tf in tfs:
        yf_symbol = f"{symbol.upper()}-USD"
        period = "60d" if tf in ["1d", "4h"] else "5d"
        try:
            df = yf.Ticker(yf_symbol).history(period=period, interval=tf)
            if df.empty or len(df) < 26:
                results[tf] = "بيانات غير كافية"
                continue
            
            last_h, last_l = df['High'].iloc[-2], df['Low'].iloc[-2]
            pivot = (last_h + last_l + df['Close'].iloc[-2]) / 3
            r1 = (2 * pivot) - last_l
            s1 = (2 * pivot) - last_h
            
            macd, sig = calculate_macd(df['Close'])
            rsi = calculate_rsi(df['Close'])
            
            if macd > sig and rsi < 70:
                results[tf] = f"🟢 **صعود متوقع** نحو المقاومة `{r1:,.2f}`"
            elif macd < sig and rsi > 30:
                results[tf] = f"🔴 **هبوط متوقع** نحو الدعم `{s1:,.2f}`"
            else:
                results[tf] = f"⚖️ **تذبذب وحيرة** بين الدعم `{s1:,.2f}` والمقاومة `{r1:,.2f}`"
        except:
            results[tf] = "خطأ في المعالجة"
            
    msg = (
        f"🔮 **التوقعات المستقبلية لعملة {symbol.upper()}** 🔮\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"⏱️ **توقع 15 دقيقة (سكالبينج):**\n{results.get('15m')}\n\n"
        f"⏱️ **توقع 1 ساعة (مدى قصير):**\n{results.get('1h')}\n\n"
        f"⏱️ **توقع 4 ساعات (مدى متوسط):**\n{results.get('4h')}\n\n"
        f"⏱️ **توقع اليوم (مدى يومي):**\n{results.get('1d')}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "**إن شاء الله 🤲**"
    )
    return msg

def generate_chart_with_analysis(df_hist, symbol, timeframe, r1, s1):
    df_plot = df_hist.tail(40).copy()
    buy_markers, sell_markers = [], []
    for i in range(len(df_plot)):
        row = df_plot.iloc[i]
        prev_row = df_plot.iloc[i-1] if i > 0 else row
        o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']
        po, pc = prev_row['Open'], prev_row['Close']
        body = abs(c - o)
        upper_shadow, lower_shadow = h - max(o, c), min(o, c) - l
        
        bullish = (lower_shadow > (body * 2) and upper_shadow <= body and c >= o) or (c > o and pc < po and c >= po and o <= pc)
        bearish = (upper_shadow > (body * 2) and lower_shadow <= body and c <= o) or (c < o and pc > po and c <= po and o >= pc)
            
        buy_markers.append(l * 0.995 if bullish else np.nan)
        sell_markers.append(h * 1.005 if bearish else np.nan)

    apds = [
        mpf.make_addplot([r1]*len(df_plot), color='red', linestyle='--', width=1.5, alpha=0.5),
        mpf.make_addplot([s1]*len(df_plot), color='green', linestyle='--', width=1.5, alpha=0.5)
    ]
    if any(not np.isnan(x) for x in buy_markers): apds.append(mpf.make_addplot(buy_markers, type='scatter', markersize=150, marker='^', color='green'))
    if any(not np.isnan(x) for x in sell_markers): apds.append(mpf.make_addplot(sell_markers, type='scatter', markersize=150, marker='v', color='red'))

    buf = io.BytesIO()
    mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=True)
    mpf.plot(df_plot, type='candle', style=s, addplot=apds, title=f"\n{symbol} ({timeframe})", figsize=(9, 5), savefig=buf)
    buf.seek(0)
    return buf.getvalue()

def analyze_candlesticks(df):
    last, prev = df.iloc[-1], df.iloc[-2]
    o, h, l, c = last['open'], last['high'], last['low'], last['close']
    po, pc = prev['open'], prev['close']
    body = abs(c - o)
    upper_shadow, lower_shadow = h - max(o, c), min(o, c) - l
    notes, bull, bear = [], 0, 0
    
    if c > o:
        notes.append("▪️ الشمعة الحالية خضراء.")
        bull += 1
    else:
        notes.append("▪️ الشمعة الحالية حمراء.")
        bear += 1

    if lower_shadow > (body * 2) and upper_shadow <= body:
        notes.append("🕯️ شمعة مطرقة (Hammer).")
        bull += 2
    elif upper_shadow > (body * 2) and lower_shadow <= body:
        notes.append("🕯️ شمعة شهاب (Shooting Star).")
        bear += 2

    return notes, bull, bear

def fetch_yf_sync(symbol, timeframe):
    yf_symbol = f"{symbol.upper()}-USD"
    period = "60d" if timeframe in ["1d", "4h"] else "5d"
    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period=period, interval=timeframe)
    
    if not hist.empty and len(hist) > 26:
        df = hist.copy()
        df.columns = [c.lower() for c in df.columns]
        
        price, open_price = df['close'].iloc[-1], df['open'].iloc[-1]
        change = ((price - open_price) / open_price) * 100
        trend = "🟢 صاعد" if change > 0 else "🔴 هابط"
        
        last_h, last_l, last_c = df['high'].iloc[-2], df['low'].iloc[-2], df['close'].iloc[-2]
        pivot = (last_h + last_l + last_c) / 3
        r1, s1 = (2 * pivot) - last_l, (2 * pivot) - last_h
        r2, s2 = pivot + (last_h - last_l), pivot - (last_h - last_l)
        
        rsi_val = calculate_rsi(df['close'])
        macd_val, signal_val = calculate_macd(df['close'])
        
        rsi_status = f"متشبع شراء ({rsi_val:.1f}) ⚠️" if rsi_val > 70 else f"متشبع بيع ({rsi_val:.1f}) 💎" if rsi_val < 30 else f"متوازن ({rsi_val:.1f}) ⚖️"
        macd_status = "إيجابي 🟢" if macd_val > signal_val else "سلبي 🔴"

        notes, bull_score, bear_score = analyze_candlesticks(df)
        
        bullish_score = bull_score + (1 if change > 0 else 0) + (2 if macd_val > signal_val else 0) + (1 if rsi_val < 40 else 0)
        bearish_score = bear_score + (1 if change <= 0 else 0) + (2 if macd_val <= signal_val else 0) + (1 if rsi_val > 60 else 0)

        if bullish_score > bearish_score + 1:
            decision = "🟢 **القرار: دخول LONG (شراء)** 🚀"
        elif bearish_score > bullish_score + 1:
            decision = "🔴 **القرار: دخول SHORT (بيع)** 📉"
        else:
            decision = "⚖️ **القرار: الانتظار والحياد (Wait)** ⏳"

        reasons = list(notes)
        reasons.append(f"▪️ RSI يدعم الشراء." if rsi_val < 40 else f"▪️ RSI قريب من التشبع." if rsi_val > 60 else "")
        reasons.append("▪️ MACD إيجابي." if macd_val > signal_val else "▪️ MACD سلبي.")

        stats = {
            "symbol": symbol.upper(), "price": price, "change": change, "trend": trend,
            "rsi": rsi_status, "macd": macd_status, "decision": decision,
            "reasons": "\n".join([r for r in reasons if r]),
            "timeframe": timeframe, "r1": r1, "r2": r2, "s1": s1, "s2": s2
        }
        
        chart_bytes = generate_chart_with_analysis(hist, symbol, timeframe, r1, s1)
        return stats, chart_bytes
    return None, None

async def get_market_data(symbol, timeframe="1d"):
    cache_key = f"{symbol}_{timeframe}"
    if cache_key in cache: return cache[cache_key]
    try:
        stats, chart_bytes = await asyncio.to_thread(fetch_yf_sync, symbol, timeframe)
        if stats and chart_bytes: cache[cache_key] = (stats, chart_bytes)
        return stats, chart_bytes
    except Exception as e:
        return None, None

async def create_signal_message(data):
    # تم إزالة قسم "التوقع المستقبلي" من هنا لجعله مستقلاً
    p = data['price']
    return (
        f"🎯 **تحليل {data['symbol']}** (فريم: `{data['timeframe']}`)\n"
        f"💰 السعر الحالي: `{p:,.2f}`\n"
        f"📊 الاتجاه: {data['trend']} (`{data['change']:.2f}%`)\n"
        f"📉 RSI: {data['rsi']} | 📈 MACD: {data['macd']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📖 **دليل قراءة الشارت:**\n"
        "🟩 **الخط الأخضر:** مستوى الدعم (Support)\n"
        "🟥 **الخط الأحمر:** مستوى المقاومة (Resistance)\n"
        "⬆️ **سهم أخضر:** نموذج شرائي (إشارة صعود)\n"
        "⬇️ **سهم أحمر:** نموذج بيعي (إشارة هبوط)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧱 **مستويات الدعم والمقاومة:**\n"
        f"🔺 مقاومات (Resistance): `{data['r1']:,.2f}` | `{data['r2']:,.2f}`\n"
        f"🔻 دعومات (Support): `{data['s1']:,.2f}` | `{data['s2']:,.2f}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{data['decision']}\n\n"
        "🕯️ **الأسباب الفنية:**\n"
        f"{data['reasons']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🟢 **LONG:** الدخول: `~{p:,.2f}` | 🛑 SL: `~{p*0.985:,.2f}` | 🎯 TP: `~{p*1.02:,.2f}`\n"
        f"🔴 **SHORT:** الدخول: `~{p:,.2f}` | 🛑 SL: `~{p*1.015:,.2f}` | 🎯 TP: `~{p*0.98:,.2f}`\n\n"
        "**إن شاء الله 🤲**"
    )

# =========================================================
# 6. واجهة المستخدم (TELEGRAM HANDLERS)
# =========================================================

def allowed(update: Update) -> bool:
    return update.effective_chat and str(update.effective_chat.id) == str(CHAT_ID)

def main_keyboard():
    # تعديل الأزرار لتعكس الفصل الواضح
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔮 التوقعات (15m, 1h, 4h, 1d)", callback_data="forecast_menu")],
        [InlineKeyboardButton("⏱️ التحليل الفني والشارت", callback_data="select_coin")],
        [InlineKeyboardButton("₿ BTC [1d]", callback_data="sig_BTC_1d"), InlineKeyboardButton("◎ SOL [1d]", callback_data="sig_SOL_1d")],
        [InlineKeyboardButton("💎 Hyperliquid/DEX", callback_data="dex_menu"), InlineKeyboardButton("📰 الأخبار", callback_data="news_menu")],
        [InlineKeyboardButton("🔥 Sentiment", callback_data="hype")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return
    await update.message.reply_text("🚀 **AURA TRADING BOT (PRO MAGIC)** 🪄\n\nاختر من القائمة الرئيسية:", reply_markup=main_keyboard(), parse_mode="Markdown")

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.message.chat.id) != str(CHAT_ID): return await query.answer("Access Denied.", show_alert=True)
    await query.answer()
    data = query.data

    try: await query.message.delete()
    except: pass

    if data == "home":
        await context.bot.send_message(chat_id=CHAT_ID, text="🚀 **القائمة الرئيسية:**", reply_markup=main_keyboard(), parse_mode="Markdown")
    
    # -----------------------------------------------
    # قائمة فازة التوقعات المستقلة
    # -----------------------------------------------
    elif data == "forecast_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("₿ توقعات BTC", callback_data="fc_BTC"), InlineKeyboardButton("◎ توقعات SOL", callback_data="fc_SOL")],
            [InlineKeyboardButton("Ξ توقعات ETH", callback_data="fc_ETH"), InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await context.bot.send_message(chat_id=CHAT_ID, text="🔮 **اختر العملة لمعرفة التوقعات للفريمات (15m, 1h, 4h, 1d):**", reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("fc_"):
        sym = data.split("_")[1]
        loading_msg = await context.bot.send_message(chat_id=CHAT_ID, text=f"⏳ جاري قراءة التوقعات المستقبلية لـ {sym}...")
        
        forecast_text = await asyncio.to_thread(generate_forecast_sync, sym)
        
        await loading_msg.delete()
        await context.bot.send_message(
            chat_id=CHAT_ID, text=forecast_text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث التوقع", callback_data=data), InlineKeyboardButton("🔙 رجوع", callback_data="forecast_menu")]])
        )
    # -----------------------------------------------
        
    elif data == "select_coin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("₿ BTC", callback_data="tf_BTC"), InlineKeyboardButton("◎ SOL", callback_data="tf_SOL")],
            [InlineKeyboardButton("Ξ ETH", callback_data="tf_ETH"), InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await context.bot.send_message(chat_id=CHAT_ID, text="🪙 **اختر العملة للتحليل والشارت:**", reply_markup=kb, parse_mode="Markdown")

    elif data == "news_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("₿ أخبار BTC", callback_data="news_BTC"), InlineKeyboardButton("◎ أخبار SOL", callback_data="news_SOL")],
            [InlineKeyboardButton("Ξ أخبار ETH", callback_data="news_ETH"), InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await context.bot.send_message(chat_id=CHAT_ID, text="📰 **اختر العملة لقراءة الأخبار:**", reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("news_"):
        sym = data.split("_")[1]
        loading_msg = await context.bot.send_message(chat_id=CHAT_ID, text=f"⏳ جاري جلب الأخبار لـ {sym}...")
        news_text = await asyncio.to_thread(fetch_news_sync, sym)
        await loading_msg.delete()
        await context.bot.send_message(
            chat_id=CHAT_ID, text=news_text, parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data=data), InlineKeyboardButton("🔙 رجوع", callback_data="news_menu")]])
        )

    elif data == "dex_menu":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("PURR", callback_data="dex_PURR"), InlineKeyboardButton("HYPE", callback_data="dex_HYPE")],
            [InlineKeyboardButton("WIF", callback_data="dex_WIF"), InlineKeyboardButton("PEPE", callback_data="dex_PEPE")],
            [InlineKeyboardButton("🔙 القائمة", callback_data="home")]
        ])
        await context.bot.send_message(chat_id=CHAT_ID, text="💎 **اختر عملة من DEX:**", reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("dex_") and data != "dex_menu":
        sym = data.split("_")[1]
        loading_msg = await context.bot.send_message(chat_id=CHAT_ID, text=f"⏳ جاري جلب بيانات {sym}...")
        msg = await asyncio.to_thread(fetch_dex_sync, sym)
        await loading_msg.delete()
        await context.bot.send_message(
            chat_id=CHAT_ID, text=msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data=data), InlineKeyboardButton("🔙 رجوع", callback_data="home")]])
        )

    elif data.startswith("tf_"):
        sym = data.split("_")[1]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("15m", callback_data=f"sig_{sym}_15m"), InlineKeyboardButton("1h", callback_data=f"sig_{sym}_1h")],
            [InlineKeyboardButton("4h", callback_data=f"sig_{sym}_4h"), InlineKeyboardButton("1d", callback_data=f"sig_{sym}_1d")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="select_coin")]
        ])
        await context.bot.send_message(chat_id=CHAT_ID, text=f"📊 **اختر الفريم لـ {sym}:**", reply_markup=kb, parse_mode="Markdown")

    elif data.startswith("sig_"):
        _, sym, tf = data.split("_")
        loading_msg = await context.bot.send_message(chat_id=CHAT_ID, text=f"⏳ جاري التحليل ورسم الشارت لـ {sym}...")
        stats, chart_bytes = await get_market_data(sym, tf)
        await loading_msg.delete()

        if not stats:
            return await context.bot.send_message(chat_id=CHAT_ID, text=f"❌ عذراً، خطأ في بيانات {sym}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="home")]]))

        msg = await create_signal_message(stats)
        await context.bot.send_photo(
            chat_id=CHAT_ID, photo=chart_bytes, caption=msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data=data), InlineKeyboardButton("🔙 رجوع", callback_data="home")]])
        )

    elif data == "hype":
        try:
            r = await asyncio.to_thread(requests.get, FEAR_GREED_URL, params={"limit": 1}, timeout=10)
            item = r.json()["data"][0]
            await context.bot.send_message(
                chat_id=CHAT_ID, text=f"🔥 **Market Sentiment**\nFear & Greed: `{item['value']}/100` ({item['value_classification']})",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="home")]])
            )
        except Exception as e:
            logger.error(f"Sentiment Error: {e}")

async def post_init(application: Application):
    asyncio.create_task(start_web_server(application))

def main():
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))
    logger.info("Bot is running...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
