import os
import logging

from google import genai
from google.genai import types
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты полезный ассистент в Telegram. Отвечай кратко и по делу, на языке пользователя.",
)
# Необязательно: список разрешённых Telegram ID через запятую (пусто = все)
ALLOWED = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}
MAX_HISTORY = 30  # сколько последних сообщений помнить

client = genai.Client(api_key=GEMINI_API_KEY)
histories: dict[int, list[types.Content]] = {}


def allowed(update: Update) -> bool:
    return not ALLOWED or update.effective_user.id in ALLOWED


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    await update.message.reply_text(
        "Привет! Напиши мне что угодно.\n/reset — очистить память диалога."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    histories.pop(update.effective_chat.id, None)
    await update.message.reply_text("Память очищена.")


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    chat_id = update.effective_chat.id
    text = update.message.text
    history = histories.setdefault(chat_id, [])
    history.append(types.Content(role="user", parts=[types.Part(text=text)]))

    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    try:
        resp = await client.aio.models.generate_content(
            model=MODEL,
            contents=history,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        answer = resp.text or "Пустой ответ, попробуй переформулировать."
    except Exception as e:
        log.exception("Gemini error")
        history.pop()  # не засоряем историю неудачным запросом
        await update.message.reply_text(f"Ошибка ИИ: {e}")
        return

    history.append(types.Content(role="model", parts=[types.Part(text=answer)]))
    del history[:-MAX_HISTORY]

    # лимит Telegram — 4096 символов
    for i in range(0, len(answer), 4000):
        await update.message.reply_text(answer[i : i + 4000])


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
    log.info("Bot started, model=%s", MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()
