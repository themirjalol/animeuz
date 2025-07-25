import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from functools import wraps
from datetime import datetime

# PostgreSQL uchun importlar
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, func, URL
from sqlalchemy.orm import sessionmaker, relationship, joinedload, declarative_base

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
BOT_TOKEN = "8433594778:AAHCO7jD21aAdiS1PqljS3_NIGQ0ckpQpf8"
ADMINS = [5873723609]  # ← O'zingizning Telegram ID

# PostgreSQL ma'lumotlar bazasi - Xavfsiz ulanish
# Ma'lumotlaringizni bu yerga kiriting:
DB_USER = "mirjalol"  # Sizning foydalanuvchi nomingiz
DB_PASSWORD = "Mirjalol2008@#"  # O'z parolingizni kiriting
DB_HOST = "postgresql-mirjalol.alwaysdata.net"
DB_PORT = 5432
DB_NAME = "mirjalol_anime"  # Sizning ma'lumotlar bazangiz nomi

# URL obyektini yaratish (maxsus belgilar avtomatik tarzda encode qilinadi)
database_url = URL.create(
    drivername="postgresql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME
)

# Engine yaratish
engine = create_engine(database_url)

# SQLAlchemy 2.0 uchun to'g'ri declarative_base
Base = declarative_base()

class Season(Base):
    __tablename__ = 'seasons'
    
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    files = relationship("VideoFile", back_populates="season", cascade="all, delete-orphan")

class VideoFile(Base):
    __tablename__ = 'video_files'
    
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('seasons.id'), nullable=False)
    file_id = Column(String, nullable=False)
    caption = Column(Text)
    number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    season = relationship("Season", back_populates="files")

class Channel(Base):
    __tablename__ = 'channels'
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Ma'lumotlar bazasi jadvallarini yaratish
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    return SessionLocal()

# Ma'lumotlarni olish funksiyalari
def load_data():
    """PostgreSQL dan barcha ma'lumotlarni o'qish"""
    db = get_db()
    try:
        # Fasllarni va ularning fayllarini olish
        seasons = db.query(Season).options(joinedload(Season.files)).all()
        
        # Kanallarni olish
        channels = db.query(Channel).all()
        
        # Natijani eski formatga o'tkazish
        data = {"channels": []}
        
        # Kanallar
        for channel in channels:
            data["channels"].append({
                "id": channel.channel_id,
                "name": channel.name
            })
        
        # Fasllar
        for season in seasons:
            files_data = []
            # Fayllarni tartiblab olish
            sorted_files = sorted(season.files, key=lambda x: x.number)
            for file in sorted_files:
                files_data.append({
                    "file_id": file.file_id,
                    "caption": file.caption or "",
                    "number": file.number
                })
            
            data[season.key] = {
                "title": season.title,
                "files": files_data
            }
        
        return data
    finally:
        db.close()

def add_file_to_season(season_key: str, file_id: str, caption: str = ""):
    """Faylni faslga qo'shish"""
    db = get_db()
    try:
        # Fasl mavjudligini tekshirish
        season = db.query(Season).filter(Season.key == season_key).first()
        if not season:
            return False
        
        # Oxirgi fayl raqamini olish
        max_number = db.query(func.max(VideoFile.number)).filter(VideoFile.season_id == season.id).scalar() or 0
        
        # Yangi fayl qo'shish
        new_file = VideoFile(
            season_id=season.id,
            file_id=file_id,
            caption=caption,
            number=max_number + 1
        )
        
        db.add(new_file)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Xato: {e}")
        return False
    finally:
        db.close()

# Kanal boshqaruvi funksiyalari
def add_channel_db(channel_id: str, channel_name: str):
    """Kanal qo'shish"""
    db = get_db()
    try:
        # Kanal allaqachon mavjudligini tekshirish
        existing = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if existing:
            return False
        
        new_channel = Channel(channel_id=channel_id, name=channel_name)
        db.add(new_channel)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Xato: {e}")
        return False
    finally:
        db.close()

def remove_channel_db(channel_id: str):
    """Kanal o'chirish"""
    db = get_db()
    try:
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if channel:
            db.delete(channel)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        print(f"Xato: {e}")
        return False
    finally:
        db.close()

def get_channels():
    """Barcha kanallarni olish"""
    db = get_db()
    try:
        channels = db.query(Channel).all()
        return [{"id": c.channel_id, "name": c.name} for c in channels]
    finally:
        db.close()

# 🤖 Bot va Dispatcher
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# 🧭 Holatlar
class AddSeason(StatesGroup):
    waiting_files = State()
    waiting_caption = State()

class EditSeason(StatesGroup):
    editing_files = State()
    waiting_caption = State()

# Foydalanuvchi obunasi tekshiruvi
async def is_user_subscribed(user_id: int) -> bool:
    """Foydalanuvchi barcha majburiy kanallarga obuna bo'lganini tekshiradi"""
    channels = get_channels()
    
    if not channels:
        return True
        
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["id"], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except TelegramForbiddenError:
            continue
        except Exception:
            return False
            
    return True

def subscription_required(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id in ADMINS:
            return await handler(message, *args, **kwargs)
            
        if not await is_user_subscribed(message.from_user.id):
            channels = get_channels()
            
            if not channels:
                return await handler(message, *args, **kwargs)
            
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
            channels = get_channels()
            
            if not channels:
                return await handler(callback, *args, **kwargs)
            
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
    
    # PostgreSQL ga yangi fasl qo'shish
    db = get_db()
    try:
        existing_season = db.query(Season).filter(Season.key == key).first()
        if existing_season:
            await message.answer("❗ Bu fasl allaqachon mavjud.")
            db.close()
            return

        new_season = Season(key=key, title=season_name.replace("_", " "))
        db.add(new_season)
        db.commit()
        
        await state.set_state(AddSeason.waiting_files)
        await state.update_data(season_key=key)

        bot_username = (await bot.me()).username
        link = f"https://t.me/{bot_username}?start={key}"
        await message.answer(f"📥 Endi fayllarni yuboring. Tugatgach /done deb yozing.\nLink: {link}")
    except Exception as e:
        db.rollback()
        await message.answer("❌ Xatolik yuz berdi.")
        print(f"Xato: {e}")
    finally:
        db.close()

# 🔘 Fayl qabul qilish (add/edit)
@dp.message(StateFilter(AddSeason.waiting_files, EditSeason.editing_files), F.video)
async def handle_video(message: Message, state: FSMContext):
    file_id = message.video.file_id
    state_data = await state.get_data()
    key = state_data["season_key"]

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

    add_file_to_season(key, file_id, caption)
    
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

# 🔘 /skip
@dp.message(StateFilter(AddSeason.waiting_caption, EditSeason.waiting_caption), Command("skip"))
async def skip_caption(message: Message, state: FSMContext):
    state_data = await state.get_data()
    key = state_data["season_key"]
    file_id = state_data["current_file_id"]

    add_file_to_season(key, file_id, "")
    
    current_state = await state.get_state()
    if current_state == AddSeason.waiting_caption.state:
        await state.set_state(AddSeason.waiting_files)
    else:
        await state.set_state(EditSeason.editing_files)
    
    await message.answer("✅ Fayl qo‘shildi (tavsiz). Davom eting...")

# 🔘 /list_seasons
@dp.message(Command("list_seasons"))
@subscription_required
async def list_seasons(message: Message):
    data = load_data()
    if not data or all(key == "channels" for key in data.keys()):
        await message.answer("❌ Hozircha mavsumlar yo‘q.")
        return

    buttons = []
    for key, season in data.items():
        if key != "channels":
            button = InlineKeyboardButton(text=season["title"], callback_data=f"view_{key}")
            buttons.append([button])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🎬 Mavjud mavsumlar:", reply_markup=markup)

# 🎬 Faslni ko'rish
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

# 🔐 /admin_list
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
        if key != "channels":
            button = InlineKeyboardButton(text=season["title"], callback_data=f"admin_view_{key}")
            buttons.append([button])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🔧 Mavjud mavsumlar (admin panel):", reply_markup=markup)

# 🔧 Admin uchun: Mavsum ustida amallar
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

# ✏️ Tahrirlash tugmasi
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

    await state.set_state(EditSeason.editing_files)
    await state.update_data(season_key=key)
    
    await callback.message.answer(f"✏️ <b>{season['title']}</b> uchun yangi fayllarni yuboring. Eski fayllar o‘chmaydi. Tugatgach /done deb yozing.")
    await callback.answer()

# 🗑️ Mavsumni o'chirish
@dp.callback_query(F.data.startswith("delete_"))
async def delete_season(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Ruxsat yo‘q.", show_alert=True)
        return

    key = callback.data.split("_", 1)[1]
    
    # PostgreSQL dan faslni o'chirish
    db = get_db()
    try:
        season = db.query(Season).filter(Season.key == key).first()
        if not season:
            await callback.answer("❌ Fasl topilmadi.", show_alert=True)
            db.close()
            return

        season_title = season.title
        db.delete(season)
        db.commit()
        
        await callback.message.edit_text(f"✅ <b>{season_title}</b> o‘chirildi.")
        await callback.answer()
    except Exception as e:
        db.rollback()
        await callback.answer("❌ Xatolik yuz berdi.", show_alert=True)
        print(f"Xato: {e}")
    finally:
        db.close()

# Kanal boshqarish buyruqlari
@dp.message(Command("add_channel"))
async def add_channel(message: Message, command: CommandObject):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    args = (command.args or "").strip()
    if not args:
        await message.answer("⚠️ Foydalanish: /add_channel <kanal_id> [kanal_nomi]")
        return

    parts = args.split(maxsplit=1)
    channel_id = parts[0]
    channel_name = parts[1] if len(parts) > 1 else channel_id

    if add_channel_db(channel_id, channel_name):
        await message.answer(f"✅ Kanal {channel_name} ({channel_id}) ro'yxatga qo'shildi.")
    else:
        await message.answer(f"❗ Kanal {channel_id} allaqachon ro'yxatda bor.")

@dp.message(Command("remove_channel"))
async def remove_channel(message: Message, command: CommandObject):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    channel_id = (command.args or "").strip()
    if not channel_id:
        await message.answer("⚠️ Foydalanish: /remove_channel <kanal_id>")
        return

    if remove_channel_db(channel_id):
        await message.answer(f"✅ Kanal {channel_id} ro'yxatdan o'chirildi.")
    else:
        await message.answer(f"❌ Kanal {channel_id} topilmadi.")

@dp.message(Command("list_channels"))
async def list_channels(message: Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Ruxsat yo‘q.")
        return

    channels = get_channels()
    
    if not channels:
        await message.answer("📭 Ro'yxat bo'sh. Hozirda majburiy obuna kanallari yo'q.")
        return

    text = "📢 Majburiy obuna kanallari:\n\n"
    for i, channel in enumerate(channels, 1):
        text += f"{i}. {channel['name']}\nID: {channel['id']}\n\n"
    
    await message.answer(text)

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