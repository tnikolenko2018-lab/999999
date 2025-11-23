import asyncio
import logging
import os
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from PIL import Image # Новая библиотека для работы с изображениями
from google import genai
from google.genai import types

# Настройка логов
logging.basicConfig(level=logging.INFO)

# --- Инициализация и проверка переменных ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Теперь ищем ключ Gemini

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("TELEGRAM_TOKEN или GEMINI_API_KEY не заданы в Variables.")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализация клиента Gemini
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Ошибка инициализации Gemini: {e}")
    # Если ключ неверный, клиент не будет создан
    client = None

# -------------------------------------------

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

    status_msg = await message.answer("🧐 Анализирую график с помощью Gemini...")

    try:
        # 1. Скачиваем фото с серверов Telegram
        photo = message.photo[-1]
        bot_file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(bot_file.file_path)
        
        # 2. Создаем объект изображения PIL для Gemini
        image = Image.open(file_data)
        
        # 3. Формируем промпт и отправляем в Gemini Pro Vision
        prompt = [
            "Ты профессиональный трейдер и психолог. Твоя задача: 1. Оценить ситуацию на графике. 2. Если есть цифры баланса — прокомментировать. 3. Дать мотивацию и совет по рискам. Отвечай коротко, по делу и с эмодзи.",
            image # Передаем объект изображения напрямую
        ]

        response = client.models.generate_content(
            model="gemini-2.5-flash", # Модель для быстрой работы с изображениями
            contents=prompt,
        )

        # 4. Ответ
        await message.answer(response.text)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Ошибка при анализе: {e}")
        await message.answer(f"Произошла ошибка при анализе: {e}. Проверь логи Railway.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
