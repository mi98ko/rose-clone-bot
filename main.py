import sqlite3
import os
from flask import Flask
from threading import Thread
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

# ---------------- DATABASE ----------------
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS filters (chat_id INTEGER, keyword TEXT, reply TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS warns (chat_id INTEGER, user_id INTEGER, count INTEGER)")
conn.commit()

# ---------------- KEEP ALIVE ----------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running!"

def run():
    app_web.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run).start()

keep_alive()

# ---------------- ADMIN CHECK ----------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    admins = await context.bot.get_chat_administrators(chat_id)
    return any(admin.user.id == user_id for admin in admins)

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 PRO MAX Rose Clone Bot Running!")

# ---------------- LOG ----------------
async def log_action(context, text):
    if LOG_CHANNEL_ID != 0:
        await context.bot.send_message(LOG_CHANNEL_ID, text)

# ---------------- BAN ----------------
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await update.message.reply_text("🚫 User Banned!")
        await log_action(context, f"🚫 {user.first_name} banned")

# ---------------- MUTE ----------------
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user.id,
            ChatPermissions(can_send_messages=False)
        )
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("Unmute", callback_data=f"unmute_{user.id}")]])
        await update.message.reply_text("🔇 User Muted!", reply_markup=btn)
        await log_action(context, f"🔇 {user.first_name} muted")

# ---------------- UNMUTE BUTTON ----------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("unmute_"):
        user_id = int(data.split("_")[1])
        await context.bot.restrict_chat_member(
            query.message.chat.id,
            user_id,
            ChatPermissions(can_send_messages=True)
        )
        await query.edit_message_text("🔊 User Unmuted!")

# ---------------- WARN ----------------
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id

        cursor.execute("SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user.id))
        data = cursor.fetchone()

        count = data[0] + 1 if data else 1

        cursor.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user.id))
        cursor.execute("INSERT INTO warns VALUES (?, ?, ?)", (chat_id, user.id, count))
        conn.commit()

        await update.message.reply_text(f"⚠️ Warn {count}/3")

        if count >= 3:
            await context.bot.restrict_chat_member(chat_id, user.id, ChatPermissions(can_send_messages=False))
            await update.message.reply_text("🚫 Auto Muted!")

# ---------------- WARNINGS ----------------
async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id

        cursor.execute("SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user.id))
        data = cursor.fetchone()

        count = data[0] if data else 0
        await update.message.reply_text(f"⚠️ Warnings: {count}")

# ---------------- RESET WARN ----------------
async def resetwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id

        cursor.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user.id))
        conn.commit()
        await update.message.reply_text("✅ Warnings Reset!")

# ---------------- FILTERS ----------------
async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = update.effective_chat.id
    keyword = context.args[0].lower()
    reply = " ".join(context.args[1:])

    cursor.execute("INSERT INTO filters VALUES (?, ?, ?)", (chat_id, keyword, reply))
    conn.commit()

    await update.message.reply_text("✅ Filter added!")

async def del_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = update.effective_chat.id
    keyword = context.args[0].lower()

    cursor.execute("DELETE FROM filters WHERE chat_id=? AND keyword=?", (chat_id, keyword))
    conn.commit()

    await update.message.reply_text("❌ Filter deleted!")

async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cursor.execute("SELECT keyword FROM filters WHERE chat_id=?", (chat_id,))
    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No filters.")
        return

    text = "\n".join([i[0] for i in data])
    await update.message.reply_text(f"📂 Filters:\n{text}")

# ---------------- AUTO FILTER ----------------
async def auto_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = update.message.text.lower()

    cursor.execute("SELECT keyword, reply FROM filters WHERE chat_id=?", (chat_id,))
    data = cursor.fetchall()

    for keyword, reply in data:
        if keyword in msg:
            await update.message.reply_text(reply)
            break

# ---------------- ANTI LINK ----------------
async def anti_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and ("http" in update.message.text or "t.me" in update.message.text):
        await update.message.delete()

# ---------------- WELCOME ----------------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        group = update.effective_chat.title
        await update.message.reply_text(f"🎉 Welcome {user.first_name} to {group}!")

# ---------------- APP ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("warn", warn))
app.add_handler(CommandHandler("warnings", warnings))
app.add_handler(CommandHandler("resetwarn", resetwarn))

app.add_handler(CommandHandler("addfilter", add_filter))
app.add_handler(CommandHandler("delfilter", del_filter))
app.add_handler(CommandHandler("filters", list_filters))

app.add_handler(CallbackQueryHandler(button))

app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_link))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_filter))

print("Bot Running...")
app.run_polling()
