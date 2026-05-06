import os
import asyncio
import random
from datetime import datetime
from typing import List
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq

# Загружаем переменные окружения
load_dotenv()

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # было os.getenv()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")              # было os.getenv()

# Проверка токенов
if not TELEGRAM_BOT_TOKEN:
    print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден в .env файле!")
    exit(1)

if not GROQ_API_KEY:
    print("❌ ОШИБКА: GROQ_API_KEY не найден в .env файле!")
    exit(1)

print(f"✅ Токен загружен: {TELEGRAM_BOT_TOKEN[:15]}...")
print(f"✅ API ключ загружен: {GROQ_API_KEY[:15]}...")

# Файлы для хранения данных
CHATS_FILE = "subscribed_chats.txt"
HISTORY_FILE = "affirmation_history.txt"

# ========== ПРОМПТ ДЛЯ ГЕНЕРАЦИИ (БЕЗ ЗВЁЗДОЧЕК) ==========
AFFIRMATION_PROMPT = """ты создаёшь «аффирмашку дня» — короткое позитивное утверждение о себе.

стиль:
- первая буква предложения ЗАГЛАВНАЯ, остальные строчные (как в обычном тексте)
- ироничное, забавное, прикольное, жизнеутверждающее
- милое, с лёгкой пафосностью и абсурдным юмором
- разрешено абсолютно всё: пицца, лягушки, левитация, стройность — всё что угодно!

формат:
просто текст БЕЗ звёздочек, БЕЗ эмодзи, БЕЗ markdown
в конце обязательно хэштег #аффирмашка_дня с новой строки

длина: 15-60 слов
не повторяй темы предыдущих аффирмашек

пример:
Я левитирую над пиццей и каждая калория улетает в космос

#аффирмашка_дня"""

FALLBACK_AFFIRMATIONS = [
    "Я лечу над пиццей и каждая калория превращается в искру счастья\n\n#аффирмашка_дня",
    "Моя стройность — это магия, а пицца — мой волшебный эликсир\n\n#аффирмашка_дня",
    "Лягушки целуют меня в надежде превратиться в принцев, но я слишком хороша\n\n#аффирмашка_дня",
    "Я ем пиццу каждый день и становлюсь только легче\n\n#аффирмашка_дня",
    "Я левитирую над совещанием, и никто не замечает\n\n#аффирмашка_дня",
    "Мой кот начал разговаривать и подтверждает мою гениальность\n\n#аффирмашка_дня",
    "Я выигрываю в спорах, даже когда молчу\n\n#аффирмашка_дня"
]


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ ==========
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


# ========== ЛОГГИРОВАНИЕ ==========
def log_user_action(user_id: int, first_name: str, username: str, action: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name_display = f"{first_name} (@{username})" if username else f"{first_name}"
    print(f"[{now}] 👤 {name_display} | ID: {user_id} | 📌 {action}")


# ========== ГЕНЕРАЦИЯ АФФИРМАШКИ ==========
async def generate_affirmation(groq_client: Groq) -> str:
    try:
        history = load_history()
        context = ""
        if history:
            context = "ранее уже были темы (не повторяй их):\n" + "\n".join(f"- {h[:60]}" for h in history[-3:])

        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": AFFIRMATION_PROMPT + "\n\n" + context},
                {"role": "user",
                 "content": "напиши новую аффирмашку дня. без звёздочек, без эмодзи, без markdown. первая буква заглавная, остальные строчные. в конце #аффирмашка_дня."}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.95,
            max_tokens=150,
            top_p=0.95
        )
        post = response.choices[0].message.content.strip()

        # Убираем звёздочки, если они появились
        post = post.replace('*', '')

        # Проверяем, что первая буква заглавная
        if post and post[0].islower():
            post = post[0].upper() + post[1:]

        # Убеждаемся, что хэштег есть
        if "#аффирмашка_дня" not in post:
            post += "\n\n#аффирмашка_дня"

        return post
    except Exception as e:
        print(f"❌ Ошибка генерации: {e}")
        return random.choice(FALLBACK_AFFIRMATIONS)


# ========== ОТПРАВКА ВСЕМ ПОДПИСЧИКАМ ==========
async def send_daily_affirmation(bot: Bot):
    print(f"\n{'=' * 50}")
    print(f"🕐 [{datetime.now().strftime('%H:%M:%S')}] ЕЖЕДНЕВНАЯ РАССЫЛКА")
    print(f"{'=' * 50}")

    groq_client = Groq(api_key=GROQ_API_KEY)
    affirmation = await generate_affirmation(groq_client)
    save_to_history(affirmation)

    chats = load_chats()
    if not chats:
        print("⚠️ Нет подписчиков для рассылки")
        return

    print(f"📨 Отправляю {len(chats)} подписчикам...")
    for chat_id in chats:
        try:
            # Отправляем без parse_mode (обычный текст)
            await bot.send_message(chat_id, affirmation)
            print(f"✅ Отправлено ID: {chat_id}")
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка отправки {chat_id}: {e}")
    print(f"{'=' * 50}\n")


# ========== КОМАНДЫ И КНОПКИ ==========
async def cmd_start(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    log_user_action(user_id, first_name, username, "Нажал /start")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться на аффирмашки", callback_data="subscribe")],
        [InlineKeyboardButton(text="❌ Отписаться", callback_data="unsubscribe")],
        [InlineKeyboardButton(text="✨ Получить аффирмашку сейчас", callback_data="get_now")]
    ])

    await message.answer(
        "✨ Привет! Я бот — Аффирмашка дня. ✨\n\n"
        "Каждое утро в 8:30 я присылаю тебе ироничную и жизнеутверждающую аффирмашку.\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )


async def callback_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    username = callback.from_user.username

    if callback.data == "subscribe":
        save_chat(user_id)
        log_user_action(user_id, first_name, username, "✅ Подписался на рассылку")
        await callback.message.answer("✅ Ты подписался на аффирмашки! Жди в 8:30.")
        await callback.answer()

    elif callback.data == "unsubscribe":
        remove_chat(user_id)
        log_user_action(user_id, first_name, username, "❌ Отписался от рассылки")
        await callback.message.answer("❌ Ты отписался. Чтобы вернуться — напиши /start")
        await callback.answer()

    elif callback.data == "get_now":
        log_user_action(user_id, first_name, username, "✨ Запросил аффирмашку сейчас")
        await callback.message.answer("🪄 Генерирую аффирмашку, минуточку...")

        groq_client = Groq(api_key=GROQ_API_KEY)
        affirmation = await generate_affirmation(groq_client)

        # Отправляем без parse_mode
        await callback.message.answer(affirmation)
        await callback.answer()


# ========== ЗАПУСК ==========
async def main():
    print(f"\n{'=' * 50}")
    print(f"🚀 ЗАПУСК БОТА")
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏰ Расписание: каждый день в 8:30")
    print(f"{'=' * 50}\n")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(callback_handler)

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        send_daily_affirmation,
        trigger="cron",
        hour=8,
        minute=30,
        args=(bot,),
        id="daily_affirmation"
    )
    scheduler.start()

    print("✅ Бот успешно запущен и работает!")
    print("📌 Команда: /start")
    print("💡 Бот будет слать аффирмашки каждый день в 8:30")
    print("⚠️ Компьютер должен быть включён в это время!\n")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())