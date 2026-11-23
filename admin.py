from aiogram import Router, F
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
import config
import database
import asyncio
import random

router = Router()

@router.message(Command("admin"))
async def admin_start(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Siz admin emassiz!")
        return

    web_url = config.WEBAPP_URL or "https://localhost:8080"
    
    await message.answer(
        "⚙️ <b>Admin Panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Menyuni Tahrirlash", web_app=WebAppInfo(url=f"{web_url}/web/admin.html"))],
                [InlineKeyboardButton(text="⚙️ Ish vaqti boshqaruv", callback_data="admin_work_mode")]
            ]
        )
    )

@router.callback_query(F.data == "admin_work_mode")
async def admin_work_mode_handler(call: CallbackQuery):
    status_val = database.get_setting("force_closed")
    # Interpretation: 
    # '0' or None -> Open
    # 'daily_close' -> Closed for day
    # 'temp_close' -> Temporary maintenance
    # '1' -> Old force close (treat as temp)
    
    if status_val == 'daily_close':
        status_text = "🌙 <b>KAFE YOPIQ (Kunlik)</b>"
        options = [
             [InlineKeyboardButton(text="🟢 Ochish (va Xabar yuborish)", callback_data="set_open")]
        ]
    elif status_val == 'temp_close' or status_val == '1':
        status_text = "🛠 <b>KAFE YOPIQ (Vaqtincha)</b>"
        options = [
             [InlineKeyboardButton(text="🟢 Ochish (va Xabar yuborish)", callback_data="set_open")]
        ]
    else:
        status_text = "🟢 <b>Kafe OCHIQ</b>"
        options = [
            [InlineKeyboardButton(text="🌙 Kunlik Yopish (23:30 dan oldin)", callback_data="set_daily_close")],
            [InlineKeyboardButton(text="🛠 Vaqtincha Yopish (Tanaffus)", callback_data="set_temp_close")]
        ]
    
    options.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")])
    
    await call.message.edit_text(
        f"⚙️ <b>Ish vaqti boshqaruv</b>\n\n"
        f"Hozirgi holat: {status_text}\n\n"
        "Kerakli harakatni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=options)
    )

@router.callback_query(F.data.in_(["set_open", "set_daily_close", "set_temp_close"]))
async def toggle_work_mode(call: CallbackQuery, bot):
    if call.data == "set_daily_close":
        database.set_setting("force_closed", "daily_close")
        await call.answer("Kafe kunlik yopildi.")
        
    elif call.data == "set_temp_close":
        database.set_setting("force_closed", "temp_close")
        await call.answer("Kafe vaqtincha yopildi.")
        
    elif call.data == "set_open":
        prev_status = database.get_setting("force_closed")
        database.set_setting("force_closed", "0")
        await call.answer("Kafe ochildi!")
        
        # Broadcast if opening after closure
        if prev_status in ['daily_close', 'temp_close', '1']:
             # Send async broadcast
             asyncio.create_task(broadcast_open_message(bot))
    
    await admin_work_mode_handler(call)

async def broadcast_open_message(bot):
    users = database.get_all_users()
    msg = (
        "📢 <b>DIQQAT! KAFE OCHILDI!</b> 🥳\n\n"
        "Hurmatli mijoz, biz yana ishga tushdik va buyurtmalarni qabul qilmoqdamiz.\n"
        "Mazali taomlardan bahramand bo'ling! 😋\n\n"
        "Buyurtma berish uchun: /start"
    )
    
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, msg)
            count += 1
            await asyncio.sleep(0.05) # Flood limit protection
        except Exception as e:
            pass
    print(f"Broadcast sent to {count} users.")

@router.callback_query(F.data == "admin_back")
async def admin_back_handler(call: CallbackQuery):
    web_url = config.WEBAPP_URL or "https://localhost:8080"
    await call.message.edit_text(
        "⚙️ <b>Admin Panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Menyuni Tahrirlash", web_app=WebAppInfo(url=f"{web_url}/web/admin.html"))],
                [InlineKeyboardButton(text="⚙️ Ish vaqti boshqaruv", callback_data="admin_work_mode")]
            ]
        )
    )

@router.callback_query(F.data.startswith("status:"))
async def status_callback(call: CallbackQuery, bot):
    # data format: "status:new_status:order_id"
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Xato data", show_alert=True)
        return
        
    new_status = parts[1]
    order_id = parts[2]
    
    real_db_status = new_status
    if new_status.startswith("canceled_"):
        real_db_status = "canceled"
    
    if database.update_order_status(order_id, real_db_status):
        status_text_map = {
            'preparing': "🍳 Tayyorlanmoqda",
            'delivering': "🚀 Yetkazilmoqda",
            'completed': "✅ Yakunlandi",
            'canceled': "❌ Bekor qilindi"
        }
        human_status = status_text_map.get(real_db_status, real_db_status)
        
        await call.answer(f"Buyurtma #{order_id} statusi o'zgardi: {human_status}")
        
        # Get order details to notify user
        order = database.get_order(order_id)
        if order:
            user_id = order['user_id']
            try:
                if new_status == 'canceled_stock':
                    cancel_msg = (
                        f"🚫 <b>Buyurtma #{order_id} bekor qilindi.</b>\n\n"
                        "Uzr so'raymiz, tanlangan mahsulot ayni vaqtda tugaganligi sababli buyurtmani bajara olmaymiz. 😔\n\n"
                        "Iltimos, menyudan boshqa mahsulot tanlab qayta buyurtma bering. Tushunishingiz uchun rahmat!"
                    )
                    await bot.send_message(user_id, cancel_msg)
                
                elif new_status == 'canceled_payment':
                    cancel_msg = (
                        f"🚫 <b>Buyurtma #{order_id} bekor qilindi.</b>\n\n"
                        "❌ <b>To'lov bilan muammo aniqlandi.</b>\n"
                        "Yuborilgan chek tasdiqlanmadi yoki pul tushmagan.\n\n"
                        "Iltimos, qaytadan tekshirib to'lov qiling yoki naqd to'lov turini tanlang."
                    )
                    await bot.send_message(user_id, cancel_msg)

                elif new_status == 'completed':
                     await bot.send_message(user_id, f"✅ Buyurtma #{order_id} yetkazib berildi. Yoqimli ishtaha! 😋")
                elif new_status == 'delivering':
                    await bot.send_message(user_id, f"ℹ️ Buyurtma #{order_id} holati: {human_status}")
                    # Schedule auto-completion (10-15 mins)
                    delay = random.randint(600, 900) 
                    asyncio.create_task(
                        delayed_completion(bot, order_id, user_id, delay)
                    )
                else:
                    await bot.send_message(user_id, f"ℹ️ Buyurtma #{order_id} holati: {human_status}")
            except Exception as e:
                print(f"Failed to notify user {user_id}: {e}")
        
        # Update admin message
        if real_db_status in ['completed', 'canceled']:
             await call.message.edit_reply_markup(reply_markup=None)
             await call.message.reply(f"Buyurtma #{order_id} {human_status}.")
    else:
        await call.answer("DB Xatolik", show_alert=True)

async def delayed_completion(bot, order_id, user_id, delay):
    await asyncio.sleep(delay)
    
    # Check if still delivering (not canceled or already completed manually)
    current_order = database.get_order(order_id)
    if current_order and current_order['status'] == 'delivering':
        # Mark as completed
        if database.update_order_status(order_id, 'completed'):
            # Notify User
            try:
                msg = (
                    f"✅ <b>Buyurtma #{order_id} yetkazib berildi.</b>\n\n"
                    "Yoqimli ishtaha! 😋\n"
                    "Bizni tanlaganingiz uchun rahmat."
                )
                await bot.send_message(user_id, msg)
                
                # Notify Admin (optional logging) - maybe send to channel?
                # For now just print log
                print(f"Order #{order_id} auto-completed after {delay}s")
            except Exception as e:
                print(f"Auto-complete notification failed: {e}")
