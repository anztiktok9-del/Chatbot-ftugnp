import streamlit as st
import telebot
import requests
import json
import os
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS
from datetime import datetime

# --- 1. KONFIGURASI TAMPILAN WEB STREAMLIT ---
st.set_page_config(page_title="Chatbot RAG UGN", page_icon="🤖")
st.title("🤖 Asisten Virtual Fakultas Teknik UGN")
st.markdown("---")
st.write("Status Server: **AKTIF ✅**")
st.write("Pengembang: **Putra Halomoan HSB**")

# --- 2. AMBIL KEY DARI SECRETS STREAMLIT ---
# Pastikan kamu sudah isi ini di menu Advanced Settings > Secrets di web Streamlit
try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    ADMIN_CHAT_ID = int(st.secrets["ADMIN_CHAT_ID"])
except Exception as e:
    st.error("⚠️ API Key/Secrets belum diatur dengan benar!")
    st.stop()

MODEL_NAME = "google/gemini-2.0-flash-001"
DATA_FILE = "knowledge.json"
LOG_FILE = "arsip_chat.json"

# --- 3. FUNGSI DATABASE LOKAL ---
def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {} if "knowledge" in filename else []
    return {} if "knowledge" in filename else []

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def simpan_ke_arsip(user_query, bot_reply):
    arsip = load_json(LOG_FILE)
    arsip.append({
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_query,
        "bot": bot_reply
    })
    save_json(LOG_FILE, arsip)

# --- 4. FUNGSI PENCARIAN & AI ---
def cari_internet(query):
    try:
        with DDGS(timeout=10) as ddgs:
            results = ddgs.text(query, max_results=2)
            return "\n".join([f"- {r['body']}" for r in results])
    except: return ""

def get_ai_response(user_msg):
    knowledge = load_json(DATA_FILE)
    
    # A. Cek Database Lokal (RAG Sederhana)
    if knowledge:
        match = process.extractOne(user_msg, knowledge.keys(), scorer=fuzz.token_set_ratio)
        if match and match[1] >= 65:
            res_lokal = knowledge[match[0]]
            simpan_ke_arsip(user_msg, res_lokal)
            return res_lokal

    # B. Lapor ke Telegram Admin jika tidak ada di database
    try:
        bot.send_message(ADMIN_CHAT_ID, f"❓ *USER NANYA:* {user_msg}")
    except: pass

    # C. Tanya AI Gemini via OpenRouter
    data_web = cari_internet(user_msg)
    prompt = (
        f"Kamu asisten UGN. Ramah, panggil 'Kak'. Jawab hanya seputar UGN/Fakultas Teknik. "
        f"Gunakan data ini jika relevan: {data_web}. "
        f"Jika ditanya di luar kampus, jawab: 'Maaf Kak, saya hanya dapat membantu seputar informasi UGN.' "
        f"Jika benar-benar buntu, jawab: MAAF_TIDAK_TAHU"
    )
    
    try:
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL_NAME, 
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_msg}
                ]
            },
            timeout=15
        )
        reply = res.json()['choices'][0]['message']['content'].strip()
        
        if "MAAF_TIDAK_TAHU" in reply:
            reply = "Halo Kak! Maaf asisten belum tahu jawabannya. Silakan cek pendaftaran di pmb.ugn.ac.id ya! 😊"
        
        simpan_ke_arsip(user_msg, reply)
        return reply
    except:
        return "Maaf Kak, server sedang sibuk. Coba lagi nanti ya!"

# --- 5. SETUP TELEGRAM BOT ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    bot.reply_to(message, "Halo Kak! Saya Asisten Virtual UGN (FT-UGN). Silakan tanya apa saja seputar kampus!")

@bot.message_handler(func=lambda message: True)
def handle_msg(message):
    if message.chat.id == ADMIN_CHAT_ID: return # Biar admin tidak menjawab dirinya sendiri
    bot.send_chat_action(message.chat.id, 'typing')
    response = get_ai_response(message.text)
    bot.reply_to(message, response)

# --- 6. JALANKAN BOT DI BACKGROUND (THREADING) ---
if "bot_running" not in st.session_state:
    bot_thread = Thread(target=bot.infinity_polling, daemon=True)
    bot_thread.start()
    st.session_state.bot_running = True

# --- 7. TAMPILAN LOG DI WEBSITE ---
st.subheader("📊 Log Percakapan Terbaru")
logs = load_json(LOG_FILE)
if logs:
    # Ambil 5 percakapan terakhir
    for chat in reversed(logs[-5:]):
        with st.expander(f"💬 {chat['user'][:30]}... ({chat['waktu']})"):
            st.write(f"**User:** {chat['user']}")
            st.write(f"**Bot:** {chat['bot']}")
else:
    st.info("Belum ada riwayat percakapan.")