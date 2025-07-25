import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from functools import wraps

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError

# 🔐 Sozlamalar
BOT_TOKEN = "BOT_TOKEN"
ADMINS = [5873723609]  # ← O'zingizning Telegram ID

DATA_FILE = Path("data.json")
if not DATA_FILE.exists():
    DATA_FILE.write_text(json.dumps({"channels": []}, ensure_ascii=False))

# 📂 Ma'lumotni o'qish/yozish
def load_data() -> Dict[str, Any]:
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

def save_data(data: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 🤖 Bot va Dispatcher
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# 🧭 Holatlar
class AddSeason(StatesGroup):
    waiting_files = State()
    waiting_caption = State() # Yangi holat

class EditSeason(StatesGroup):
    editing_files = State()
    waiting_caption = State() # Yangi holat

# Yangi struktura uchun yordamchi funksiya
def get_season_info(season_key: str) -> Optional[Dict[str, Any]]:
    """Fasl ma'lumotlarini olish"""
    data = load_data()
    return data.get(season_key)

def add_file_to_season(season_key: str, file_id: str, caption: str = "") -> None:
    """Faylni faslga qo'shish"""
    data = load_data()
    if season_key in data:
        data[season_key]["files"].append({
            "file_id": file_id,
            "caption": caption,
            "number": len(data[season_key]["files"]) + 1
        })
        save_data(data)

def update_file_caption(season_key: str, file_index: int, new_caption: str) -> bool:
    """Fayl tavsifini yangilash"""
    data = load_data()
    if season_key in data and 0 <= file_index < len(data[season_key]["files"]):
        data[season_key]["files"][file_index]["caption"] = new_caption
        save_data(data)
        return True
    return False

# Foydalanuvchi obunasi tekshiruvi
async def is_user_subscribed(user_id: int) -> bool:
    """Foydalanuvchi barcha majburiy kanallarga obuna bo'lganini tekshiradi"""
    data = load_data()
    channels = data.get("channels", [])
    
    # Agar kanallar ro'yxati bo'sh bo'lsa, cheklov yo'q
    if not channels:
        return True
        
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["id"], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False  # Agar hech bo'lmaganda bitta kanalga obuna bo'lmasa
        except TelegramForbiddenError:
            # Bot kanalda admin emas, xavfsizlik uchun ruxsat beramiz
            continue
        except Exception:
            return False  # Xatolik yuz bersa, obuna emas deb hisoblaymiz
            
    return True  # Barcha kanallarga obuna

def subscription_required(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id in ADMINS:
            return await handler(message, *args, **kwargs)
            
        if not await is_user_subscribed(message.from_user.id):
            data = load_data()
            channels = data.get("channels", [])
            
            if not channels:
                return await handler(message, *args, **kwargs)  # Cheklov yo'q
            
            buttons = [
                [InlineKeyboardButton(text=f"📢 {channel['name']}", url=f"https://t.me/{channel['id'].lstrip('@')}")]
                for channel in channels
            ]
            buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(
                "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak!",
                reply_markup=keyboard
            )
            return
        return await handler(message, *args, **kwargs)
    return wrapper

def subscription_required_callback(handler):
    @wraps(handler)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if callback.from_user.id in ADMINS:
            return await handler(callback, *args, **kwargs)
            
        if not await is_user_subscribed(callback.from_user.id):
            data = load_data()
            channels = data.get("channels", [])
            
            if not channels:
                return await handler(callback, *args, **kwargs)  # Cheklov yo'q
            
            buttons = [
                [InlineKeyboardButton(text=f"📢 {channel['name']}", url=f"https://t.me/{channel['id'].lstrip('@')}")]
                for channel in channels
            ]
            buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.answer("⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling!", show_alert=True)
            try:
                await callback.message.edit_text(
                    "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak!",
                    reply_markup=keyboard
                )
            except:
                await callback.message.answer(
                    "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak!",
                    reply_markup=keyboard
                )
            return
        return await handler(callback, *args, **kwargs)
    return wrapper

# 🔘 /start (yoki start link bilan)
@dp.message(CommandStart(deep_link=True))
@subscription_required
async def start_with_param(message: Message, command: CommandObject):
    season_key = command.args
    data = load_data()
    season = data.get(season_key)
    if not season:
        await message.answer("❌ Bunday fasl topilmadi.")
        return

    await message.answer(f"🎬 <b>{season['title']}</b>\nYuklanmoqda...")
    for file_info in season["files"]:
        file_id = file_info["file_id"]
        caption = file_info.get("caption", "")
        number = file_info.get("number", "")
        
        caption_text = f"{number}-qism" + (f": {caption}" if caption else "")
        
        await message.answer_video(file_id, caption=caption_text)
        await asyncio.sleep(1)

@dp.message(CommandStart())
@subscription_required
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

    bot_username = (await bot.me()).username
    link = f"https://t.me/{bot_username}?start={key}"
    await message.answer(f"📥 Endi fayllarni yuboring. Tugatgach /done deb yozing.\nLink: {link}")

# 🔘 Fayl qabul qilish (add/edit) - endi caption so'raydi
@dp.message(StateFilter(AddSeason.waiting_files, EditSeason.editing_files), F.video)
async def handle_video(message: Message, state: FSMContext):
    file_id = message.video.file_id
    state_data = await state.get_data()
    key = state_data["season_key"]

    # Fayl qo'shamiz, lekin caption so'raymiz
    await state.update_data(current_file_id=file_id)
    await state.set_state(AddSeason.waiting_caption if await state.get_state() == AddSeason.waiting_files.state else EditSeason.waiting_caption)
    
    await message.answer("📝 Ushbu video uchun tavsif yozing (ixtiyoriy, bekor qilish uchun /skip):")

# 🔘 Tavsifni qabul qilish
@dp.message(StateFilter(AddSeason.waiting_caption, EditSeason.waiting_caption))
async def handle_caption(message: Message, state: FSMContext):
    state_data = await state.get_data()
    key = state_data["season_key"]
    file_id = state_data["current_file_id"]
    caption = message.text if message.text and message.text != "/skip" else ""

    # Faylni saqlash
    add_file_to_season(key, file_id, caption)
    
    # Holatni qayta o'rnatish
    current_state = await state.get_state()
    if current_state == AddSeason.waiting_caption.state:
        await state.set_state(AddSeason.waiting_files)
    else:
        await state.set_state(EditSeason.editing_files)
    
    await message.answer("✅ Fayl qo‘shildi. Davom eting...")

# 🔘 /done
@dp.message(StateFilter(AddSeason.waiting_files, EditSeason.editing_files, AddSeason.waiting_caption, EditSeason.waiting_caption), Command("done"))
async def done_adding_editing(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Jarayon tugadi. Endi linkni ulashishingiz mumkin.")

# 🔘 /skip - tavsizni o'tkazib yuborish
@dp.message(StateFilter(AddSeason.waiting_caption, EditSeason.waiting_caption), Command("skip"))
async def skip_caption(message: Message, state: FSMContext):
    state_data = await state.get_data()
    key = state_data["season_key"]
    file_id = state_data["current_file_id"]

    # Bo'sh tavsif bilan faylni saqlash
    add_file_to_season(key, file_id, "")
    
    # Holatni qayta o'rnatish
    current_state = await state.get_state()
    if current_state == AddSeason.waiting_caption.state:
        await state.set_state(AddSeason.waiting_files)
    else:
        await state.set_state(EditSeason.editing_files)
    
    await message.answer("✅ Fayl qo‘shildi (tavsif). Davom eting...")

# 🔘 /list_seasons - Barcha mavsumlarni inline tugmalar bilan ko'rsatadi
@dp.message(Command("list_seasons"))
@subscription_required
async def list_seasons(message: Message):
    data = load_data()
    if not data or all(key == "channels" for key in data.keys()):
        await message.answer("❌ Hozircha mavsumlar yo‘q.")
        return

    buttons = []
    for key, season in data.items():
        if key != "channels":  # channels kalitini tashlab ketamiz
            button = InlineKeyboardButton(text=season["title"], callback_data=f"view_{key}")
            buttons.append([button])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🎬 Mavjud mavsumlar:", reply_markup=markup)

# 🎬 Faslni ko'rish (callback orqali)
@dp.callback_query(F.data.startswith("view_"))
@subscription_required_callback
async def view_season(callback: CallbackQuery):
    key = callback.data.split("_", 1)[1]
    data = load_data()
    season = data.get(key)

    if not season:
        await callback.answer("❌ Fasl topilmadi.", show_alert=True)
        return

    await callback.message.answer(f"🎬 <b>{season['title']}</b>\nYuklanmoqda...")
    for file_info in season["files"]:
        file_id = file_info["file_id"]
        caption = file_info.get("caption", "")
        number = file_info.get("number", "")
        
        caption_text = f"{number}-qism" + (f": {caption}" if caption else "")
        
        await callback.message.answer_video(file_id, caption=caption_text)
        await asyncio.sleep(1)

    await callback.answer()

# 🔐 /admin_list - Faqat admin uchun mavsumlar ro'yxati (tahrirlash/o'chirish bilan)
@dp.message(Command("admin_list"))
async def admin_list_seasons(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    data = load_data()
    if not data or all(key == "channels" for key in data.keys()):
        await message.answer("❌ Hozircha mavsumlar yo‘q.")
        return

    buttons = []
    for key, season in data.items():
        if key != "channels":  # channels kalitini tashlab ketamiz
            button = InlineKeyboardButton(text=season["title"], callback_data=f"admin_view_{key}")
            buttons.append([button])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🔧 Mavjud mavsumlar (admin panel):", reply_markup=markup)

# 🔧 Admin uchun: Mavsum ustida amallar (tahrirlash/o'chirish)
@dp.callback_query(F.data.startswith("admin_view_"))
async def admin_view_season(callback: CallbackQuery):
    key = callback.data.split("_", 2)[2]
    data = load_data()
    season = data.get(key)

    if not season:
        await callback.answer("❌ Fasl topilmadi.", show_alert=True)
        return

    title = season["title"]
    edit_button = InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_{key}")
    delete_button = InlineKeyboardButton(text="🗑️ O‘chirish", callback_data=f"delete_{key}")
    back_button = InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_list")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [edit_button],
        [delete_button],
        [back_button]
    ])

    await callback.message.edit_text(f"🔧 <b>{title}</b> uchun amallar:", reply_markup=markup)
    await callback.answer()

# ✏️ Tahrirlash tugmasi uchun callback handler
@dp.callback_query(F.data.startswith("edit_"))
async def edit_season_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Ruxsat yo‘q.", show_alert=True)
        return

    key = callback.data.split("_", 1)[1]
    data = load_data()
    season = data.get(key)

    if not season:
        await callback.answer("❌ Bunday fasl topilmadi.", show_alert=True)
        return

    # FSM holatini o'rnatamiz
    await state.set_state(EditSeason.editing_files)
    await state.update_data(season_key=key)
    
    await callback.message.answer(f"✏️ <b>{season['title']}</b> uchun yangi fayllarni yuboring. Eski fayllar o‘chmaydi. Tugatgach /done deb yozing.")
    await callback.answer()

# 🗑️ Mavsumni o'chirish (admin)
@dp.callback_query(F.data.startswith("delete_"))
async def delete_season(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Ruxsat yo‘q.", show_alert=True)
        return

    key = callback.data.split("_", 1)[1]
    data = load_data()
    season = data.get(key)

    if not season:
        await callback.answer("❌ Fasl topilmadi.", show_alert=True)
        return

    del data[key]
    save_data(data)

    await callback.message.edit_text(f"✅ <b>{season['title']}</b> o‘chirildi.")
    await callback.answer()

# Kanal boshqarish buyruqlari
# Kanal qo'shish
@dp.message(Command("add_channel"))
async def add_channel(message: Message, command: CommandObject):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    args = (command.args or "").strip()
    if not args:
        await message.answer("⚠️ Foydalanish: /add_channel &lt;kanal_id&gt; [kanal_nomi]")
        return

    parts = args.split(maxsplit=1)
    channel_id = parts[0]
    channel_name = parts[1] if len(parts) > 1 else channel_id

    data = load_data()
    if "channels" not in data:
        data["channels"] = []

    # Kanal allaqachon mavjudligini tekshirish
    if any(chan["id"] == channel_id for chan in data["channels"]):
        await message.answer(f"❗ Kanal {channel_id} allaqachon ro'yxatda bor.")
        return

    data["channels"].append({
        "id": channel_id,
        "name": channel_name
    })
    save_data(data)

    await message.answer(f"✅ Kanal {channel_name} ({channel_id}) ro'yxatga qo'shildi.")

# Kanal o'chirish
@dp.message(Command("remove_channel"))
async def remove_channel(message: Message, command: CommandObject):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    channel_id = (command.args or "").strip()
    if not channel_id:
        await message.answer("⚠️ Foydalanish: /remove_channel &lt;kanal_id&gt;")
        return

    data = load_data()
    if "channels" not in data:
        data["channels"] = []

    # Kanalni ro'yxatdan o'chirish
    original_length = len(data["channels"])
    data["channels"] = [chan for chan in data["channels"] if chan["id"] != channel_id]
    
    if len(data["channels"]) == original_length:
        await message.answer(f"❌ Kanal {channel_id} topilmadi.")
    else:
        save_data(data)
        await message.answer(f"✅ Kanal {channel_id} ro'yxatdan o'chirildi.")

# Kanallar ro'yxatini ko'rish
@dp.message(Command("list_channels"))
async def list_channels(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    data = load_data()
    channels = data.get("channels", [])

    if not channels:
        await message.answer("📭 Ro'yxat bo'sh. Hozirda majburiy obuna kanallari yo'q.")
        return

    text = "📢 Majburiy obuna kanallari:\n\n"
    for i, channel in enumerate(channels, 1):
        text += f"{i}. {channel['name']}\nID: {channel['id']}\n\n"
    
    await message.answer(text)

# Callback tekshiruvini yangilash
@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    if await is_user_subscribed(callback.from_user.id):
        await callback.message.edit_text("✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.")
        await callback.answer()
    else:
        await callback.answer("❌ Siz hali barcha kanallarga obuna bo'lmagansiz!", show_alert=True)

# 🚀 Ishga tushirish
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())