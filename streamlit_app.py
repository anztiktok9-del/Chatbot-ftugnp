import streamlit as st
import telebot
import requests
import json
import os
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS
from datetime import datetime

# --- 1. SETTING UI (Mahasiswa Kanan, Bot Kiri) ---
st.set_page_config(page_title="Chatbot FT UGN", page_icon="🎓", layout="centered")

st.markdown("""
    <style>
    /* Mengatur balon chat user agar di kanan (secara visual di Streamlit versi terbaru sudah otomatis, tapi ini penguat) */
    .stChatMessage { margin-bottom: 15px; border-radius: 15px; }
    .st-emotion-cache-janfss { flex-direction: row-reverse; text-align: right; } /* User ke kanan */
    </style>
""", unsafe_allow_html=True)

st.title("🎓 Smart Assistant Fakultas Teknik UGN")
st.caption("Pusat Informasi Akademik Digital - Dikembangkan oleh: Putra Halomoan HSB")

# --- 2. KONFIGURASI SECRETS ---
try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    ADMIN_CHAT_ID = int(st.secrets["ADMIN_CHAT_ID"])
except:
    st.error("⚠️ Konfigurasi Secrets (Token/API Key) belum lengkap!")
    st.stop()

MODEL_NAME = "google/gemini-2.0-flash-001"
DATA_FILE = "knowledge.json"

# --- 3. FUNGSI DATABASE (KNOWLEDGE) ---
def load_knowledge():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_knowledge(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 4. LOGIKA PINTAR & KESOPANAN ---
def get_response(user_msg):
    knowledge = load_knowledge()
    base_reply = ""
    is_from_knowledge = False
    
    # A. Cek Knowledge Base (Fuzzy Matching agar 1 info bisa buat banyak pertanyaan)
    if knowledge:
        # Mencari kemiripan kata kunci (misal: "Ibu Noni" atau "Dekan Teknik")
        match = process.extractOne(user_msg, knowledge.keys(), scorer=fuzz.token_set_ratio)
        if match and match[1] >= 70:
            base_reply = knowledge[match[0]]
            is_from_knowledge = True

    # B. Jika tidak ada di Knowledge, baru tanya AI + Search
    if not is_from_knowledge:
        try:
            with DDGS(timeout=10) as ddgs:
                search = ddgs.text(f"Universitas Graha Nusantara {user_msg}", max_results=2)
                context = "\n".join([r['body'] for r in search])
        except: context = "Tidak ada data internet."

        prompt_ai = (
            f"Kamu asisten resmi Fakultas Teknik UGN. "
            f"TUGAS: Jawab HANYA seputar UGN/FT. Info tambahan: {context}. "
            f"Jika pertanyaan di luar kampus, jawab dengan sangat sopan bahwa kamu hanya asisten kampus. "
            f"Jika kamu benar-benar tidak tahu infonya, JAWAB: [TIDAK_TAHU]"
        )
        
        try:
            res = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": MODEL_NAME, "messages": [{"role": "system", "content": prompt_ai}, {"role": "user", "content": user_msg}]},
                timeout=15
            )
            base_reply = res.json()['choices'][0]['message']['content']
        except:
            return "Maaf Kak, koneksi server sedang sibuk. Silakan coba sesaat lagi ya! 😊"

    # C. Handling jika TIDAK TAHU (Kirim ke Telegram)
    if "[TIDAK_TAHU]" in base_reply or not base_reply:
        msg_admin = f"⚠️ **ADA PERTANYAAN BARU:**\n\nUser: `{user_msg}`\n\nOpal, silakan balas dengan format:\n`/tambah {user_msg} | Jawabannya`"
        bot.send_message(ADMIN_CHAT_ID, msg_admin, parse_mode="Markdown")
        return "Halo Kak! Maaf, saat ini asisten belum memiliki data tersebut. Pertanyaan Kakak sudah diteruskan ke Admin Fakultas Teknik untuk segera diperbarui. Silakan tanya hal lain ya! 😊"

    # D. WRAPPER KESOPANAN (Membuat jawaban singkat jadi sopan)
    # Ini supaya jawaban "Ibu Noni dekan" jadi "Tentu Kak, Ibu Noni adalah Dekan Fakultas Teknik UGN..."
    prompt_sopan = (
        f"Ubah jawaban berikut menjadi kalimat yang sangat sopan, ramah, dan profesional sebagai asisten kampus UGN. "
        f"Jangan menambah informasi palsu. Jawaban: {base_reply}"
    )
    
    try:
        res_sopan = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt_sopan}]},
            timeout=10
        )
        return res_sopan.json()['choices'][0]['message']['content']
    except:
        return base_reply # Jika AI sopan gagal, kirim jawaban asli saja

# --- 5. TELEGRAM KHUSUS ADMIN OPAL ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['tambah'])
def tambah_data(message):
    if message.chat.id == ADMIN_CHAT_ID:
        try:
            isi = message.text.replace('/tambah', '').strip()
            q, a = isi.split('|')
            data = load_knowledge()
            data[q.strip().lower()] = a.strip()
            save_knowledge(data)
            bot.reply_to(message, f"✅ **Data Tersimpan!**\n\nSekarang bot sudah tahu jawaban untuk: *{q.strip()}*")
        except:
            bot.reply_to(message, "❌ Gagal! Format: `/tambah Tanya | Jawab`")

def run_bot():
    bot.infinity_polling()

if "bot_thread" not in st.session_state:
    st.session_state.bot_thread = Thread(target=run_bot, daemon=True)
    st.session_state.bot_thread.start()

# --- 6. TAMPILAN CHAT (MAHASISWA) ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Tampilkan history chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input Chat
if prompt := st.chat_input("Apa yang ingin kamu ketahui tentang FT UGN?"):
    # Tampilkan chat user (kanan)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Tampilkan chat bot (kiri)
    with st.chat_message("assistant"):
        with st.spinner("Sedang mengetik..."):
            answer = get_response(prompt)
            st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})