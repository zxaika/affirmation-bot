import os
import time
import asyncio
import random
from datetime import datetime
from typing import List
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq

# Задержка для хостинга
time.sleep(5)

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден")
    exit(1)

if not GROQ_API_KEY:
    print("❌ ОШИБКА: GROQ_API_KEY не найден")
    exit(1)

print(f"✅ Токен загружен: {TELEGRAM_BOT_TOKEN[:15]}...")
print(f"✅ API ключ загружен: {GROQ_API_KEY[:15]}...")

# Файлы
CHATS_FILE = "subscribed_chats.txt"
HISTORY_FILE = "affirmation_history.txt"

# ========== ПРОМПТ ==========
AFFIRMATION_PROMPT = """ты создаёшь «аффирмашку дня» — короткое позитивное утверждение о себе.

стиль:
- первая буква предложения ЗАГЛАВНАЯ, остальные строчные
- ироничное, забавное, жизнеутверждающее, кринжовое — что хочешь
- темы любые, не ограничен

формат:
просто текст без звёздочек, без эмодзи
в конце придумай ОДИН хэштег по теме

пример:
Мой начальник спит, а мои KPI растут сами собой

#рабочаямагия

не повторяй темы"""

# Резервные аффирмашки
FALLBACK_AFFIRMATIONS = [
    "Мой начальник спит, а мои KPI растут сами собой\n\n#рабочеечудо",
    "Я левитирую над совещанием, и никто не замечает\n\n#невидимка",
    "Мой кот начал разговаривать и подтверждает мою гениальность\n\n#котофилософия",
    "Я выигрываю в спорах, даже когда молчу\n\n#силатишины",
    "Я высыпаюсь за 4 часа и чувствую себя отдохнувшим\n\n#сонсила",
    "Деньги сами находят меня, даже когда я их не ищу\n\n#денежныйпоток"
]

def load_chats() -> List[int]:
    try:
        with open(CHATS_FILE, "r") as f:
            return [int(line.strip()) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_chat(chat_id: int):
    chats = load_chats()
    if chat_id not in chats:
        chats.append(chat_id)
        with open(CHATS_FILE, "w") as f:
            for cid in chats:
                f.write(f"{cid}\n")
        print(f"✅ Новый подписчик: {chat_id}")

def remove_chat(chat_id: int):
    chats = load_chats()
    if chat_id in chats:
        chats.remove(chat_id)
        with open(CHATS_FILE, "w") as f:
            for cid in chats:
                f.write(f"{cid}\n")
        print(f"❌ Отписался: {chat_id}")

def load_history() -> List[str]:
    try:
        with open(HISTORY_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_to_history(affirmation: str):
    history = load_history()
    short = affirmation[:80].replace('\n', ' ')
    history.append(short)
    if len(history) > 20:
        history = history[-20:]
    with open(HISTORY_FILE, "w") as f:
        for item in history:
            f.write(f"{item}\n")

async def generate_affirmation(groq_client: Groq) -> str:
    try:
        history = load_history()
        context = ""
        if history:
            context = "не повторяй эти темы:\n" + "\n".join(f"- {h[:60]}" for h in history[-5:])

        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": AFFIRMATION_PROMPT + "\n\n" + context},
                {"role": "user", "content": "напиши новую аффирмашку дня"}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.95,
            max_tokens=120
        )
        post = response.choices[0].message.content.strip()
        post = post.replace('*', '')
        
        if post and post[0].islower():
            post = post[0].upper() + post[1:]
        
        if '#' not in post:
            post += "\n\n#аффирмашка"
        
        return post
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return random.choice(FALLBACK_AFFIRMATIONS)

def add_donation_button() -> InlineKeyboardMarkup:
    """Добавляет кнопку доната с вероятностью 5%"""
    if random.random() < 0.05:  # 5% вероятность
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="☕ Купить кофе автору", url="https://www.tbank.ru/cf/5hkmbahjfYd")],
            [InlineKeyboardButton(text="✨ Получить ещё аффирмашку", callback_data="get_now")]
        ])
        return keyboard
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ Получить ещё аффирмашку", callback_data="get_now")]
        ])
        return keyboard

async def send_daily_affirmation(bot: Bot):
    print(f"\n🕐 [{datetime.now()}] Ежедневная рассылка")
    groq_client = Groq(api_key=GROQ_API_KEY)
    affirmation = await generate_affirmation(groq_client)
    save_to_history(affirmation)
    
    keyboard = add_donation_button()
    
    for chat_id in load_chats():
        try:
            await bot.send_message(chat_id, affirmation, reply_markup=keyboard)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Ошибка {chat_id}: {e}")

async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", callback_data="subscribe")],
        [InlineKeyboardButton(text="❌ Отписаться", callback_data="unsubscribe")],
        [InlineKeyboardButton(text="✨ Получить аффирмашку", callback_data="get_now")]
    ])
    await message.answer(
        "✨ Аффирмашка дня ✨\n\n"
        "Каждое утро в 8:30 по Москве.\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )

async def callback_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "subscribe":
        save_chat(user_id)
        await callback.message.answer("✅ Подписался! Жди в 8:30")
    elif callback.data == "unsubscribe":
        remove_chat(user_id)
        await callback.message.answer("❌ Отписался")
    elif callback.data == "get_now":
        await callback.message.answer("🪄 Генерирую...")
        groq_client = Groq(api_key=GROQ_API_KEY)
        affirmation = await generate_affirmation(groq_client)
        keyboard = add_donation_button()
        await callback.message.answer(affirmation, reply_markup=keyboard)
    await callback.answer()

async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(callback_handler)
    
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_affirmation, "cron", hour=8, minute=30, args=(bot,))
    scheduler.start()
    
    print("✅ Бот запущен!")
    print("⏰ Рассылка каждый день в 8:30")
    print("💸 Кнопка доната появляется с вероятностью 5%")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
