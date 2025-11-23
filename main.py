import asyncio
import logging
import os
import re 
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

# НОВЫЙ СПИСОК РАЗРЕШЕННЫХ ПОЛЬЗОВАТЕЛЕЙ (Чтение из настроек Render)
# ID должны быть перечислены через запятую без пробелов: "123456789,987654321"
ALLOWED_USER_IDS_STR = os.getenv("ALLOWED_USER_IDS") 

# Преобразуем строку ID в список чисел
if ALLOWED_USER_IDS_STR:
    try:
        # Очистка и преобразование строки ID в список чисел
        ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USER_IDS_STR.split(',') if uid.strip()]
    except ValueError:
         logging.error("Ошибка: Неверный формат ID в ALLOWED_USER_IDS. Должны быть только числа, разделенные запятыми.")
         ALLOWED_USERS = []
else:
    logging.warning("Предупреждение: Переменная ALLOWED_USER_IDS не установлена. Доступ ограничен.")
    ALLOWED_USERS = []

def is_user_allowed(user_id: int) -> bool:
    """Проверяет, находится ли ID пользователя в списке разрешенных."""
    return user_id in ALLOWED_USERS

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
    # 🛑 ПРОВЕРКА ДОСТУПА 🛑
    if not is_user_allowed(message.from_user.id):
        await message.answer("Извините, этот бот является приватным. Доступ только по приглашениям.")
        return
        
    if not client:
        await message.answer("Ошибка: Ключ AI API недействителен. Бот не может работать с AI.")
        return
    
    await message.answer("Привет! Я твой AI-аналитик. ⚡️\n"
                         "Пришли скриншот графика и получи **быстрый анализ и точные точки входа**.\n"
                         "Для расчетов риска или вопросов по трейдингу пиши текст.")

# --- ОБРАБОТЧИК ДЛЯ ТЕКСТОВЫХ СООБЩЕНИЙ (Строгая специализация + Расчеты) ---
@dp.message(F.text)
async def handle_text_message(message: Message):
    # 🛑 ПРОВЕРКА ДОСТУПА 🛑
    if not is_user_allowed(message.from_user.id):
        await message.answer("Извините, этот бот является приватным. Доступ только по приглашениям.")
        return
        
    if not client:
        await message.answer("AI-сервис недоступен.")
        return
    
    user_text = message.text.lower().strip()
    
    # 1. Обработка благодарности
    if user_text in ["спасибо", "спс", "благодарю", "окей", "ок", "спс большое"]:
        await message.answer("Рад помочь! Успешной торговли. 🚀")
        return
        
    # 2. Обработка запроса на расчет риска (1% от баланса)
    if "торговать" in user_text or "рассчитать" in user_text or "сумм" in user_text or "баланс" in user_text:
        numbers = re.findall(r'\d+', user_text)
        if numbers:
            try:
                balance = float(numbers[-1]) 
                risk_percent = 0.01
                risk_amount = balance * risk_percent
                
                response_text = (
                    f"**Расчет риска по правилу 1%:**\n"
                    f"Ваш баланс: **{balance:.2f}**\n"
                    f"Рекомендуемый риск на сделку (1%): **{risk_amount:.2f}**\n\n"
                    "**Правильный подход:** Всегда входите в сделку суммой, равной **1%** от вашего текущего баланса. Это самая безопасная стратегия для долгосрочной торговли."
                )
                await message.answer(response_text)
                return
            except ValueError:
                pass 
    
    status_msg = await message.answer("🧠 Думаю и пишу ответ...")
    
    try:
        # 3. Строгий промпт для SMC/Трейдинга (Общие вопросы)
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

# --- ОБРАБОТЧИК ДЛЯ АНАЛИЗА ГРАФИКОВ (ФИНАЛЬНЫЙ СИГНАЛ) ---
@dp.message(F.photo)
async def analyze_chart(message: Message):
    # 🛑 ПРОВЕРКА ДОСТУПА 🛑
    if not is_user_allowed(message.from_user.id):
        await message.answer("Извините, этот бот является приватным. Доступ только по приглашениям.")
        return
        
    if not client:
        await message.answer("AI-сервис недоступен.")
        return

    status_msg = await message.answer("🚨 Выполняю технический анализ...")

    try:
        photo = message.photo[-1]
        bot_file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(bot_file.file_path)
        image = Image.open(file_data)
        
        prompt = [
            "Ты ультра-фокусированный AI-аналитик по техническому анализу, использующий концепцию Smart Money Concepts. Твоя задача — предоставить ЧЕТКИЙ ТОРГОВЫЙ СИГНАЛ в виде цифр, основываясь на анализе графика, и подтвердить его дополнительным рыночным фильтром.\n\n"
            "**СТРУКТУРА ОТВЕТА (ОЧЕНЬ СТРОГО — ТОЛЬКО КЛЮЧЕВЫЕ ПУНКТЫ):**\n"
            "1. **СИГНАЛ:** [ПОКУПКА 🟢 ⬆️] или [ПРОДАЖА 🔴 ⬇️]\n"
            "2. **ВХОД (ENTRY):** Укажи конкретную цену входа.\n"
            "3. **ДЛИТЕЛЬНОСТЬ:** 2 минуты.\n"
            "4. **АНАЛИЗ:** Кратко (1-2 слова) укажи причину движения.\n"
            "5. **ФИЛЬТР:** Кратко укажи дополнительное подтверждение (Тренд/Импульс).\n"
            "6. **БАЛАНС:** Комментарий по балансу (если виден).\n"
            "**ОБЯЗАТЕЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ:** Это не финансовый совет и не гарантия прибыли. **Если изображение не является графиком**, ответь СТРОГО: 'Я делаю разбор только технических графиков, а не других фото. Пришлите, пожалуйста, график.'"
            ,
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
        await message.answer(f"Произошла ошибка при анализе: {e}. Попробуй еще раз.")


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
