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
CASHDESK_PAYOUT_API_URL = "https://e-depobet.com/v1/public/api/cashdesk/payout"

# Telegram bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Store admin chat IDs
ADMIN_CHAT_IDS = []

# States in the conversation
ASK_PHONE, ASK_AMOUNT, ASK_1XBET_ID, ASK_WITHDRAWAL_CODE, ADMIN_CONFIRMATION = range(5)

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

def send_cashdesk_payout_request(user_id: str, code: str) -> dict:
    """Send cashdesk payout request to the Laravel API."""
    payload = {
        "userId": user_id,
        "code": code,
        "language": "fr"
    }

    logging.debug(f"Sending cashdesk payout request with payload: {payload}")
    try:
        response = requests.post(CASHDESK_PAYOUT_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        api_response = response.json()
        logging.debug(f"Cashdesk Payout API response: {api_response}")
        return api_response
    except requests.exceptions.RequestException as e:
        logging.error(f"Cashdesk Payout API request failed: {e}")
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

        # Check for empty response with 200 OK
        if response.status_code == 200 and not response.text.strip():
            logging.debug("Withdrawal API returned empty response with 200 OK - treating as success")
            return {"status": "success", "message": "Withdrawal processed successfully"}
        
        response.raise_for_status()
        
        # Try to parse JSON response
        try:
            api_response = response.json()
            logging.debug(f"Withdrawal API parsed response: {api_response}")
            
            # Check for the specific success message
            if api_response.get("message") == "Transaction réalisée avec succès":
                return {"status": "success", "message": api_response.get("message")}
            
            return api_response
        except ValueError:
            # If response is not JSON but contains success message text
            if "Transaction réalisée avec succès" in response.text:
                return {"status": "success", "message": "Transaction réalisée avec succès"}
            else:
                logging.warning(f"Withdrawal API returned non-JSON response: {response.text}")
                return {"status": "error", "message": "Invalid response format from API"}
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Withdrawal API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"Error response status: {e.response.status_code}")
            logging.error(f"Error response content: {e.response.text}")
        return {"status": "error", "message": str(e)}

# Admin handlers
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a user as admin."""
    chat_id = update.effective_chat.id
    if chat_id not in ADMIN_CHAT_IDS:
        ADMIN_CHAT_IDS.append(chat_id)
        await update.message.reply_text("✅ Vous êtes maintenant enregistré comme administrateur.")
    else:
        await update.message.reply_text("Vous êtes déjà enregistré comme administrateur.")
    
    # Log admin registration
    logging.info(f"Admin registered with chat_id: {chat_id}")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all registered admins."""
    if not ADMIN_CHAT_IDS:
        await update.message.reply_text("Aucun administrateur n'est encore enregistré.")
        return
    
    admin_list = "\n".join([f"- Admin ID: {chat_id}" for chat_id in ADMIN_CHAT_IDS])
    await update.message.reply_text(f"Administrateurs enregistrés:\n{admin_list}")

async def send_to_admin(context: ContextTypes.DEFAULT_TYPE, user_data: dict) -> None:
    """Send withdrawal request to admin for confirmation."""
    admin_message = (
        f"🔄 Nouvelle demande de retrait:\n\n"
        f"📱 Téléphone: {user_data['phone_number']}\n"
        f"💰 Montant: {user_data['amount']}\n"
        f"🆔 ID 1xBET: {user_data['xbet_id']}\n"
        f"🔑 Code de retrait: {user_data['withdrawal_code']}\n\n"
        f"Pour confirmer, répondez avec le code: CONFIRM-{user_data['xbet_id']}"
    )
    
    # Store user chat_id in context for later use when admin confirms
    context.bot_data["pending_withdrawal"] = {
        "chat_id": context._user_id,
        "data": user_data
    }
    
    # Send to all registered admins
    sent = False
    for admin_chat_id in ADMIN_CHAT_IDS:
        try:
            await context.bot.send_message(chat_id=admin_chat_id, text=admin_message)
            logging.info(f"Withdrawal request sent to admin {admin_chat_id} for ID {user_data['xbet_id']}")
            sent = True
        except Exception as e:
            logging.error(f"Failed to send withdrawal request to admin {admin_chat_id}: {e}")
    
    # If no admins registered yet
    if not sent:
        logging.warning("No admin registered or failed to send withdrawal notifications")

async def process_admin_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process admin confirmation for withdrawal."""
    # Check if the sender is registered as an admin
    sender_chat_id = update.effective_chat.id
    if sender_chat_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ Vous n'êtes pas autorisé à confirmer les retraits. Contactez l'administrateur.")
        return
    
    # Check for confirmation code
    message_text = update.message.text
    if not message_text.startswith("CONFIRM-"):
        return
    
    try:
        confirmed_xbet_id = message_text.split("CONFIRM-")[1]
        
        # Check if there's a pending withdrawal with this ID
        pending = context.bot_data.get("pending_withdrawal")
        if not pending or pending["data"]["xbet_id"] != confirmed_xbet_id:
            await update.message.reply_text("❌ Aucune demande de retrait en attente avec cet ID.")
            return
        
        # Process the confirmed withdrawal
        user_data = pending["data"]
        chat_id = pending["chat_id"]
        
        # First call the cashdesk payout API
        cashdesk_payout_response = send_cashdesk_payout_request(
            user_data["xbet_id"], 
            user_data["withdrawal_code"]
        )
        
        if cashdesk_payout_response.get("status") == "success":
            await update.message.reply_text(
                f"✅ Retrait 1xBET confirmé! API: {cashdesk_payout_response.get('message', 'Succès')}"
            )
            
            # Now send the MoMo withdrawal request
            withdrawal_response = send_withdrawal_request(
                user_data["amount"], 
                user_data["phone_number"]
            )
            
            if withdrawal_response.get("status") == "success" or withdrawal_response.get("message") == "Transaction réalisée avec succès":
                await update.message.reply_text("✅ Retrait MoMo traité avec succès!")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Votre demande de retrait a été approuvée et traitée avec succès!"
                )
            else:
                error_msg = withdrawal_response.get("message", "Erreur inconnue")
                await update.message.reply_text(f"❌ Échec du retrait MoMo. Erreur: {error_msg}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Retrait 1xBET réussi mais échec du transfert MoMo. Contactez le support."
                )
        else:
            error_msg = cashdesk_payout_response.get("message", "Erreur inconnue")
            await update.message.reply_text(f"❌ Échec du retrait 1xBET. Erreur: {error_msg}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Votre demande de retrait a été rejetée. Vérifiez vos informations et réessayez."
            )
        
        # Clear the pending withdrawal
        context.bot_data.pop("pending_withdrawal", None)
        
    except Exception as e:
        logging.error(f"Error processing admin confirmation: {e}")
        await update.message.reply_text(f"❌ Erreur lors du traitement: {str(e)}")

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
            
            # Check for the specific success message (with correct accents)
            if api_response.get("message") == "Paiement effectué avec succès":
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
        
        # Store the current user's chat_id for admin confirmation
        context._user_id = update.effective_chat.id
        
        # Check if we have any admins registered
        if not ADMIN_CHAT_IDS:
            await update.message.reply_text(
                "⚠️ Aucun administrateur n'est enregistré pour traiter les retraits.\n"
                "Veuillez contacter le support technique."
            )
            return ConversationHandler.END
        
        # Send information to admin for confirmation
        await send_to_admin(context, context.user_data)
        
        await update.message.reply_text(
            "✅ Votre demande de retrait a été envoyée à l'administrateur pour validation.\n"
            "Vous recevrez une notification dès que votre demande sera traitée."
        )
        
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
    
    # Add admin handlers
    application.add_handler(CommandHandler("admin_register", register_admin))
    application.add_handler(CommandHandler("list_admins", list_admins))
    
    # Add conversation handler
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
    
    # Add handler for admin confirmations
    application.add_handler(MessageHandler(filters.Regex(r"^CONFIRM-\d+$"), process_admin_confirmation))
    
    application.run_polling()

if __name__ == "__main__":
    main()
