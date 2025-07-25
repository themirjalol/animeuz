import asyncio
import json
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# 🔐 Sozlamalar
BOT_TOKEN = "BOT_TOKEN"
ADMINS = [5873723609]  # ← O'zingizning Telegram ID

DATA_FILE = Path("data.json")
if not DATA_FILE.exists():
    DATA_FILE.write_text(json.dumps({}))

# 📂 Ma'lumotni o'qish/yozish
def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# 🤖 Bot va Dispatcher
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# 🧭 Holatlar
class AddSeason(StatesGroup):
    waiting_files = State()

class EditSeason(StatesGroup):
    editing_files = State()

# 🔘 /start (yoki start link bilan)
@dp.message(CommandStart(deep_link=True))
async def start_with_param(message: Message, command: CommandObject):
    season_key = command.args
    data = load_data()
    season = data.get(season_key)
    if not season:
        await message.answer("❌ Bunday fasl topilmadi.")
        return

    await message.answer(f"🎬 <b>{season['title']}</b>\nYuklanmoqda...")
    for file_id in season["files"]:
        await message.answer_video(file_id)
        await asyncio.sleep(1)

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("👋 Anime yuklovchi botga xush kelibsiz!")

# 🔘 /add_season <nom>
@dp.message(Command("add_season"))
async def add_season(message: Message, command: CommandObject, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    season_name = (command.args or "").strip()
    if not season_name:
        await message.answer("⚠️ Foydalanish: /add_season <nom>")
        return

    season_name = season_name.replace(" ", "_")
    key = f"season_{season_name}"
    data = load_data()
    if key in data:
        await message.answer("❗ Bu fasl allaqachon mavjud.")
        return

    data[key] = {
        "title": season_name.replace("_", " "),
        "files": []
    }
    save_data(data)

    await state.set_state(AddSeason.waiting_files)
    await state.update_data(season_key=key)

    link = f"https://t.me/{(await bot.me()).username}?start={key}"
    await message.answer(f"📥 Endi fayllarni yuboring. Tugatgach /done deb yozing.\nLink: {link}")

# 🔘 /edit_season <nom>
@dp.message(Command("edit_season"))
async def edit_season(message: Message, command: CommandObject, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    season_name = (command.args or "").strip()
    if not season_name:
        await message.answer("⚠️ Foydalanish: /edit_season <nom>")
        return

    season_name = season_name.replace(" ", "_")
    key = f"season_{season_name}"

    data = load_data()
    if key not in data:
        await message.answer("❌ Bunday fasl topilmadi.")
        return

    await state.set_state(EditSeason.editing_files)
    await state.update_data(season_key=key)
    await message.answer("✏️ Endi yangi fayllarni yuboring. Eski fayllar o‘chmaydi. Tugatgach /done deb yozing.")

# 🔘 Fayl qabul qilish (add/edit)
@dp.message(StateFilter(AddSeason.waiting_files, EditSeason.editing_files), F.video)
async def handle_video(message: Message, state: FSMContext):
    file_id = message.video.file_id
    state_data = await state.get_data()
    key = state_data["season_key"]

    data = load_data()
    data[key]["files"].append(file_id)
    save_data(data)

    await message.answer("✅ Qo‘shildi")

# 🔘 /done
@dp.message(StateFilter(AddSeason.waiting_files, EditSeason.editing_files), Command("done"))
async def done_adding_editing(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Jarayon tugadi. Endi linkni ulashishingiz mumkin.")

# 🚀 Ishga tushirish
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
