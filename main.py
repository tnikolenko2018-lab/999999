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
    
    await message.answer("Привет! Я твой AI-наставник. 🚀\n"
                         "Я здесь, чтобы помочь тебе в работе и дать поддержку.\n"
                         "Ты можешь: \n"
                         "1. Прислать скриншот графика для **технического анализа и прогноза на 2 минуты**.\n"
                         "2. Задать любой вопрос о работе или попросить меня что-то рассчитать. **Я общаюсь как человек!**")

# --- ОБРАБОТЧИК ДЛЯ ТЕКСТОВЫХ СООБЩЕНИЙ (Общая помощь и расчеты) ---
@dp.message(F.text)
async def handle_text_message(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return
    
    status_msg = await message.answer("🧠 Думаю и пишу ответ...")
    
    try:
        # Промпт для общих вопросов и расчетов (человеческий тон)
        prompt_text = f"Ты очень дружелюбный и поддерживающий финансовый наставник, который общается как человек. Твоя задача — дать максимально полезный совет, выполнить расчет или ответить на вопрос пользователя, используя теплый, человеческий тон. Всегда добавляй слова поддержки и мотивации. Запрос пользователя: {message.text}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt_text,
        )

        await message.answer(response.text)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Ошибка при обработке текста: {e}")
        await message.answer(f"Произошла ошибка при обработке текста: {e}. Попробуй еще раз.")

# --- ОБРАБОТЧИК ДЛЯ АНАЛИЗА ГРАФИКОВ (С ПРОГНОЗОМ) ---
@dp.message(F.photo)
async def analyze_chart(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return

    status_msg = await message.answer("🧐 Анализирую график, даю прогноз и пишу тебе ответ...")

    try:
        photo = message.photo[-1]
        bot_file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(bot_file.file_path)
        image = Image.open(file_data)
        
        # НОВЫЙ ПРОМПТ ДЛЯ ПРОГНОЗА
        prompt = [
            "Ты очень дружелюбный, поддерживающий и высококвалифицированный финансовый наставник. Твоя задача — дать максимально полезный анализ и прогноз, общаясь как человек. \n\n"
            "1. **АНАЛИЗ И ПРОГНОЗ:** Проведи быстрый технический анализ графика (свечи, уровни поддержки/сопротивления, максимумы/минимумы). Дай свой **вероятностный прогноз** движения цены на следующие **2 минуты** (ВВЕРХ/ВНИЗ), ясно объяснив, почему (например, отскок от минимума или пробой максимума). **Обязательно добавь предупреждение, что это не финансовый совет и не гарантия.**\n"
            "2. **БАЛАНС:** Прокомментируй цифры баланса (если они видны).\n"
            "3. **ПОДДЕРЖКА:** Дай мотивацию, поддержку и совет по управлению рисками.\n"
            "Общайся тепло, по-человечески, и используй эмодзи.",
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
