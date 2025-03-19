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
CASHDESK_DEPOSIT_API_URL = "https://e-depobet.com/v1/public/api/cashdesk/deposit"
WITHDRAWAL_API_URL = "https://e-depobet.com/v1/public/api/transfer"

# Telegram bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# States in the conversation
ASK_PHONE, ASK_AMOUNT, ASK_1XBET_ID, ASK_WITHDRAWAL_CODE = range(4)

# Function to call the new cashdesk deposit API
def send_cashdesk_deposit_request(user_id: int, amount: float) -> dict:
    """Send deposit request to the new cashdesk deposit API."""
    payload = {
        "userId": user_id,
        "amount": amount,
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

# Modify the deposit request function to include the second API call
def send_deposit_request(amount: int, phone_number: str, xbet_id: int) -> dict:
    """Send deposit request to the Laravel API and then call the new cashdesk deposit API."""
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
        
        if api_response.get("status") == "success":
            # Call the new cashdesk deposit API
            cashdesk_response = send_cashdesk_deposit_request(int(xbet_id), float(amount))
            return cashdesk_response
        
        return api_response
    except requests.exceptions.RequestException as e:
        logging.error(f"Deposit API request failed: {e}")
        return {"status": "error", "message": str(e)}

# Modify the ask_1xbet_id handler to include the new API call
async def ask_1xbet_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the 1xBET ID and proceed based on action."""
    xbet_id = update.message.text
    if re.match(r"^\d{6,10}$", xbet_id):
        context.user_data["xbet_id"] = xbet_id
        if context.user_data["action"] == "deposit":
            phone_number = context.user_data["phone_number"]
            amount = context.user_data["amount"]
            api_response = send_deposit_request(amount, phone_number, xbet_id)
            action_text = "Paiement"
            
            if api_response.get("status") == "success":
                await update.message.reply_text(f"✅ {action_text} réussi! Réponse API : {api_response.get('message', 'Succès')}")
            else:
                error_message = api_response.get("message", "Erreur inconnue.")
                await update.message.reply_text(f"❌ Échec du {action_text.lower()}. Message de l'API : {error_message}")
            return ConversationHandler.END
        else:  # withdrawal
            await update.message.reply_text("Merci! Veuillez entrer votre code de retrait (4 caractères max, lettres et chiffres).")
            return ASK_WITHDRAWAL_CODE
    await update.message.reply_text("ID 1xBET invalide. Veuillez entrer un ID valide (6 à 10 chiffres).")
    return ASK_1XBET_ID
