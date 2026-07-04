from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from config import config
from app.database.models import BotAdmin
from app.utils.auth import is_admin
from app.utils.logging_config import logger

router = Router(name="admin")

@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, db_session: AsyncSession):
    if message.from_user.id != config.SUPER_ADMIN_ID:
        await message.answer("❌ عذراً، هذا الأمر مخصص للمالك (Super Admin) فقط.")
        return
    
    target_user_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer("❌ يرجى كتابة معرف المستخدم بشكل صحيح. مثال: `/addadmin 123456`", parse_mode="Markdown")
            return
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("❌ يرجى تحديد معرف المستخدم أو الرد على رسالة المستخدم باستخدام الأمر `/addadmin`", parse_mode="Markdown")
        return
    
    if target_user_id == config.SUPER_ADMIN_ID:
        await message.answer("⚠️ هذا المستخدم هو المالك بالفعل.")
        return
        
    stmt = select(BotAdmin).where(BotAdmin.user_id == target_user_id)
    res = await db_session.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        await message.answer("⚠️ هذا المستخدم مسؤول بالفعل في قاعدة البيانات.")
        return
        
    try:
        new_admin = BotAdmin(user_id=target_user_id, added_by=message.from_user.id)
        db_session.add(new_admin)
        await db_session.commit()
        logger.info(f"Admin added dynamically: User ID {target_user_id} by Super Admin")
        await message.answer(f"✅ تم إضافة المستخدم `{target_user_id}` كمسؤول بنجاح.", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error adding admin to database")
        await db_session.rollback()
        await message.answer(f"❌ فشل إضافة المسؤول إلى قاعدة البيانات: {e}")

@router.message(Command("deladmin"))
async def cmd_deladmin(message: Message, db_session: AsyncSession):
    if message.from_user.id != config.SUPER_ADMIN_ID:
        await message.answer("❌ عذراً، هذا الأمر مخصص للمالك (Super Admin) فقط.")
        return
        
    target_user_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer("❌ يرجى كتابة معرف المستخدم بشكل صحيح. مثال: `/deladmin 123456`", parse_mode="Markdown")
            return
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        await message.answer("❌ يرجى تحديد معرف المستخدم أو الرد على رسالة المستخدم باستخدام الأمر `/deladmin`", parse_mode="Markdown")
        return
        
    stmt = select(BotAdmin).where(BotAdmin.user_id == target_user_id)
    res = await db_session.execute(stmt)
    admin_entry = res.scalar_one_or_none()
    if not admin_entry:
        await message.answer("⚠️ هذا المستخدم ليس مسؤولاً في قاعدة البيانات.")
        return
        
    try:
        await db_session.delete(admin_entry)
        await db_session.commit()
        logger.info(f"Admin removed dynamically: User ID {target_user_id} by Super Admin")
        await message.answer(f"✅ تم إزالة المستخدم `{target_user_id}` من قائمة المسؤولين.", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error removing admin from database")
        await db_session.rollback()
        await message.answer(f"❌ فشل إزالة المسؤول من قاعدة البيانات: {e}")

@router.message(F.photo)
async def handle_custom_thumbnail(message: Message, db_session: AsyncSession):
    authorized = await is_admin(message.from_user.id, db_session)
    if not authorized:
        await message.answer("❌ عذراً، لا تملك الصلاحية لتغيير الصورة المصغرة للفيديو.")
        return
        
    photo = message.photo[-1]
    
    # Ensure app/data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    thumb_path = data_dir / "custom_thumb.jpg"
    
    try:
        # Save the file_id directly as a string to app/data/custom_thumb_id.txt
        thumb_id_path = data_dir / "custom_thumb_id.txt"
        with open(thumb_id_path, "w") as f:
            f.write(photo.file_id)
            
        logger.info(f"Custom video thumbnail updated by Admin (User ID: {message.from_user.id}) with File ID: {photo.file_id}")
        await message.answer("✅ تم تحديث الصورة المصغرة الافتراضية للفيديوهات بنجاح.")
    except Exception as e:
        logger.exception("Error saving custom thumbnail file_id")
        await message.answer(f"❌ فشل تحديث الصورة المصغرة: {e}")
