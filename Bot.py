import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# سرفر Flask بسيط باش منصة Render تفهم أن التطبيق يخدم
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port)

# المعطيات متاع البوت وجوجل
TELEGRAM_TOKEN = "8829847415:AAGqU-VGZ--S_dohigg6I_bS65F3-GGgYa8"
GEMINI_API_KEY = "AQ.Ab8RN6LrUF1hzl2WhKOseWJ-4VQ..."

genai.configure(api_key=GEMINI_API_KEY)

system_prompt = """
أنت متداول عملات رقمية محترف وخبير في التحليل الفني للعقود الآجلة (Futures). 
عندما يطلب منك المستخدم تحليل سوق أو صورة لمخطط بياني (Chart)، قم تحليل الشموع اليابانية، 
وركز على استخراج النماذج الفنية، ومؤشرات الزخم مثل RSI و MACD. 
أعطِ رأياً واضحاً حول ما إذا كان الاتجاه يميل إلى Long أو Short بناءً على السيولة وحركة السعر، مع التذكير دائماً بإدارة المخاطر.
"""

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=system_prompt
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً بك يا ياسين! البوت يخدم الآن على السيرفر بصفة رسمية. ابعثلي اسم أي عملة أو تصويرة شارت باش نحللهالك بـ Pro.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    processing_msg = await update.message.reply_text("⏳ جاري تحليل السوق والـ Hype...")
    try:
        response = model.generate_content(user_message)
        await processing_msg.edit_text(response.text)
    except Exception as e:
        await processing_msg.edit_text("صار خطأ في التحليل، عاود جرب.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    processing_msg = await update.message.reply_text("👁️ جاري قراءة الشموع اليابانية والمؤشرات...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_byte_array = await photo_file.download_as_bytearray()
        image_parts = [{"mime_type": "image/jpeg", "data": photo_byte_array}]
        prompt = "حلل هذا المخطط البياني بالتفصيل، ما هي نقاط الدخول والخروج والاتجاه المحتمل (Long/Short)؟"
        response = model.generate_content([prompt, image_parts[0]])
        await processing_msg.edit_text(response.text)
    except Exception as e:
        await processing_msg.edit_text("ما نجمتش نقرا التصويرة بوضوح، ثبت منها وعاود.")

def main():
    # تشغيل سرفر Flask في الخلفية
    t = threading.Thread(target=run_flask)
    t.start()

    # تشغيل البوت
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
