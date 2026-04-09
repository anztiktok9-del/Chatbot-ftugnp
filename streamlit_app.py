import streamlit as st
import telebot
import requests
import json
import os
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS
from datetime import datetime

# --- 1. KONFIGURASI TAMPILAN ---
st.set_page_config(page_title="Chatbot FT UGN", page_icon="🎓", layout="centered")

# CSS untuk membedakan balon chat (Mahasiswa Kanan, Bot Kiri)
st.markdown("""
    <style>
    .stChatMessage { margin-bottom: 15px; border-radius: 15px; }
    /* Memastikan input chat tetap rapi */
    .stChatInputContainer { padding-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.title("🎓 Smart Assistant Fakultas Teknik UGN")
st.caption("Pusat Layanan Informasi Digital - Pengembang: Putra Halomoan HSB")

# --- 2. KONFIGURASI KUNCI (SECRETS) ---
try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    ADMIN_CHAT_ID = int(st.secrets["ADMIN_CHAT_ID"])
except:
    st.error("⚠️ Secrets belum diatur di Dashboard Streamlit!")
    st.stop()

MODEL_NAME = "google/gemini-2.0-flash-001"
DATA_FILE = "knowledge.json"

# --- 3. FUNGSI DATABASE ---
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

# --- 4. LOGIKA PINTAR & PENANGANAN PERTANYAAN ---
def get_response(user_msg):
    knowledge = load_knowledge()
    base_reply = ""
    is_from_knowledge = False
    
    # Kata kunci untuk mendeteksi pertanyaan "Daftar" (List)
    kata_kunci_jamak = ["siapa saja", "siapa aja", "daftar", "dosen-dosen", "apa saja", "list"]
    apakah_nanya_daftar = any(word in user_msg.lower() for word in kata_kunci_jamak)

    # A. CEK KNOWLEDGE BASE (RAG LOKAL)
    if knowledge:
        # Gunakan scorer yang lebih teliti (token_sort_ratio)
        match = process.extractOne(user_msg.lower(), knowledge.keys(), scorer=fuzz.token_sort_ratio)
        
        # Jika kemiripan sangat tinggi (>85%) dan BUKAN pertanyaan daftar
        if match and match[1] >= 85 and not apakah_nanya_daftar:
            base_reply = knowledge[match[0]]
            is_from_knowledge = True
        # Jika kemiripan tinggi tapi user nanya daftar, kita cek apakah jawaban di DB panjang (berupa list)
        elif match and match[1] >= 65 and apakah_nanya_daftar:
            if len(knowledge[match[0]]) > 50: # Asumsi kalau jawaban panjang berarti itu daftar
                base_reply = knowledge[match[0]]
                is_from_knowledge = True
            else:
                base_reply = "[INFO_KURANG_LENGKAP]"

    # B. JIKA TIDAK ADA DI LOKAL / KURANG LENGKAP -> TANYA AI & INTERNET
    if not is_from_knowledge or base_reply == "[INFO_KURANG_LENGKAP]":
        try:
            with DDGS(timeout=10) as ddgs:
                # Fokus pencarian spesifik ke UGN
                search = ddgs.text(f"daftar dosen Fakultas Teknik Universitas Graha Nusantara Padangsidimpuan", max_results=3)
                context = "\n".join([r['body'] for r in search])
        except: context = ""

        prompt_ai = (
            f"Kamu asisten resmi Fakultas Teknik UGN. "
            f"TUGAS: Jawab seputar kampus UGN/FT saja. Data pendukung: {context}. "
            f"PENTING: Jika user nanya daftar dosen tapi data tidak lengkap, jawab: [TIDAK_TAHU]. "
            f"Jika pertanyaan di luar kampus, jawab dengan menolak sopan. "
            f"Jika kamu tidak punya data pasti, jangan mengarang nama orang, jawab: [TIDAK_TAHU]"
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
            return "Maaf Kak, server sedang sibuk. Silakan coba sebentar lagi ya! 😊"

    # C. HANDLING LAPOR KE ADMIN TELEGRAM (Jika Bot Bingung)
    if "[TIDAK_TAHU]" in base_reply or base_reply == "[INFO_KURANG_LENGKAP]":
        msg_admin = f"⚠️ **BOT BUTUH BANTUAN!**\n\nUser Nanya: `{user_msg}`\n\nOpal, silakan tambahkan data lengkapnya:\n`/tambah {user_msg} | Jawaban Lengkap Kamu`"
        bot.send_message(ADMIN_CHAT_ID, msg_admin, parse_mode="Markdown")
        return "Tentu Kak! Untuk informasi tersebut, asisten sedang melakukan pembaruan data dengan pihak Akademik FT-UGN agar jawabannya akurat. Pertanyaan Kakak sudah diteruskan ke Admin. Ada lagi yang bisa asisten bantu? 😊"

    # D. POLES KESOPANAN (RE-WRITING)
    prompt_sopan = (
        f"Ubah teks berikut menjadi jawaban asisten kampus yang sangat sopan, ramah, dan profesional. "
        f"Gunakan panggil 'Kak' atau 'Rekan Mahasiswa'. Teks: {base_reply}"
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
        return base_reply

# --- 5. TELEGRAM KHUSUS ADMIN (UPDATE KNOWLEDGE) ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['tambah'])
def tambah_data(message):
    if message.chat.id == ADMIN_CHAT_ID:
        try:
            isi = message.text.replace('/tambah', '').strip()
            q, a = isi.split('|')
            data = load_knowledge()
            # Simpan pertanyaan dalam huruf kecil agar mudah dicocokkan
            data[q.strip().lower()] = a.strip()
            save_knowledge(data)
            bot.reply_to(message, f"✅ **Berhasil Disimpan!**\n\nKini asisten sudah tahu tentang: *{q.strip()}*")
        except:
            bot.reply_to(message, "❌ Format salah! Gunakan: `/tambah Pertanyaan | Jawaban`")

# Jalankan Bot Telegram di thread terpisah
if "bot_started" not in st.session_state:
    Thread(target=bot.infinity_polling, daemon=True).start()
    st.session_state.bot_started = True

# --- 6. ANTARMUKA CHAT (MAHASISWA) ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Tampilkan riwayat chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input pertanyaan Mahasiswa
if prompt := st.chat_input("Tulis pertanyaanmu di sini..."):
    # Simpan dan tampilkan chat user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Proses dan tampilkan respon bot
    with st.chat_message("assistant"):
        with st.spinner("Mencari informasi resmi..."):
            final_answer = get_response(prompt)
            st.markdown(final_answer)
    st.session_state.messages.append({"role": "assistant", "content": final_answer})