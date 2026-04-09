import streamlit as st
import telebot
import requests
import json
import os
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS
from datetime import datetime

# --- 1. SETTING HALAMAN ---
st.set_page_config(page_title="Chatbot FT UGN", page_icon="🎓", layout="centered")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stChatMessage { border-radius: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

st.title("🎓 Layanan Informasi Akademik FT-UGN")
st.info("Selamat datang Kak! Silakan tanya seputar informasi kampus UGN di bawah ini.")

# --- 2. KONFIGURASI KUNCI ---
try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    ADMIN_CHAT_ID = int(st.secrets["ADMIN_CHAT_ID"])
except:
    st.error("⚠️ Secrets belum diatur!")
    st.stop()

MODEL_NAME = "google/gemini-2.0-flash-001"
DATA_FILE = "knowledge.json"

# --- 3. FUNGSI DATABASE ---
def load_knowledge():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_knowledge(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 4. LOGIKA PINTAR BOT (UNTUK WEBSITE) ---
def get_response(user_msg):
    knowledge = load_knowledge()
    
    # Cek Database yang sudah ditambah Admin via Telegram
    if knowledge:
        match = process.extractOne(user_msg, knowledge.keys(), scorer=fuzz.token_set_ratio)
        if match and match[1] >= 70:
            return knowledge[match[0]]

    # Jika tidak ada, tanya AI Gemini
    try:
        with DDGS(timeout=10) as ddgs:
            search = ddgs.text(f"info kampus UGN {user_msg}", max_results=2)
            context = "\n".join([r['body'] for r in search])
    except: context = ""

    prompt = f"Kamu asisten UGN. Ramah. Jawab seputar kampus. Info: {context}. Jika buntu jawab: MAAF_TIDAK_TAHU"
    
    try:
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": MODEL_NAME, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}]}
        )
        reply = res.json()['choices'][0]['message']['content']
        return "Maaf Kak, asisten belum tahu jawabannya. Silakan cek pendaftaran di pmb.ugn.ac.id ya! 😊" if "MAAF_TIDAK_TAHU" in reply else reply
    except: return "Server sibuk, Kak!"

# --- 5. TELEGRAM KHUSUS ADMIN (TAMBAH KNOWLEDGE) ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start'])
def welcome_admin(message):
    if message.chat.id == ADMIN_CHAT_ID:
        bot.reply_to(message, "Halo Admin **Opal**! 🛠️\n\nKirim format: `/tambah Tanya | Jawab` untuk isi otak bot.")

@bot.message_handler(commands=['tambah'])
def tambah_data(message):
    if message.chat.id == ADMIN_CHAT_ID:
        try:
            isi = message.text.replace('/tambah', '').strip()
            q, a = isi.split('|')
            data = load_knowledge()
            data[q.strip().lower()] = a.strip()
            save_knowledge(data)
            bot.reply_to(message, f"✅ Berhasil! Sekarang bot tahu tentang: *{q.strip()}*")
        except:
            bot.reply_to(message, "❌ Salah format! Gunakan: `/tambah Tanya | Jawab`")

if "bot_running" not in st.session_state:
    Thread(target=bot.infinity_polling, daemon=True).start()
    st.session_state.bot_running = True

# --- 6. TAMPILAN CHAT WEBSITE (MAHASISWA) ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Munculkan chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input Chat
if prompt := st.chat_input("Ketik pertanyaanmu di sini..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response = get_response(prompt)
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})

st.sidebar.markdown(f"---")
st.sidebar.write("**Admin Control:**")
st.sidebar.write("Gunakan Telegram untuk menambah database pertanyaan.")