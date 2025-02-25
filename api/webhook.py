from http.server import BaseHTTPRequestHandler
import os
import json
import asyncio
import requests
import datetime
from telebot.async_telebot import AsyncTeleBot  
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv


load_dotenv()
# Initialize bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
print(BOT_TOKEN)
bot = AsyncTeleBot(BOT_TOKEN)

# Initializee Firebase

firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "hullu-25607.firebasestorage.app"})
db = firestore.client()
bucket = storage.bucket()


def generate_start_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Order Now", web_app=WebAppInfo(url="https://tg-store.vercel.app/")))
    return keyboard


@bot.message_handler(commands=['start'])  
async def start(message):
    user_id = str(message.from_user.id)  
    user_first_name = str(message.from_user.first_name)  
    user_last_name = message.from_user.last_name
    user_username = message.from_user.username
    user_language_code = str(message.from_user.language_code)
    is_premium = message.from_user.is_premium
    text = message.text.split()
    welcome_message = (  
        f"Hello {user_first_name} {user_last_name}! 👋\n\n"
        f"Welcome to Hulu Delivery.\n\n"
        f"collect points and order Products!\n\n"
        f"Invite friends to earn more points! 🧨\n"
    )

    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
        

            # Prepare user data
            user_data = {
                'userImage': None,
                'firstName': user_first_name,
                'lastName': user_last_name,
                'username': user_username,
                'languageCode': user_language_code,
                'isPremium': is_premium,
                'phone':None,
                'balance': 0,
                'daily': {
                    'claimedTime': None,
                    'claimedDay': 0
                },
                  
            }

            if len(text) > 1 and text[1].startswith('ref_'):   
                referrer_id = text[1][4:]
                referrer_ref = db.collection('users').document(referrer_id)
                referrer_doc = referrer_ref.get()

                if referrer_doc.exists:
                    user_data['referredBy'] = referrer_id
                    referrer_data = referrer_doc.to_dict()
                    bonus_amount = 500 if is_premium else 100
                    current_balance = referrer_data.get('balance', 0)
                    new_balance = current_balance + bonus_amount

                    referrals = referrer_data.get('referrals', {})
                    if referrals is None:
                        referrals = {}
                    referrals[user_id] = {
                        'addedValue': bonus_amount,
                        'firstName': user_first_name,
                        'lastName': user_last_name,
                        'userImage': None,
                    }  

                    referrer_ref.update({
                        'balance': new_balance,
                        'referrals': referrals
                    })
                else:
                    user_data['referredBy'] = None

            user_ref.set(user_data)

        keyboard = generate_start_keyboard()
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)  
    except Exception as e:
        error_message = "Error. Please try again!"
        await bot.reply_to(message, error_message)  
        print(f"Error occurred: {str(e)}")  

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # Handle CORS preflight request
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "https://d2bf-185-183-33-220.ngrok-free.app")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])  
        post_data = self.rfile.read(content_length)
        request_path = self.path  
        
        if request_path == "/api/create-order":
            self.create_order(post_data)
        else:
            update_dict = json.loads(post_data.decode('utf-8'))
            asyncio.run(self.process_update(update_dict))

        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")  
        self.end_headers()

def create_order(self, post_data):
    try:
        order_data = json.loads(post_data.decode('utf-8'))
        print("Received order data:", order_data)  

        # Extract order details
        user_id = order_data.get("userId")
        items = order_data.get("items", [])
        total_price = order_data.get("totalPrice")
        payment_method = order_data.get("paymentMethod", "Not specified")  

        # Validate required fields
        if not user_id or not isinstance(items, list) or len(items) == 0 or total_price is None:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing required fields (userId, items, or totalPrice)"}).encode("utf-8"))
            return

        # Create an order document in Firestore
        order_ref = db.collection("orders").document()
        order_ref.set({
            "userId": user_id,
            "items": items,
            "totalPrice": total_price,
            "paymentMethod": payment_method,
            "status": "pending",
            "createdAt": datetime.datetime.utcnow().isoformat(),
        })

        # Notify the admin
        admin_id = 386095768
        item_list = "\n".join([f"- {item.get('name', 'Unknown Item')} (x{item.get('quantity', 1)})" for item in items])
        order_message = (
            f"📦 *New Order Received!*\n\n"
            f"👤 *User ID:* `{user_id}`\n"
            f"🛒 *Items:*\n{item_list}\n"
            f"💰 *Total Price:* {total_price}\n"
            f"💳 *Payment Method:* {payment_method}\n\n"
            f"✅ Please review and accept the order."
        )

        asyncio.run(bot.send_message(admin_id, order_message, parse_mode="Markdown"))

        # Send success response
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"message": "Order created successfully"}).encode("utf-8"))

    except json.JSONDecodeError:
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Invalid JSON format"}).encode("utf-8"))

    except Exception as e:
        print(f"Error occurred: {str(e)}")  # Log error
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    async def process_update(self, update_dict):
        update = types.Update.de_json(update_dict)
        await bot.process_new_updates([update])

    def do_GET(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write('Hello, BOT is running!'.encode('utf-8'))
