import sqlite3
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = "8390210892:AAGb1G9hS3gZcKI62Zxj7BNxr5hpXFw3Jd0"
ADMIN_ID = 2076460872 # PUT YOUR TELEGRAM ID
DB_NAME = "bot.db"

# ---------- DATABASE ----------
def init_db():
    con = sqlite3.connect(DB_NAME)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        completed_tasks INTEGER DEFAULT 0
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        assigned INTEGER DEFAULT 0
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        user_id INTEGER,
        task_id TEXT,
        proof TEXT,
        status TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        user_id INTEGER,
        amount INTEGER,
        bank TEXT,
        status TEXT
    )""")

    con.commit()
    con.close()

def db():
    return sqlite3.connect(DB_NAME)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    con = db()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
                (user.id, user.username))
    con.commit()
    con.close()

    keyboard = [
        [InlineKeyboardButton("📝 Task", callback_data="task")],
        [InlineKeyboardButton("👤 Account", callback_data="account")],
        [InlineKeyboardButton("💰 Withdrawal", callback_data="withdraw")],
        [InlineKeyboardButton("🎁 Referral", callback_data="referral")]
    ]
    await update.message.reply_text(
        "👋 Welcome\nSelect an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- BUTTON HANDLER ----------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "task":
        await query.message.reply_text(
            "📝 Task Instructions\n"
            "• Complete the assigned task\n"
            "• Submit proof here\n"
            "• Admin will verify within 5 hours"
        )
        context.user_data["awaiting_proof"] = True

    elif query.data == "account":
        con = db()
        cur = con.cursor()
        cur.execute("SELECT balance, completed_tasks FROM users WHERE user_id=?",
                    (query.from_user.id,))
        bal, tasks = cur.fetchone()
        con.close()

        await query.message.reply_text(
            f"👤 Your Account\n"
            f"✅ Completed Tasks: {tasks}\n"
            f"💰 Balance: Rs {bal}"
        )

    elif query.data == "withdraw":
        await query.message.reply_text(
            "💸 Enter withdrawal amount\n(Minimum Rs 250)"
        )
        context.user_data["withdraw_amount"] = True

    elif query.data == "referral":
        await query.message.reply_text("🚧 Coming Soon")

# ---------- TASK SUBMISSION ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    con = db()
    cur = con.cursor()

    # TASK PROOF
    if context.user_data.get("awaiting_proof"):
        cur.execute("SELECT task_id FROM tasks WHERE assigned=0 LIMIT 1")
        task = cur.fetchone()

        if not task:
            await update.message.reply_text("❌ No tasks available")
            return

        task_id = task[0]

        cur.execute("UPDATE tasks SET assigned=1 WHERE task_id=?", (task_id,))
        cur.execute(
            "INSERT INTO submissions VALUES (?,?,?,?)",
            (user.id, task_id, text, "pending")
        )
        con.commit()

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"accept_{user.id}_{task_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}_{task_id}")
            ]
        ])

        await context.bot.send_message(
            ADMIN_ID,
            f"📥 New Task Submission\n"
            f"User: @{user.username}\n"
            f"Task ID: {task_id}\n"
            f"Proof: {text}",
            reply_markup=buttons
        )

        await update.message.reply_text("⏳ Task submitted. Wait for admin approval.")
        context.user_data["awaiting_proof"] = False

    # WITHDRAW AMOUNT
    elif context.user_data.get("withdraw_amount"):
        amount = int(text)
        if amount < 250:
            await update.message.reply_text("❌ Minimum withdrawal is Rs 250")
            return

        context.user_data["amount"] = amount
        context.user_data["withdraw_amount"] = False
        context.user_data["bank"] = True
        await update.message.reply_text("🏦 Enter bank details")

    # BANK DETAILS
    elif context.user_data.get("bank"):
        amount = context.user_data["amount"]
        cur.execute(
            "INSERT INTO withdrawals VALUES (?,?,?,?)",
            (user.id, amount, text, "pending")
        )
        con.commit()

        button = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Paid", callback_data=f"paid_{user.id}_{amount}")]
        ])

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 Withdrawal Request\n"
            f"User: @{user.username}\n"
            f"Amount: Rs {amount}\n"
            f"Bank: {text}",
            reply_markup=button
        )

        await update.message.reply_text("⏳ Payment will be sent within 2 days")
        context.user_data.clear()

    con.close()

# ---------- ADMIN ACTIONS ----------
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action = data[0]
    user_id = int(data[1])
    value = data[2]

    con = db()
    cur = con.cursor()

    if action == "accept":
        cur.execute("UPDATE submissions SET status='accepted' WHERE user_id=? AND task_id=?",
                    (user_id, value))
        cur.execute("UPDATE users SET balance=balance+25, completed_tasks=completed_tasks+1 WHERE user_id=?",
                    (user_id,))
        con.commit()
        await context.bot.send_message(user_id, "✅ Task accepted\n💰 Rs 25 added")

    elif action == "reject":
        cur.execute("UPDATE submissions SET status='rejected' WHERE user_id=? AND task_id=?",
                    (user_id, value))
        con.commit()
        await context.bot.send_message(user_id, "❌ Task rejected")

    elif action == "paid":
        cur.execute("UPDATE withdrawals SET status='paid' WHERE user_id=? AND amount=?",
                    (user_id, value))
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=?",
                    (value, user_id))
        con.commit()
        await context.bot.send_message(user_id, "✅ Payment sent successfully")

    con.close()
    await query.edit_message_reply_markup(None)

# ---------- ADMIN COMMAND ----------
async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only")

    task_id = context.args[0]
    con = db()
    cur = con.cursor()
    cur.execute("INSERT INTO tasks (task_id) VALUES (?)", (task_id,))
    con.commit()
    con.close()

    await update.message.reply_text(f"✅ Task {task_id} added")

# ---------- MAIN ----------
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(accept|reject|paid)_"))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
