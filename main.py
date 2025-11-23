import asyncio
import logging
import os
from io import BytesIO
from http.server import BaseHTTPRequestHandler, HTTPServer # Новые импорты для заглушки

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from PIL import Image
from google import genai
from google.genai import types

# --- Настройка логов и переменных ---
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("TELEGRAM_TOKEN или GEMINI_API_KEY не заданы.")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Ошибка инициализации Gemini: {e}")
    client = None
    
# --- ЗАГЛУШКА ДЛЯ RENDER (Открывает порт, чтобы избежать таймаута) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    """Минимальный HTTP-сервер для ответа на Health Check Render."""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running.')

def start_health_check_server():
    """Запускает сервер на порту, который требует Render (8080)."""
    PORT = int(os.environ.get("PORT", 8080)) # Порт, который Render ожидает
    server = HTTPServer(('', PORT), HealthCheckHandler)
    logging.info(f"Заглушка Render: Запущен HTTP-сервер на порту {PORT}")
    server.serve_forever()
# -----------------------------------------------------------------------


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not client:
        await message.answer("Ошибка: Ключ Gemini API недействителен. Бот не может работать с AI.")
        return
    await message.answer("Привет! Я твой AI-помощник на Gemini. 🚀\n"
                         "Пришли мне скриншот графика, и я его проанализирую.")

@dp.message(F.photo)
async def analyze_chart(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return
    # [Остальной код анализа графика остается прежним]...
    status_msg = await message.answer("🧐 Анализирую график с помощью Gemini...")
    try:
        photo = message.photo[-1]
        bot_file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(bot_file.file_path)
        image = Image.open(file_data)
        
        prompt = [
            "Ты профессиональный трейдер и психолог. Твоя задача: 1. Оценить ситуацию на графике. 2. Если есть цифры баланса — прокомментировать. 3. Дать мотивацию и совет по рискам. Отвечай коротко, по делу и с эмодзи.",
            image
        ]
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        await message.answer(response.text)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Ошибка при анализе: {e}")
        await message.answer(f"Произошла ошибка при анализе: {e}. Проверь логи Render.")

async def start_telegram_bot():
    """Асинхронный запуск Telegram-бота."""
    # Решает TelegramConflictError
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)


async def main():
    # Запускаем Health Check Server в отдельном потоке
    health_check_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_check_thread.start()
    
    # Запускаем Telegram-бота
    await start_telegram_bot()


if __name__ == "__main__":
    import threading
    asyncio.run(main())
