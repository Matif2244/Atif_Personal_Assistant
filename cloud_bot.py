import os
import json
import time
import asyncio
import firebase_admin
from firebase_admin import credentials, db
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask
import threading

# ==========================================
# CONFIGURATION
# ==========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FIREBASE_KEY_FILE = "atif-personal-assistant-firebase-adminsdk-fbsvc-f1a1415712.json"
FIREBASE_DB_URL = "https://atif-personal-assistant-default-rtdb.firebaseio.com/"

# ==========================================
# 1. DUMMY WEB SERVER (To Keep Cloud Alive)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Cloud Bot is Running 24/7!"

def run_web_server():
    # Render requires binding to a port provided by env var PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 2. AI & FIREBASE SETUP
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)

def get_model():
    try:
        all_models = list(genai.list_models())
        usable = [m for m in all_models if 'generateContent' in m.supported_generation_methods]
        
        selected = None
        # Priority: 1.5 Flash
        for m in usable:
            if "1.5" in m.name and "flash" in m.name:
                selected = m
                break
        if not selected: # Fallback
             selected = usable[0] if usable else None

        if selected:
            print(f"✅ Cloud Brain Active: {selected.name}")
            return genai.GenerativeModel(selected.name)
    except Exception as e:
        print(f"❌ AI Error: {e}")
    return None

model = get_model()

if not firebase_admin._apps:
    # Check if file exists, else try to create from ENV (For Cloud)
    if os.path.exists(FIREBASE_KEY_FILE):
        cred = credentials.Certificate(FIREBASE_KEY_FILE)
    else:
        # Fallback for Cloud (Agar file upload na ho to Env var se parho)
        # Filhal file upload method use karenge
        print("❌ Firebase Key File Not Found!")
        exit()
        
    firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})

# ==========================================
# 3. TELEGRAM BOT LOGIC
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text
    
    print(f"📩 Message: {text}")

    if not model:
        await update.message.reply_text("❌ AI Brain Error.")
        return

    # AI Processing
    prompt = f"""
    You are a Home Automation Bot. User said: "{text}"
    Classify intent: 'LAPTOP' (automation) or 'CHAT'.
    Output JSON: {{"intent": "...", "command": "...", "reply": "..."}}
    """
    try:
        response = model.generate_content(prompt)
        clean = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        
        if data.get("intent") == "LAPTOP":
            cmd = data.get("command")
            db.reference('task_queue').push({
                'command': cmd,
                'status': 'pending',
                'timestamp': int(time.time()),
                'from': user.first_name
            })
            await update.message.reply_text(f"✅ Order Sent: `{cmd}`")
        else:
            await update.message.reply_text(data.get("reply"))
            
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text("⚠️ Error processing request.")

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    # Start Web Server in Background (Thread)
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    
    print("🚀 Cloud Bot Started...")
    
    if not TELEGRAM_TOKEN:
        print("❌ Telegram Token Missing")
    else:
        app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        app_bot.run_polling()