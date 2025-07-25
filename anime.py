import asyncio
import json
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.utils.markdown import hcode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from aiogram.client.default import DefaultBotProperties

# 🔐 Sozlamalar
BOT_TOKEN = "7146716475:AAEXDbhIlWDeGuyukyTT2Sd-ntLOLf3LcZ8"
ADMINS = [5873723609]  # O'zingizning Telegram ID'nigiz

DATA_FILE = Path("data.json")

# 📂 Faylni tayyorlab qo'yamiz
if not DATA_FILE.exists():
    DATA_FILE.write_text(json.dumps({}))

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# 📥 Bot sozlamalari
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())


# 🚦 Holatlar
class AddSeason(StatesGroup):
    waiting_files = State()

# 📌 Boshlash komandasi
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

# ✅ Admin yangi fasl qo‘shadi
@dp.message(Command("add_season"))
async def add_season(message: Message, command: CommandObject, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    season_name = command.args
    if not season_name:
        await message.answer("⚠️ Foydalanish: /add_season <nom>")
        return

    data = load_data()
    key = f"season_{season_name}"
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

    await message.answer(f"📥 Endi fayllarni yuboring. Tugatgach /done deb yozing.\nLink: https://t.me/{(await bot.me()).username}?start={key}")

# 📤 Fayl qabul qilish
@dp.message(AddSeason.waiting_files, F.video)
async def collect_files(message: Message, state: FSMContext):
    file_id = message.video.file_id
    state_data = await state.get_data()
    key = state_data["season_key"]

    data = load_data()
    data[key]["files"].append(file_id)
    save_data(data)

    await message.answer("✅ Qo‘shildi")

# ✅ Tugatish
@dp.message(AddSeason.waiting_files, Command("done"))
async def finish_adding(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Fasl yaratildi. Endi linkni ulashishingiz mumkin.")

# 🏁 Ishga tushirish
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())