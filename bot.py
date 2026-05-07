import os
import time
import asyncio
import random
import json
from datetime import datetime
from typing import List, Dict
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq


# Задержка для хостинга
time.sleep(5)

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))  # ← теперь из переменной окружения

if not TELEGRAM_BOT_TOKEN:
    print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден")
    exit(1)

if not GROQ_API_KEY:
    print("❌ ОШИБКА: GROQ_API_KEY не найден")
    exit(1)

if ADMIN_ID == 0:
    print("❌ ОШИБКА: ADMIN_ID не найден")
    exit(1)

print(f"✅ Токен загружен: {TELEGRAM_BOT_TOKEN[:15]}...")
print(f"✅ API ключ загружен: {GROQ_API_KEY[:15]}...")
print(f"👑 Админ ID: {ADMIN_ID}")

# Файлы
CHATS_FILE = "subscribed_chats.txt"
HISTORY_FILE = "affirmation_history.txt"
AFFIRMATIONS_LOG = "affirmations_sent.txt"
RATINGS_FILE = "affirmations_ratings.json"

# ========== РАБОТА С РЕЙТИНГОМ ==========
def load_ratings() -> Dict:
    try:
        with open(RATINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_ratings(ratings: Dict):
    with open(RATINGS_FILE, "w") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)

def add_rating(affirmation: str, rating: int):
    """rating: 1 = 👍, -1 = 👎"""
    ratings = load_ratings()
    
    key = affirmation[:100].replace('\n', ' ')
    
    if key not in ratings:
        ratings[key] = {"likes": 0, "dislikes": 0, "full": affirmation}
    
    if rating == 1:
        ratings[key]["likes"] += 1
    elif rating == -1:
        ratings[key]["dislikes"] += 1
    
    save_ratings(ratings)

def get_top_affirmations(limit: int = 10) -> List[tuple]:
    """Возвращает топ аффирмашек по рейтингу"""
    ratings = load_ratings()
    
    scored = []
    for key, data in ratings.items():
        total = data["likes"] + data["dislikes"]
        if total >= 3:
            score = data["likes"] / total
            scored.append((score, data["likes"], data["dislikes"], data["full"]))
    
    scored.sort(reverse=True)
    return scored[:limit]

# ========== ПРОМПТ ==========
AFFIRMATION_PROMPT = """ты создаёшь «аффирмашку дня» — короткое позитивное утверждение о себе.

стиль:
- первая буква предложения ЗАГЛАВНАЯ, остальные строчные
- ироничное, забавное, жизнеутверждающее, абсурдное
- темы любые: работа, сон, отношения, деньги, бытовая магия

запрещено: еда, пицца, носки, лягушки

формат:
текст без звёздочек, без эмодзи
в конце придумай ОДИН хэштег по теме

примеры:
Процесс согласования проходит быстро и экологично. Коллеги доверяют моему вкусу.

#рабочаямагия

Я высыпаюсь за 4 часа и чувствую себя отдохнувшим.

#сонсила

не повторяй темы"""

# Резервные аффирмашки
FALLBACK_AFFIRMATIONS = [
    "Я сплю до обеда и все успеваю.\n\n#сонсила",
    "Мои руки растут из плеч.\n\n#уверенность",
    "Процесс согласования проходит быстро и экологично.\n\n#рабочаямагия",
    "Состояние ментальной овуляции сопровождает меня по жизни.\n\n#менталка",
    "Я гений.\n\n#гениальность",
    "Мои аффирмации работают.\n\n#магия",
    "Я всегда выигрываю в настольные игры.\n\n#победа",
    "На моих устройствах всегда стабильное интернет-соединение.\n\n#техномагия",
]

def load_chats() -> List[int]:
    try:
        with open(CHATS_FILE, "r") as f:
            return [int(line.strip()) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_chat(chat_id: int, first_name: str = "", username: str = ""):
    chats = load_chats()
    if chat_id not in chats:
        chats.append(chat_id)
        with open(CHATS_FILE, "w") as f:
            for cid in chats:
                f.write(f"{cid}\n")
        
        if username:
            print(f"✅ Новый подписчик: {first_name} (@{username}) | ID: {chat_id}")
        elif first_name:
            print(f"✅ Новый подписчик: {first_name} | ID: {chat_id}")
        else:
            print(f"✅ Новый подписчик: ID: {chat_id}")

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
    short = affirmation[:100].replace('\n', ' ')
    history.append(short)
    if len(history) > 30:
        history = history[-30:]
    with open(HISTORY_FILE, "w") as f:
        for item in history:
            f.write(f"{item}\n")

def log_affirmation_to_user(chat_id: int, affirmation: str):
    try:
        with open(AFFIRMATIONS_LOG, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            short = affirmation[:80].replace('\n', ' ')
            f.write(f"[{timestamp}] User: {chat_id} | {short}\n")
    except:
        pass

async def generate_affirmation(groq_client: Groq) -> str:
    try:
        history = load_history()
        context = ""
        if history:
            context = "не повторяй эти темы:\n" + "\n".join(f"- {h[:60]}" for h in history[-5:])

        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": AFFIRMATION_PROMPT + "\n\n" + context},
                {"role": "user", "content": "напиши новую аффирмашку. с хэштегом в конце. без пиццы, еды, носков, лягушек."}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.9,
            max_tokens=120
        )
        post = response.choices[0].message.content.strip()
        post = post.replace('*', '')
        
        if post and post[0].islower():
            post = post[0].upper() + post[1:]
        
        forbidden = ["пицц", "еда", "съесть", "лягуш", "носк", "стройн", "вес", "диет"]
        for word in forbidden:
            if word in post.lower():
                return random.choice(FALLBACK_AFFIRMATIONS)
        
        if '#' not in post:
            post += "\n\n#аффирмашка"
        
        return post
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return random.choice(FALLBACK_AFFIRMATIONS)

def get_rating_keyboard(affirmation_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками лайк/дизлайк и донатом"""
    buttons = [
        [
            InlineKeyboardButton(text="👍", callback_data=f"like_{affirmation_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"dislike_{affirmation_id}")
        ]
    ]
    
    # Кнопка доната с вероятностью 5%
    if random.random() < 0.05:
        buttons.append([InlineKeyboardButton(text="☕ Купить кофе автору", url="https://www.tbank.ru/cf/5hkmbahjfYd")])
    
    buttons.append([InlineKeyboardButton(text="✨ Получить ещё аффирмашку", callback_data="get_now")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def send_affirmation_with_rating(bot: Bot, chat_id: int, affirmation: str, affirmation_id: str = None):
    """Отправляет аффирмашку с кнопками рейтинга"""
    if affirmation_id is None:
        affirmation_id = str(int(datetime.now().timestamp()))
    
    keyboard = get_rating_keyboard(affirmation_id)
    await bot.send_message(chat_id, affirmation, reply_markup=keyboard)
    return affirmation_id

async def send_daily_affirmation(bot: Bot):
    print(f"\n🕐 [{datetime.now()}] Ежедневная рассылка")
    groq_client = Groq(api_key=GROQ_API_KEY)
    affirmation = await generate_affirmation(groq_client)
    save_to_history(affirmation)
    
    for chat_id in load_chats():
        try:
            await send_affirmation_with_rating(bot, chat_id, affirmation)
            log_affirmation_to_user(chat_id, affirmation)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Ошибка {chat_id}: {e}")

async def cmd_start(message: Message):
    first_name = message.from_user.first_name or ""
    username = message.from_user.username or ""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", callback_data="subscribe")],
        [InlineKeyboardButton(text="❌ Отписаться", callback_data="unsubscribe")],
        [InlineKeyboardButton(text="✨ Получить аффирмашку", callback_data="get_now")]
    ])
    await message.answer(
        "✨ Аффирмашка дня ✨\n\n"
        "Каждое утро в 8:30 по Москве.\n\n"
        "Оценивай аффирмашки 👍👎\n"
        "Топ лучших — /top\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )

async def cmd_top(message: Message):
    """Показывает топ лучших аффирмашек"""
    top = get_top_affirmations(10)
    
    if not top:
        await message.answer("📭 Пока нет оценок. Оценивай аффирмашки 👍👎, чтобы появился топ!")
        return
    
    result = "🏆 *Топ лучших аффирмашек*\n\n"
    
    for i, (score, likes, dislikes, text) in enumerate(top, 1):
        # Берём первую строку или первые 60 символов
        short_text = text.split('\n')[0][:60]
        if len(text.split('\n')[0]) > 60:
            short_text += "..."
        
        result += f"{i}. {short_text}\n"
        result += f"   👍 {likes} | 👎 {dislikes}\n\n"
    
    await message.answer(result, parse_mode="Markdown")

async def cmd_stats(message: Message):
    """Статистика для админа"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У тебя нет доступа к этой команде.")
        return
    
    chats = load_chats()
    history = load_history()
    ratings = load_ratings()
    
    total_ratings = sum(len(r) for r in ratings.values())
    
    stats_text = f"📊 *Статистика бота*\n\n"
    stats_text += f"👥 Подписчиков: *{len(chats)}*\n"
    stats_text += f"📝 Аффирмашек сгенерировано: *{len(history)}*\n"
    stats_text += f"⭐ Всего оценок: *{total_ratings}*\n"
    
    await message.answer(stats_text, parse_mode="Markdown")

async def callback_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "subscribe":
        first_name = callback.from_user.first_name or ""
        username = callback.from_user.username or ""
        save_chat(user_id, first_name, username)
        await callback.message.answer("✅ Подписался! Жди в 8:30")
    
    elif data == "unsubscribe":
        remove_chat(user_id)
        await callback.message.answer("❌ Отписался")
    
    elif data == "get_now":
        await callback.message.answer("🪄 Генерирую...")
        groq_client = Groq(api_key=GROQ_API_KEY)
        affirmation = await generate_affirmation(groq_client)
        await send_affirmation_with_rating(callback.bot, user_id, affirmation)
        log_affirmation_to_user(user_id, affirmation)
    
    elif data.startswith("like_"):
        affirmation_id = data[5:]
        # В реальности нужно хранить соответствие id -> текст
        # Пока просто считаем
        add_rating(affirmation_id, 1)
        await callback.answer("👍 Спасибо за оценку!")
    
    elif data.startswith("dislike_"):
        affirmation_id = data[8:]
        add_rating(affirmation_id, -1)
        await callback.answer("👎 Спасибо за честность!")
    
    await callback.answer()

async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_top, Command("top"))
    dp.message.register(cmd_stats, Command("stats"))
    dp.callback_query.register(callback_handler)
    
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_affirmation, "cron", hour=8, minute=30, args=(bot,))
    scheduler.start()
    
    print("✅ Бот запущен!")
    print("⏰ Рассылка каждый день в 8:30")
    print("👍👎 У аффирмашек есть кнопки оценки")
    print("🏆 Команда /top — топ лучших аффирмашек")
    print("👑 Команда /stats — статистика (только админ)")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
