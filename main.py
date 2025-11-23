import asyncio
import logging
import os
from io import BytesIO
import threading 
from http.server import BaseHTTPRequestHandler, HTTPServer 

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
    
# --- ЗАГЛУШКА ДЛЯ RENDER (Health Check) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    """Минимальный HTTP-сервер для ответа на Health Check Render."""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running.')

def start_health_check_server():
    """Запускает сервер на порту, который требует Render (8080)."""
    PORT = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('', PORT), HealthCheckHandler)
    logging.info(f"Заглушка Render: Запущен HTTP-сервер на порту {PORT}")
    server.serve_forever()
# -----------------------------------------------------------------------


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not client:
        await message.answer("Ошибка: Ключ AI API недействителен. Бот не может работать с AI.")
        return
    
    # Краткое приветствие для SMC-аналитика
    await message.answer("Привет! Я твой SMC-аналитик. ⚡️\n"
                         "Пришли скриншот графика и получи **быстрый анализ и прогноз**.\n"
                         "Для общих вопросов пиши текст.")

# --- ОБРАБОТЧИК ДЛЯ ТЕКСТОВЫХ СООБЩЕНИЙ (Общая помощь) ---
@dp.message(F.text)
async def handle_text_message(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return
    
    status_msg = await message.answer("🧠 Думаю и пишу ответ...")
    
    try:
        # Общий промпт
        prompt_text = f"Ты опытный финансовый аналитик. Ответь на вопрос пользователя, выполни расчет или дай совет. Запрос: {message.text}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt_text,
        )

        await message.answer(response.text)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Ошибка при обработке текста: {e}")
        await message.answer(f"Произошла ошибка при обработке текста: {e}. Попробуй еще раз.")

# --- ОБРАБОТЧИК ДЛЯ АНАЛИЗА ГРАФИКОВ (SMC И СКОРОСТЬ) ---
@dp.message(F.photo)
async def analyze_chart(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return

    status_msg = await message.answer("🔎 Быстрый SMC-анализ...")

    try:
        photo = message.photo[-1]
        bot_file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(bot_file.file_path)
        image = Image.open(file_data)
        
        # НОВЫЙ, СКОРОСТНОЙ ПРОМПТ ДЛЯ SMC
        prompt = [
            "Ты эксперт по Smart Money Concepts (SMC). Твоя задача — дать **краткий, лаконичный и быстрый** анализ. Используй термины SMC (Order Block, FVG, ликвидность, BOS, CHoCH).\n\n"
            "**СТРУКТУРА ОТВЕТА (Строго!):**\n"
            "1. **КЛЮЧЕВОЙ УРОВЕНЬ:** Найденный Order Block / FVG / Зона ликвидности.\n"
            "2. **ПРОГНОЗ (2 минуты):** Вероятностное направление цены (ВВЕРХ ⬆️ или ВНИЗ ⬇️).\n"
            "3. **ПРИЧИНА:** Кратко (1-2 предложения) объясни, почему (например, 'реакция на Order Block' или 'снятие ликвидности').\n"
            "4. **БАЛАНС:** Комментарий по балансу (если виден).\n"
            "**ВАЖНО:** Не пиши длинных вступлений и заключений. Только факты по пунктам. Добавь дисклеймер, что это не гарантия.",
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
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)


async def main():
    health_check_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_check_thread.start()
    
    await start_telegram_bot()


if __name__ == "__main__":
    asyncio.run(main())
