import asyncio
import json
import random
import os
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Current Battle Royale map: Chapter 7, Season 5 (Crossbones Isle).
LOCATIONS = [
    "Rubber Resort",
    "The Chest",
    "Loot Lagoon",
    "Fortune's Fort",
    "Lantern Landing",
    "Arlong Park",
    "Cursed Cavern",
    "The $.$. Rocky",
    "Windmill Village",
    "Loguetown",
    "Busy Bay",
    "Plunder Port",
]

DATA_FILE = Path("bot_data.json")

MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 120
# How long the random "chest is available" moment stays open.
WINDOW_SECONDS = 10

FUNNY_MESSAGES = [
    "Пока пусто. Даже Бургер-пёс сегодня без добычи. 🍔",
    "Сундук ушёл в отпуск. Загляни чуть позже. 🏖️",
    "Ничего нет! Ты нажал быстрее, чем успел приземлиться. 🪂",
    "Тишина... Даже кирка скучает. ⛏️",
    "Пока без сундука. RNG сегодня притворяется мебелью. 🪑",
    "Мимо! Сундук спрятался лучше, чем ты в кустах. 🌳",
]

data = {"chats": {}}
timers: dict[int, asyncio.Task] = {}
active_events: dict[int, dict] = {}


def load_data() -> None:
    global data
    if DATA_FILE.exists():
        try:
            loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            pass
    data.setdefault("chats", {})


def save_data() -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_chat(chat_id: int) -> dict:
    return data.setdefault("chats", {}).setdefault(
        str(chat_id), {"players": {}}
    )


def check_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔎 Проверить сундук", callback_data="check_chest")]]
    )


def get_token() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Не задана переменная окружения BOT_TOKEN. "
            "Добавьте токен в Railway → Variables."
        )
    return token


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎮 Fortnite Random Chest Bot\n\n"
        "Добавьте ники друзей:\n"
        "/addnick ВашНик\n\n"
        "Команды:\n"
        "/players — список игроков\n"
        "/delnick ВашНик — удалить ник\n"
        "/go — запустить случайные моменты\n"
        "/stop — остановить\n\n"
        "Нажимайте кнопку «Проверить сундук». "
        "Случайный момент появляется на 10 секунд, "
        "через случайные 30–120 секунд.",
        reply_markup=check_keyboard(),
    )


async def addnick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Формат: /addnick ВашНик")
        return
    nickname = " ".join(context.args).strip()
    get_chat(update.effective_chat.id)["players"][nickname.casefold()] = nickname
    save_data()
    await update.message.reply_text(f"✅ Добавил игрока: {nickname}")


async def delnick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Формат: /delnick ВашНик")
        return
    nickname = " ".join(context.args).strip()
    players = get_chat(update.effective_chat.id)["players"]
    removed = players.pop(nickname.casefold(), None)
    save_data()
    await update.message.reply_text(
        f"Удалил игрока {removed}." if removed else "Такого ника нет в списке."
    )


async def players(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    roster = list(get_chat(update.effective_chat.id)["players"].values())
    if not roster:
        await update.message.reply_text("Список пуст. Добавьте ник: /addnick ВашНик")
        return
    await update.message.reply_text("👥 Игроки:\n" + "\n".join(f"• {n}" for n in roster))


async def event_loop(application: Application, chat_id: int) -> None:
    try:
        while True:
            await asyncio.sleep(random.randint(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
            roster = list(get_chat(chat_id)["players"].values())
            if not roster:
                continue

            event_id = random.randint(100000, 999999999)
            active_events[chat_id] = {
                "id": event_id,
                "expires_at": asyncio.get_running_loop().time() + WINDOW_SECONDS,
            }

            # The group gets a brief cue; the button is attached for quick checking.
            cue = await application.bot.send_message(
                chat_id,
                "👀 Кажется, что-то происходит... "
                "У вас есть 10 секунд проверить сундук!",
                reply_markup=check_keyboard(),
            )

            await asyncio.sleep(WINDOW_SECONDS)
            current = active_events.get(chat_id)
            if current and current["id"] == event_id:
                active_events.pop(chat_id, None)
                try:
                    await application.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=cue.message_id,
                        text="⌛ Момент упущен! Сундук испарился. "
                             "Следующий шанс будет в случайный момент. 🫥",
                        reply_markup=check_keyboard(),
                    )
                except Exception:
                    pass
    except asyncio.CancelledError:
        raise


async def check_chest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    event = active_events.get(chat_id)
    now = asyncio.get_running_loop().time()

    if not event or now > event["expires_at"]:
        await query.message.reply_text(random.choice(FUNNY_MESSAGES))
        return

    # First player to press the button claims this moment for the whole group.
    active_events.pop(chat_id, None)
    roster = list(get_chat(chat_id)["players"].values())
    if not roster:
        await query.message.reply_text("Сначала добавьте игроков командой /addnick Ник.")
        return

    nickname = random.choice(roster)
    location = random.choice(LOCATIONS)
    await query.message.reply_text(
        "🚨 ТВОЙ МОМЕНТ НАСТАЛ!\n"
        "⚡ Быстрее залетай в катку!\n\n"
        f"🎮 Игрок: {nickname}\n"
        f"📍 Локация: {location}\n\n"
        "🎁 Найди и открой там сундук!",
        reply_markup=check_keyboard(),
    )


async def go(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not get_chat(chat_id)["players"]:
        await update.message.reply_text("Сначала добавьте ник: /addnick ВашНик")
        return

    task = timers.get(chat_id)
    if task and not task.done():
        await update.message.reply_text("Уже запущено! Используйте /stop.")
        return

    timers[chat_id] = asyncio.create_task(event_loop(context.application, chat_id))
    await update.message.reply_text(
        "🟢 Игра началась! События будут появляться через случайные 30–120 секунд.\n"
        "У каждого события окно 10 секунд. Кто первый нажмёт кнопку — тот забирает момент.",
        reply_markup=check_keyboard(),
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    task = timers.pop(chat_id, None)
    active_events.pop(chat_id, None)
    if task and not task.done():
        task.cancel()
        await update.message.reply_text("🔴 Случайные события остановлены.")
    else:
        await update.message.reply_text("События уже остановлены.")


def main() -> None:
    load_data()
    application = Application.builder().token(get_token()).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addnick", addnick))
    application.add_handler(CommandHandler("delnick", delnick))
    application.add_handler(CommandHandler("players", players))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CallbackQueryHandler(check_chest, pattern="^check_chest$"))
    application.run_polling()


if __name__ == "__main__":
    main()
