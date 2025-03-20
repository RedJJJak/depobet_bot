import logging
import requests
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
import re

# Configure logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG)

# Laravel Payment API configuration
DEPOSIT_API_URL = "https://e-depobet.com/v1/public/api/process-payment"
WITHDRAWAL_API_URL = "https://e-depobet.com/v1/public/api/transfer"
CASHDESK_DEPOSIT_API_URL = "https://e-depobet.com/v1/public/api/cashdesk/deposit"

# Telegram bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# States in the conversation
ASK_PHONE, ASK_AMOUNT, ASK_1XBET_ID, ASK_WITHDRAWAL_CODE = range(4)

# Validators
def validate_phone_number(phone_number: str) -> bool:
    """Validate an international phone number."""
    return bool(re.match(r"^\+\d{10,15}$", phone_number))

def validate_amount(amount: str) -> bool:
    """Validate the amount is a number and within range."""
    try:
        value = int(amount)
        return 100 <= value <= 500000
    except ValueError:
        return False

def validate_1xbet_id(xbet_id: str) -> bool:
    """Validate 1xBET ID as a 6–10 digit number."""
    return bool(re.match(r"^\d{6,10}$", xbet_id))

def validate_withdrawal_code(code: str) -> bool:
    """Validate withdrawal code: 4 chars max, letters and digits only."""
    return bool(re.match(r"^[a-zA-Z0-9]{1,4}$", code))

def send_deposit_request(amount: int, phone_number: str) -> dict:
    """Send deposit request to the Laravel API."""
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]

    payload = {
        "amount": str(amount),
        "externalId": "12345678",
        "email": "exemple@gmail.com",
        "nompre": "Lux",
        "payer": {"partyIdType": "MSISDN"},
        "country_code": "bj",
        "partyId": phone_number,
        "payerMessage": "Paiement pour service",
        "payeeNote": "Commande de service",
    }

    logging.debug(f"Sending deposit request with payload: {payload}")
    try:
        response = requests.post(DEPOSIT_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        api_response = response.json()
        logging.debug(f"Deposit API response: {api_response}")
        return api_response
    except requests.exceptions.RequestException as e:
        logging.error(f"Deposit API request failed: {e}")
        return {"status": "error", "message": str(e)}

def send_cashdesk_deposit_request(user_id: str, amount: int) -> dict:
    """Send cashdesk deposit request to the Laravel API."""
    payload = {
        "userId": user_id,
        "amount": float(amount),
        "language": "fr"
    }

    logging.debug(f"Sending cashdesk deposit request with payload: {payload}")
    try:
        response = requests.post(CASHDESK_DEPOSIT_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        api_response = response.json()
        logging.debug(f"Cashdesk Deposit API response: {api_response}")
        return api_response
    except requests.exceptions.RequestException as e:
        logging.error(f"Cashdesk Deposit API request failed: {e}")
        return {"status": "error", "message": str(e)}

def send_withdrawal_request(amount: int, phone_number: str) -> dict:
    """Send withdrawal request to the Laravel API."""
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]

    payload = {
        "amount": str(amount),
        "partyId": phone_number
    }

    logging.debug(f"Sending withdrawal request with payload: {payload}")
    try:
        response = requests.post(WITHDRAWAL_API_URL, json=payload, timeout=60)
        logging.debug(f"Withdrawal API status code: {response.status_code}")
        logging.debug(f"Withdrawal API raw response: '{response.text}'")

        if response.status_code == 200 and not response.text.strip():  # Empty response with 200 OK
            logging.debug("Withdrawal API returned empty response with 200 OK - treating as success")
            return {"status": "success", "message": "Withdrawal processed successfully"}
        
        response.raise_for_status()
        api_response = response.json()
        logging.debug(f"Withdrawal API parsed response: {api_response}")
        return api_response
    except requests.exceptions.RequestException as e:
        logging.error(f"Withdrawal API request failed: {e}")
        return {"status": "error", "message": str(e)}

# Handlers
async def greet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Greet the user with inline buttons."""
    logging.info("Greet function called")
    keyboard = [[InlineKeyboardButton("Depo (Deposit)", callback_data="deposit")],
                [InlineKeyboardButton("Retrait (Withdraw)", callback_data="withdraw")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bienvenue! Veuillez choisir une option ci-dessous.", reply_markup=reply_markup)
    return ASK_PHONE

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline button actions."""
    query = update.callback_query
    await query.answer()
    context.user_data["action"] = query.data
    await query.edit_message_text("Veuillez entrer votre numéro de téléphone au format international (+2290123456789).")
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the phone number."""
    phone_number = update.message.text
    if validate_phone_number(phone_number):
        context.user_data["phone_number"] = phone_number
        action_text = "déposer" if context.user_data["action"] == "deposit" else "retirer"
        await update.message.reply_text(f"Merci! Combien voulez-vous {action_text}? (Entre 100 et 500000)")
        return ASK_AMOUNT
    await update.message.reply_text("Numéro invalide. Veuillez entrer un numéro valide (+1234567890).")
    return ASK_PHONE

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the transaction amount."""
    amount = update.message.text
    if validate_amount(amount):
        context.user_data["amount"] = int(amount)
        await update.message.reply_text("Merci! Veuillez entrer votre ID 1xBET (6 à 10 chiffres).")
        return ASK_1XBET_ID
    await update.message.reply_text("Montant invalide. Veuillez entrer un montant entre 100 et 500000.")
    return ASK_AMOUNT

async def ask_1xbet_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the 1xBET ID and proceed based on action."""
    xbet_id = update.message.text
    if validate_1xbet_id(xbet_id):
        context.user_data["xbet_id"] = xbet_id
        if context.user_data["action"] == "deposit":
            phone_number = context.user_data["phone_number"]
            amount = context.user_data["amount"]
            
            # First API call - process payment
            api_response = send_deposit_request(amount, phone_number)
            
            # Check for the specific success message
            if api_response.get("status") == "success" and api_response.get("message") == "Paiement effectue avec succes":
                await update.message.reply_text("✅ Paiement MoMo réussi! Traitement du crédit sur votre compte 1xBET...")
                
                # Now proceed with the cashdesk API call
                cashdesk_response = send_cashdesk_deposit_request(xbet_id, amount)
                
                if cashdesk_response.get("status") == "success":
                    await update.message.reply_text(
                        f"✅ Crédit sur compte 1xBET réussi!\n"
                        f"Message de l'API: {cashdesk_response.get('message', 'Succès')}"
                    )
                else:
                    error_message = cashdesk_response.get("message", "Erreur inconnue.")
                    await update.message.reply_text(
                        f"⚠️ Échec du crédit sur compte 1xBET!\n"
                        f"Message de l'API: {error_message}\n"
                        f"Veuillez contacter le support avec votre ID 1xBET: {xbet_id}"
                    )
            else:
                status_message = api_response.get("message", "Erreur inconnue.")
                await update.message.reply_text(f"❌ Échec du paiement MoMo. Message: {status_message}")
            
            return ConversationHandler.END
        else:  # withdrawal
            await update.message.reply_text("Merci! Veuillez entrer votre code de retrait (4 caractères max, lettres et chiffres).")
            return ASK_WITHDRAWAL_CODE
    await update.message.reply_text("ID 1xBET invalide. Veuillez entrer un ID valide (6 à 10 chiffres).")
    return ASK_1XBET_ID

async def ask_withdrawal_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the withdrawal code and process the withdrawal."""
    withdrawal_code = update.message.text
    if validate_withdrawal_code(withdrawal_code):
        context.user_data["withdrawal_code"] = withdrawal_code
        phone_number = context.user_data["phone_number"]
        amount = context.user_data["amount"]
        api_response = send_withdrawal_request(amount, phone_number)
        action_text = "Retrait"
        
        if api_response.get("status") == "success":
            await update.message.reply_text(f"✅ {action_text} réussi! Réponse API : {api_response.get('message', 'Succès')}")
        else:
            error_message = api_response.get("message", "Erreur inconnue.")
            await update.message.reply_text(f"❌ Échec du {action_text.lower()}. Message de l'API : {error_message}")
        return ConversationHandler.END
    
    await update.message.reply_text("Code de retrait invalide. Veuillez entrer un code valide (4 caractères max, lettres et chiffres).")
    return ASK_WITHDRAWAL_CODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("🚫 Transaction annulée. Tapez DepoBet pour réessayer.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Main function
def main() -> None:
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"(?i)^depobet$"), greet)],
        states={
            ASK_PHONE: [CallbackQueryHandler(handle_action), MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_1XBET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_1xbet_id)],
            ASK_WITHDRAWAL_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_withdrawal_code)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
