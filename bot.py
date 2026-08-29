import os
import threading
import requests
from flask import Flask

from google import genai
from google.genai import types

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================
# Render Web Server
# =========================

app_flask = Flask(__name__)


@app_flask.route("/")
def home():
    return "Bot is running 24/7!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# Environment Variables
# =========================

TELEGRAM_TOKEN = "8829847415:AAGqU-VGZ--S_dohigg6I_bS65F3-GGgYa8"
GEMINI_API_KEY = AQ.Ab8RN6K7GDPCmQfKRODRckpX4TgzTG1LNG9pNjTGVsFB58x01g


if not TELEGRAM_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from Render Environment Variables")


if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing from Render Environment Variables")


# =========================
# Gemini
# =========================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


SYSTEM_PROMPT = """
أنت مساعد محترف في تحليل أسواق العملات الرقمية.

عندما يطلب المستخدم تحليل سوق أو يرسل Chart:

- حلل اتجاه السعر.
- حلل الشموع اليابانية.
- ابحث عن الدعم والمقاومة.
- حلل RSI إذا كان ظاهراً في الصورة.
- حلل MACD إذا كان ظاهراً في الصورة.
- حلل مناطق السيولة.
- ابحث عن Breakout أو Fakeout.
- حدد السيناريو الأقوى.
- إذا كانت المعطيات غير كافية، قل ذلك بوضوح ولا تخترع مؤشرات غير ظاهرة.

عند إعطاء سيناريو تداول:
- وضح هل الميل Long أو Short.
- اقترح Entry محتمل.
- وضح Stop Loss.
- وضح Take Profit.
- اذكر مستوى المخاطرة.
- لا تقدم التداول على أنه مضمون.
- إذا كان السوق غير واضح، قل WAIT بدل إجبار المستخدم على Long أو Short.

كن واضحاً ومختصراً ومنظماً.
"""


MODEL = "gemini-3.7-flash"


# =========================
# Start Command
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🤖 مرحبا يا ياسين!\n\n"
        "البوت جاهز 🔥\n\n"
        "ابعثلي:\n"
        "• اسم العملة\n"
        "• أو Chart 📊\n\n"
        "ونحللهالك."
    )


# =========================
# Gemini Text Function
# =========================

def generate_text(prompt: str) -> str:

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT
        )
    )

    if not response.text:
        return "ما رجعتليش Gemini إجابة."

    return response.text


# =========================
# Handle Text
# =========================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    user_message = update.message.text

    processing_msg = await update.message.reply_text(
        "⏳ جاري تحليل السوق..."
    )

    try:

        prompt = f"""
حلل طلب المستخدم التالي:

{user_message}
"""

        answer = generate_text(prompt)

        await processing_msg.edit_text(answer)

    except Exception as e:

        print("TEXT ERROR:")
        print(repr(e))

        await processing_msg.edit_text(
            "❌ صار خطأ أثناء الاتصال بـ Gemini.\n"
            "عاود جرّب بعد شوية."
        )


# =========================
# Handle Photo
# =========================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.photo:
        return

    processing_msg = await update.message.reply_text(
        "👁️ جاري قراءة الـChart..."
    )

    try:

        # Get Telegram file
        telegram_file = await update.message.photo[-1].get_file()

        # Download image directly
        image_response = requests.get(
            telegram_file.file_path,
            timeout=30
        )

        image_response.raise_for_status()

        image_bytes = image_response.content

        # Detect MIME type
        mime_type = "image/jpeg"

        if telegram_file.file_path.lower().endswith(".png"):
            mime_type = "image/png"

        elif telegram_file.file_path.lower().endswith(".webp"):
            mime_type = "image/webp"

        # Gemini image part
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type
        )

        prompt = """
حلل الـChart الموجود في الصورة تحليلاً احترافياً.

ركز على:

1. اتجاه السوق Trend
2. حركة الشموع اليابانية
3. Support / Resistance
4. Liquidity
5. Breakout / Fakeout
6. RSI إذا كان ظاهراً
7. MACD إذا كان ظاهراً
8. مناطق الدخول المحتملة
9. Stop Loss
10. Take Profit

في النهاية أعطني:

📊 الاتجاه:
LONG / SHORT / WAIT

🎯 Entry:
...

🛑 Stop Loss:
...

💰 Take Profit:
...

⚠️ Risk:
Low / Medium / High

إذا كان RSI أو MACD غير ظاهرين في الصورة، لا تخترع قيمهم.
إذا كانت الصورة غير واضحة أو المعطيات غير كافية، قل ذلك بصراحة.
"""

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                prompt,
                image_part
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            )
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response")

        await processing_msg.edit_text(
            response.text
        )

    except Exception as e:

        print("PHOTO ERROR:")
        print(repr(e))

        await processing_msg.edit_text(
            "❌ ما نجمتش نعالج الـChart.\n"
            "تأكد اللي الصورة واضحة وعاود ابعثها."
        )


# =========================
# Error Handler
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print("TELEGRAM ERROR:")
    print(repr(context.error))


# =========================
# Main
# =========================

def main():

    # Start Flask for Render
    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    print("Starting Telegram bot...")

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # Text
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    # Photos
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    # Errors
    application.add_error_handler(
        error_handler
    )

    print("Bot is polling...")

    application.run_polling(
        drop_pending_updates=True
    )


# =========================
# Run
# =========================

if __name__ == "__main__":
    main()
