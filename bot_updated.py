import asyncio
import json
import os
import random
from pathlib import Path
from urllib.parse import quote_plus

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Battle Royale, Chapter 7 Season 5 / Crossbones Isle, Fortnite v43.10.
# Counts are reported possible regular-chest spawn points from game-file data,
# not guaranteed chests in a particular match.
# Source: https://lifecrisis.life/loot (dataset updated 2026-11-12).
CHEST_AREAS = [
    {"name": "Buggy's Beachhead", "spots": 51},
    {"name": "Lantern Landing", "spots": 42},
    {"name": "Loguetown", "spots": 40},
    {"name": "Arlong Park", "spots": 40},
    {"name": "Cursed Cavern", "spots": 35},
    {"name": "Plunder Port", "spots": 32},
    {"name": "The $.$. Rocky", "spots": 31},
    {"name": "Windmill Village", "spots": 23},
    {"name": "Busy Bay", "spots": 20},
    {"name": "Baratie", "spots": 15},
    {"name": "The Salty Skull", "spots": 12},
    {"name": "Nami's Tangerine Grove", "spots": 8},
    {"name": "Henry", "spots": 6},
    {"name": "The Chest", "spots": 5},
    {"name": "Giant's Battlefield", "spots": 3},
]

MAP_URL = "https://lifecrisis.life/loot"
DATA_FILE = Path("bot_data.json")
TOKEN_FILE = Path("token.txt")

MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 120
WINDOW_SECONDS = 10

FUNNY_MESSAGES = [
    "Мимо! Сундук спрятался лучше, чем ты в кустах. 🌳",
    "Пока пусто. Даже Бургер-пёс сегодня без добычи. 🍔",
    "Сундук ушёл в отпуск. Загляни чуть позже. 🏖️",
    "Ничего нет! Ты нажал быстрее, чем успел приземлиться. 🪂",
    "Тишина... Даже кирка скучает. ⛏️",
    "Пока без сундука. RNG сегодня притворяется мебелью. 🪑",
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
    # Railway supplies BOT_TOKEN as an environment variable.
    token = os.getenv("BOT_TOKEN", "").strip()
    if token:
        return token

    # Local fallback for running on a computer; do not upload token.txt to GitHub.
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token and token != "PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE":
            return token

    raise SystemExit(
        "Не найден токен. Добавьте BOT_TOKEN в Railway Variables "
        "или создайте локальный token.txt."
    )


def choose_area() -> dict:
    # Weighted by the number of reported possible regular-chest spawn points.
    return random.choices(
        CHEST_AREAS,
        weights=[area["spots"] for area in CHEST_AREAS],
        k=1,
    )[0]


def area_map_url(area_name: str) -> str:
    return f"{MAP_URL}?spot={quote_plus(area_name)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎮 Fortnite Random Chest Bot\n\n"
        "Добавьте ники друзей:\n"
        "/addnick ВашНик\n\n"
        "Команды:\n"
        "/players — список игроков\n"
        "/delnick ВашНик — удалить ник\n"
        "/go — запустить случайные моменты\n"
        "/stop — остановить\n"
        "/map — открыть актуальную карту сундуков\n\n"
        "Через случайные 30–120 секунд появится сигнал. "
        "Нажмите «Проверить сундук», чтобы получить игрока и реальную "
        "зону поиска на карте Battle Royale.",
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


async def show_map(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🗺 Актуальная карта возможных точек сундуков Battle Royale:\n"
        f"{MAP_URL}\n\n"
        "Точки показывают возможные места появления, а не гарантируют сундук "
        "в каждой отдельной катке."
    )


async def event_loop(application: Application, chat_id: int) -> None:
    try:
        while True:
            await asyncio.sleep(random.randint(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
            roster = list(get_chat(chat_id)["players"].values())
            if not roster:
                continue

            event_id = random.randint(100000, 999999999)
            area = choose_area()
            player = random.choice(roster)
            active_events[chat_id] = {
                "id": event_id,
                "player": player,
                "area": area,
                "expires_at": asyncio.get_running_loop().time() + WINDOW_SECONDS,
            }

            cue = await application.bot.send_message(
                chat_id,
                "🚨 ТВОЙ МОМЕНТ НАСТАЛ!\n"
                "⚡ Быстрее залетай в катку!\n\n"
                "Нажми «Проверить сундук» в течение 10 секунд, "
                "чтобы узнать игрока и точку поиска.",
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
                        text="⌛ Момент упущен! Сундук не дождался. "
                             "Следующий шанс появится внезапно. 🫥",
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

    active_events.pop(chat_id, None)
    area = event["area"]
    player = event["player"]

    await query.message.reply_text(
        "🚨 ТВОЙ МОМЕНТ НАСТАЛ!\n"
        "⚡ Быстрее залетай в катку!\n\n"
        f"🎮 Игрок: {player}\n"
        f"📍 Район поиска: {area['name']}\n"
        f"🧰 В базе отмечено возможных точек обычных сундуков: {area['spots']}\n\n"
        "Важно: это реальные возможные точки появления, но сундук "
        "не гарантирован в каждой катке.\n"
        f"🗺 Карта этой локации: {area_map_url(area['name'])}",
        reply_markup=check_keyboard(),
        disable_web_page_preview=True,
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
        "🟢 Игра началась! Сигналы будут появляться через случайные 30–120 секунд.\n"
        "У каждого сигнала окно 10 секунд. Нажмите кнопку, чтобы получить "
        "игрока и актуальную зону поиска сундуков.",
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
    application.add_handler(CommandHandler("map", show_map))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CallbackQueryHandler(check_chest, pattern="^check_chest$"))
    application.run_polling()


if __name__ == "__main__":
    main()
