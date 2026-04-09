import streamlit as st
import telebot
import requests
import json
import os
import time
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS

# --- 1. KONFIGURASI TAMPILAN (MAHASISWA KANAN, BOT KIRI) ---
st.set_page_config(page_title="Chatbot FT UGN", page_icon="🎓", layout="centered")

st.markdown("""
    <style>
    .stChatMessage { margin-bottom: 15px; border-radius: 15px; }
    /* Memastikan balon chat user terlihat rapi di kanan */
    </style>
""", unsafe_allow_html=True)

st.title("🎓 Smart Assistant Fakultas Teknik UGN")
st.caption("Pusat Layanan Informasi Digital - Pengembang: Putra Halomoan HSB")

# --- 2. AMBIL KUNCI DARI SECRETS ---
try:
    TOKEN = st.secrets["TELEGRAM_TOKEN"]
    OPENROUTER_KEY = st.secrets["OPENROUTER_API_KEY"]
    ADMIN_ID = int(st.secrets["ADMIN_CHAT_ID"])
except Exception as e:
    st.error(f"⚠️ Konfigurasi Secrets Bermasalah: {e}")
    st.stop()

DATA_FILE = "knowledge.json"
MODEL = "google/gemini-2.0-flash-001"

# --- 3. FUNGSI DATABASE (KNOWLEDGE) ---
def load_k():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_k(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 4. LOGIKA PINTAR & SOPAN SANTUN ---
def get_ai_response(user_msg):
    knowledge = load_k()
    base_reply = ""
    # Deteksi jika mahasiswa bertanya daftar/list
    is_list = any(w in user_msg.lower() for w in ["siapa aja", "siapa saja", "daftar", "dosen-dosen", "apa saja", "list"])

    # A. Cek Knowledge Base Lokal
    if knowledge:
        match = process.extractOne(user_msg.lower(), knowledge.keys(), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 85 and not is_list:
            base_reply = knowledge[match[0]]
        elif match and match[1] >= 70 and is_list:
            # Jika tanya daftar dan jawaban di DB panjang (>40 karakter), kita anggap lengkap
            if len(knowledge[match[0]]) > 40:
                base_reply = knowledge[match[0]]
            else: 
                base_reply = "[BUTUH_ADMIN]"
        else: 
            base_reply = "[BUTUH_ADMIN]"
    else: 
        base_reply = "[BUTUH_ADMIN]"

    # B. Jika di Database Tidak Ada -> Tanya AI & Internet
    if base_reply == "[BUTUH_ADMIN]":
        try:
            with DDGS(timeout=10) as ddgs:
                search = ddgs.text(f"Universitas Graha Nusantara Padangsidimpuan {user_msg}", max_results=2)
                context = "\n".join([r['body'] for r in search])
        except: context = ""

        prompt = (
            f"Kamu asisten resmi Fakultas Teknik UGN. Jawab seputar kampus saja. "
            f"Data pendukung: {context}. Jika pertanyaan di luar topik kampus, tolak dengan sangat sopan. "
            f"Jika informasi tidak lengkap atau kamu tidak tahu, JAWAB WAJIB: [TIDAK_TAHU]"
        )
        try:
            res = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={"model": MODEL, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}]},
                timeout=15
            )
            base_reply = res.json()['choices'][0]['message']['content']
        except: 
            return "Maaf Kak, server sedang sibuk. Silakan coba sebentar lagi ya! 😊"

    # C. Lapor Admin Jika Bot Bingung / Butuh Knowledge Baru
    if "[TIDAK_TAHU]" in base_reply or base_reply == "[BUTUH_ADMIN]":
        try:
            msg_ke_admin = f"⚠️ **BOT BUTUH BANTUAN!**\n\nUser Nanya: `{user_msg}`\n\nOpal, silakan tambahkan pengetahuan baru dengan balas format:\n`/tambah {user_msg} | Jawabannya`"
            bot.send_message(ADMIN_ID, msg_ke_admin, parse_mode="Markdown")
        except: pass
        return "Halo Kak! Saat ini asisten belum memiliki data lengkap mengenai hal itu. Pertanyaan Kakak sudah diteruskan ke Admin Fakultas Teknik untuk segera diperbarui. Silakan tanya hal lain ya! 😊"

    # D. Wrapper Kesopanan (Membuat jawaban singkat jadi ramah)
    prompt_sopan = (
        f"Ubah kalimat berikut menjadi jawaban asisten kampus yang sangat sopan, ramah, dan profesional. "
        f"Gunakan panggil 'Kak' atau 'Rekan Mahasiswa'. Jawaban: {base_reply}"
    )
    try:
        res_sopan = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt_sopan}]},
            timeout=10
        )
        return res_sopan.json()['choices'][0]['message']['content']
    except: 
        return base_reply

# --- 5. TELEGRAM BOT SETUP (ADMIN CONTROL) ---
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['tambah'])
def admin_tambah(m):
    if m.chat.id == ADMIN_ID:
        try:
            isi = m.text.replace('/tambah', '').strip()
            q, a = isi.split('|')
            d = load_k()
            d[q.strip().lower()] = a.strip()
            save_k(d)
            bot.reply_to(m, f"✅ **Pengetahuan Tersimpan!**\n\nSekarang bot sudah tahu jawaban untuk: *{q.strip()}*")
        except: 
            bot.reply_to(m, "❌ Format salah! Gunakan: `/tambah Tanya | Jawab`")

def start_bot():
    try:
        # Menghapus koneksi lama agar server Streamlit yang memegang kendali
        bot.remove_webhook()
        time.sleep(1)
        # Ping ke Opal untuk bukti bot nyala
        bot.send_message(ADMIN_ID, "🚀 **Bot Sistem FT-UGN Siap!** Jalur komunikasi website sudah aktif.")
        bot.infinity_polling(timeout=20)
    except: pass

# Jalankan bot di background thread
if "bot_active" not in st.session_state:
    Thread(target=start_bot, daemon=True).start()
    st.session_state.bot_active = True

# --- 6. ANTARMUKA CHAT (MAHASISWA) ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Tampilkan riwayat chat di website
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input pertanyaan dari Mahasiswa
if prompt := st.chat_input("Tulis pertanyaanmu seputar kampus di sini..."):
    # Tampilkan chat user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Proses jawaban bot
    with st.chat_message("assistant"):
        with st.spinner("Sedang memproses informasi..."):
            ans = get_ai_response(prompt)
            st.markdown(ans)
    st.session_state.messages.append({"role": "assistant", "content": ans})
