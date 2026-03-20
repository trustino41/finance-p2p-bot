import os
import httpx
import hashlib
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# --- 1. CONFIGURATION ---
TOKEN = "8684970540:AAFCvC0OknPVCsszBI6CxnJM8n9LxmHqQwI"
CHAT_ID = "7311646141"
WEBHOOK_URL =  "https://github.com/trustino41/finance-p2p-bot.git"
# رابط صورة التنبيه (USDT أو Binance)
IMAGE_URL = "https://raw.githubusercontent.com/binance/brand-assets/master/logo/vertical/black.png"

current_amount = "200000"
last_data_hash = ""
last_alert_hash = ""
show_price_filter = 0.0
alert_price = 0.0

# --- 2. KEYBOARD & HELPERS ---
def get_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10k", callback_data="amt_10000"),
            InlineKeyboardButton("100k", callback_data="amt_100000"),
            InlineKeyboardButton("200k", callback_data="amt_200000"),
        ],
        [InlineKeyboardButton("🔄 Actualiser", callback_data="refresh")]
    ])

def is_blocked_payment(ad):
    blocked = ["airtime", "orange", "flexy", "ooredoo", "mobilis"]
    methods = ad.get("adv", {}).get("tradeMethods", [])
    for m in methods:
        name = str(m.get("tradeMethodName", "")).lower()
        if any(b in name for b in blocked): return True
    return False

def build_message(adverts):
    msg = f"📊 *Recherche: {int(current_amount):,} DZD*\n"
    if show_price_filter > 0:
        msg += f"💹 *Filtre: >= {show_price_filter}*\n"
    if alert_price > 0:
        msg += f"🚨 *Alerte à: {alert_price}*\n"
    msg += "\n"
    for i, ad in enumerate(adverts[:5], start=1):
        price = ad["adv"]["price"]
        name = ad["advertiser"]["nickName"]
        msg += f"{i}️⃣ *{price} DZD* | 👤 `{name}`\n"
    return msg

# --- 3. CORE LOGIC (FETCH & NOTIFY) ---
async def fetch_p2p(context: ContextTypes.DEFAULT_TYPE):
    global last_data_hash, last_alert_hash
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    payload = {
        "asset": "USDT", "fiat": "DZD", "merchantCheck": False,
        "page": 1, "rows": 10, "tradeType": "SELL", "transAmount": current_amount
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json=payload)
            data = res.json()
        
        adverts = [a for a in data.get("data", []) if not is_blocked_payment(a)]
        
        if show_price_filter > 0:
            adverts = [a for a in adverts if float(a["adv"]["price"]) >= show_price_filter]

        if not adverts: return

        status = "".join(f"{a['adv']['price']}" for a in adverts[:3])
        current_hash = hashlib.md5(status.encode()).hexdigest()

        if current_hash != last_data_hash:
            last_data_hash = current_hash
            msg = build_message(adverts)
            # إرسال الصورة مع التحديث
            await context.bot.send_photo(
                chat_id=CHAT_ID,
                photo=IMAGE_URL,
                caption=msg,
                parse_mode="Markdown",
                reply_markup=get_keyboard()
            )

        # منطق التنبيه الخاص (Alert)
        top_price = float(adverts[0]["adv"]["price"])
        if alert_price > 0 and top_price >= alert_price:
            alert_key = f"alert-{top_price}"
            if hashlib.md5(alert_key.encode()).hexdigest() != last_alert_hash:
                last_alert_hash = hashlib.md5(alert_key.encode()).hexdigest()
                await context.bot.send_message(CHAT_ID, f"🚨 *ALERTE P2P!*\nLe prix a atteint `{top_price} DZD`", parse_mode="Markdown")

    except Exception as e: print(f"Error: {e}")

# --- 4. HANDLERS ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_amount, show_price_filter, alert_price, last_data_hash
    text = update.message.text.strip()
    
    if text == "0":
        show_price_filter = 0.0
        alert_price = 0.0
        await update.message.reply_text("✅ Filtres réinitialisés.")
    elif text.isdigit() and int(text) > 1000:
        current_amount = text
        await update.message.reply_text(f"⚙️ Montant changé à {text} DZD")
    else:
        try:
            val = float(text)
            if show_price_filter == 0: show_price_filter = val
            else: alert_price = val
            await update.message.reply_text(f"✅ Paramètres mis à jour.")
        except: pass
    
    last_data_hash = ""
    await fetch_p2p(context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_amount, last_data_hash
    query = update.callback_query
    await query.answer()
    if "amt_" in query.data:
        current_amount = query.data.split("_")[1]
    last_data_hash = ""
    await fetch_p2p(context)

# --- 5. DEPLOYMENT (RENDER WEBHOOK) ---
def main():
    PORT = int(os.environ.get("PORT", 8443))
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    if app.job_queue:
        app.job_queue.run_repeating(fetch_p2p, interval=60, first=5)

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()
