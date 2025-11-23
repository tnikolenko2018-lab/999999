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
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running.')

def start_health_check_server():
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
                         "Пришли скриншот графика и получи **быстрый анализ, прогноз и точные точки входа**.\n"
                         "Для вопросов по трейдингу пиши текст.")

# --- ОБРАБОТЧИК ДЛЯ ТЕКСТОВЫХ СООБЩЕНИЙ (Строгая специализация) ---
@dp.message(F.text)
async def handle_text_message(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return
    
    user_text = message.text.lower().strip()
    
    # 1. Обработка благодарности
    if user_text in ["спасибо", "спс", "благодарю", "окей", "ок", "спс большое"]:
        await message.answer("Рад помочь! Успешной торговли. 🚀")
        return
    
    status_msg = await message.answer("🧠 Думаю и пишу ответ...")
    
    try:
        # 2. Строгий промпт для SMC/Трейдинга
        prompt_text = (
            "Ты узкоспециализированный AI-аналитик по Smart Money Concepts (SMC) и техническому анализу. "
            "Отвечай только по теме трейдинга, анализа, расчетов рисков и SMC. Ответ должен быть максимально "
            "кратким и по существу. "
            "Если вопрос НЕ связан с трейдингом, финансовым анализом или SMC, "
            "ответь СТРОГО: 'Я аналитик на ИИ, ваш личный помощник. Моя специализация — технический анализ и SMC.' "
            f"Запрос: {user_text}"
        )
        
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt_text,
        )

        await message.answer(response.text)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Ошибка при обработке текста: {e}")
        await message.answer(f"Произошла ошибка при обработке текста: {e}. Попробуй еще раз.")

# --- ОБРАБОТЧИК ДЛЯ АНАЛИЗА ГРАФИКОВ (СИГНАЛЫ) ---
@dp.message(F.photo)
async def analyze_chart(message: Message):
    if not client:
        await message.answer("AI-сервис недоступен.")
        return

    status_msg = await message.answer("🚨 Выполняю поиск точек входа по SMC...")

    try:
        photo = message.photo[-1]
        bot_file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(bot_file.file_path)
        image = Image.open(file_data)
        
        # НОВЫЙ ПРОМПТ ДЛЯ ТОЧНЫХ СИГНАЛОВ
        prompt = [
            "Ты ультра-фокусированный AI-аналитик, работающий исключительно по концепции Smart Money Concepts (SMC). Твоя задача — предоставить ЧЕТКИЙ ТОРГОВЫЙ СИГНАЛ в виде цифр, основываясь на Order Blocks, FVG (Fair Value Gaps), Breaker Blocks и ликвидности. \n\n"
            "**СТРУКТУРА ОТВЕТА (ОЧЕНЬ СТРОГО — ТОЛЬКО ЦИФРЫ И КОРОТКИЙ АНАЛИЗ):**\n"
            "1. **КЛЮЧЕВОЕ НАПРАВЛЕНИЕ (2 минуты):** ПОКУПКА (Buy) 🟢 или ПРОДАЖА (Sell) 🔴.\n"
            "2. **ТОЧКА ВХОДА (ENTRY):** Укажи конкретную цену входа (например, 1.25000).\n"
            "3. **СТОП-ЛОСС (SL):** Укажи конкретную цену стоп-лосса.\n"
            "4. **ТЭЙК-ПРОФИТ (TP):** Укажи конкретную цену для первой цели (Take Profit 1).\n"
            "5. **ОСНОВАНИЕ:** Кратко (одно предложение) укажи элемент SMC (например, Order Block на 1.24900). \n"
            "**ОБЯЗАТЕЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ:** Это анализ изображения, а не реальные котировки. Всегда проверяйте цифры. Это не финансовый совет и не гарантия прибыли.",
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
