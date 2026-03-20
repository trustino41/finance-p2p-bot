import os
import httpx
import hashlib
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# --- 1. CONFIGURATION ---
TOKEN = "8684970540:AAFCvC0OknPVCsszBI6CxnJM8n9LxmHqQwI"
CHAT_ID = "7311646141"
WEBHOOK_URL = "https://finance-p2p-bot-1.onrender.com"
# رابط صورة التنبيه (USDT أو Binance)
IMAGE_URL = "https://raw.githubusercontent.com/binance/brand-assets/master/logo/vertical/black.png"


current_amount = "200000"
last_data_hash = ""
last_alert_hash = ""

show_price_filter = 0.0
alert_price = 0.0


def get_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10k", callback_data="amt_10000"),
            InlineKeyboardButton("100k", callback_data="amt_100000"),
            InlineKeyboardButton("200k", callback_data="amt_200000"),
        ],
        [InlineKeyboardButton("🔄 Actualiser", callback_data="refresh")]
    ])


def norm(x):
    return str(x).strip().lower() if x else ""


def format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def extract_payment_names(ad):
    names = []
    adv = ad.get("adv", {})

    methods = adv.get("tradeMethods", [])
    for m in methods:
        if isinstance(m, dict):
            for k in ("tradeMethodName", "identifier", "payType", "payMethodName"):
                if m.get(k):
                    names.append(str(m.get(k)))

    for p in adv.get("payTypes", []):
        if p:
            names.append(str(p))

    unique = []
    for n in names:
        if n not in unique:
            unique.append(n)

    return unique


def is_blocked_payment(ad):
    blocked = ["airtime", "orange"]
    for name in extract_payment_names(ad):
        t = norm(name)
        if any(b in t for b in blocked):
            return True
    return False


def build_message(adverts):
    msg = f"📊 Recherche pour un montant de : DZD {int(current_amount):,}\n"

    if show_price_filter > 0:
        msg += f"💹 Afficher les acheteurs à partir de : ⁠ {format_number(show_price_filter)} ⁠ et plus\n"
    else:
        msg += "💹 Afficher tous les prix\n"

    if alert_price > 0:
        msg += f"🚨 Prix d'alerte : ⁠ {format_number(alert_price)} ⁠\n"

    msg += "\n"

    for i, ad in enumerate(adverts[:5], start=1):
        adv = ad.get("adv", {})
        user = ad.get("advertiser", {})

        price = adv.get("price", "0")
        name = user.get("nickName", "Inconnu")
        rate = user.get("positiveRate", 0)

        try:
            rate = float(rate)
        except Exception:
            rate = 0.0

        if rate <= 1:
            rate *= 100

        min_l = adv.get("minSingleTransAmount", "0")
        max_l = adv.get("dynamicMaxSingleTransAmount", adv.get("maxSingleTransAmount", "0"))

        msg += (
            f"{i}️⃣ {price} DZD\n"
            f"👤 ⁠ {name} ⁠ | 👍 ⁠ {rate:.2f}% ⁠\n"
            f"💰 ⁠ {min_l} ⁠ - ⁠ {max_l} ⁠\n\n"
        )

    return msg


async def fetch_p2p(context: ContextTypes.DEFAULT_TYPE):
    global last_data_hash, last_alert_hash

    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    payload = {
        "asset": "USDT",
        "fiat": "DZD",
        "merchantCheck": False,
        "page": 1,
        "rows": 10,
        "tradeType": "SELL",
        "transAmount": current_amount
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        adverts = data.get("data", [])
        adverts = [a for a in adverts if not is_blocked_payment(a)]

        if show_price_filter > 0:
            filtered = []
            for a in adverts:
                try:
                    price = float(a["adv"]["price"])
                    if price >= show_price_filter:
                        filtered.append(a)
                except Exception:
                    pass
            adverts = filtered

        if not adverts:
            text = "⚠️ Aucun acheteur ne correspond aux paramètres actuels."
            current_hash = hashlib.md5(text.encode()).hexdigest()

            if current_hash != last_data_hash:
                last_data_hash = current_hash
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=text,
                    reply_markup=get_keyboard()
                )
            return

        try:
            adverts.sort(key=lambda a: float(a["adv"]["price"]), reverse=True)
        except Exception:
            pass

        status = "".join(
            f"{a['adv'].get('price', '')}{a['advertiser'].get('nickName', '')}"
            for a in adverts[:5]
        )
        current_hash = hashlib.md5(status.encode()).hexdigest()

        top_price = 0.0
        top_name = ""
        try:
            top_price = float(adverts[0]["adv"]["price"])
            top_name = adverts[0]["advertiser"].get("nickName", "")
        except Exception:
            pass

        if current_hash != last_data_hash:
            last_data_hash = current_hash
            msg = build_message(adverts)

            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown",
                reply_markup=get_keyboard()
            )

        if alert_price > 0 and top_price >= alert_price:
            alert_key = f"{top_price}-{top_name}"
            current_alert_hash = hashlib.md5(alert_key.encode()).hexdigest()

            if current_alert_hash != last_alert_hash:
                last_alert_hash = current_alert_hash
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f"🚨 Alerte de prix\n\n"
                        f"Un acheteur a atteint le prix d'alerte ou plus.\n\n"
                        f"💵 Prix : ⁠ {format_number(top_price)} DZD ⁠\n"
                        f"👤 Nom : ⁠ {top_name} ⁠"
                    ),
                    parse_mode="Markdown"
                )

    except Exception as e:
        print("ERROR:", e)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_amount, last_data_hash, last_alert_hash
    global show_price_filter, alert_price

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().replace(",", ".")

    if text == "0":
        show_price_filter = 0.0
        alert_price = 0.0
        last_data_hash = ""
        last_alert_hash = ""

        await update.message.reply_text("✅ Le prix d'affichage et le prix d'alerte ont été réinitialisés.")
        await fetch_p2p(context)
        return

    try:
        value = float(text)

        if 0 < value < 1000:
            if show_price_filter == 0:
                show_price_filter = value
                last_data_hash = ""
                last_alert_hash = ""
                await update.message.reply_text(
                    f"✅ Prix minimum d'affichage mis à jour à : {format_number(show_price_filter)} et plus"
                )
                await fetch_p2p(context)
                return

            if value >= show_price_filter:
                alert_price = value
                last_alert_hash = ""
                await update.message.reply_text(
                    f"🚨 Prix d'alerte mis à jour à : {format_number(alert_price)}"
                )
                await fetch_p2p(context)
                return

            show_price_filter = value
            if alert_price > 0 and alert_price < show_price_filter:
                alert_price = 0.0

            last_data_hash = ""
            last_alert_hash = ""
            await update.message.reply_text(
                f"✅ Prix minimum d'affichage mis à jour à : {format_number(show_price_filter)} et plus"
            )
            await fetch_p2p(context)
            return

    except Exception:
        pass

    if text.isdigit():
        current_amount = text
        last_data_hash = ""

        await update.message.reply_text(
            f"⚙️ Montant de recherche changé à {int(text):,} DZD"
        )
        await fetch_p2p(context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_amount, last_data_hash

    query = update.callback_query
    if not query:
        return

    await query.answer()

    if query.data.startswith("amt_"):
        current_amount = query.data.split("_")[1]

    last_data_hash = ""
    await fetch_p2p(context)


async def scan_callback(context: ContextTypes.DEFAULT_TYPE):
    await fetch_p2p(context)


def main():
    print("Bot started on Render...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    if app.job_queue:
        app.job_queue.run_repeating(scan_callback, interval=08, first=3)

    port = int(os.environ.get("PORT", 10000))

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
    )


if _name_ == "_main_":
    main()
