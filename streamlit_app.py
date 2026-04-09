import streamlit as st
import telebot
import requests
import json
import os
import time
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS

# --- 1. SETTING UI (Mahasiswa Kanan, Bot Kiri) ---
st.set_page_config(page_title="Chatbot FT UGN", page_icon="🎓", layout="centered")

st.markdown("""
    <style>
    .stChatMessage { margin-bottom: 15px; border-radius: 15px; }
    </style>
""", unsafe_allow_html=True)

st.title("🎓 Smart Assistant Fakultas Teknik UGN")
st.caption("Dikembangkan oleh: Putra Halomoan HSB")

# --- 2. AMBIL KEY DARI SECRETS ---
try:
    TOKEN = st.secrets["TELEGRAM_TOKEN"]
    OPENROUTER_KEY = st.secrets["OPENROUTER_API_KEY"]
    ADMIN_ID = int(st.secrets["ADMIN_CHAT_ID"])
except Exception as e:
    st.error(f"⚠️ Secrets Error: {e}")
    st.stop()

DATA_FILE = "knowledge.json"
MODEL = "google/gemini-2.0-flash-001"

# --- 3. FUNGSI DATABASE ---
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

# --- 4. LOGIKA PINTAR & KESOPANAN ---
def get_ai_response(user_msg):
    knowledge = load_k()
    base_reply = ""
    is_list = any(w in user_msg.lower() for w in ["siapa aja", "siapa saja", "daftar", "dosen-dosen", "apa saja", "list"])

    # A. Cek Knowledge (Fuzzy Matching)
    if knowledge:
        match = process.extractOne(user_msg.lower(), knowledge.keys(), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 85 and not is_list:
            base_reply = knowledge[match[0]]
        elif match and match[1] >= 70 and is_list:
            # Jika tanya daftar dan jawaban di DB panjang, pakai itu. Jika pendek, lapor admin.
            if len(knowledge[match[0]]) > 40:
                base_reply = knowledge[match[0]]
            else:
                base_reply = "[BUTUH_ADMIN]"
        else:
            base_reply = "[BUTUH_ADMIN]"
    else:
        base_reply = "[BUTUH_ADMIN]"

    # B. Jika di Database tidak ada atau butuh update, tanya AI Internet
    if base_reply == "[BUTUH_ADMIN]":
        try:
            with DDGS(timeout=10) as ddgs:
                search = ddgs.text(f"Universitas Graha Nusantara Padangsidimpuan {user_msg}", max_results=2)
                context = "\n".join([r['body'] for r in search])
        except: context = ""

        prompt = (
            f"Kamu asisten resmi Fakultas Teknik UGN. Jawab seputar kampus saja. "
            f"Data: {context}. Jika di luar kampus, tolak sopan. "
            f"Jika info tidak lengkap/tidak tahu, JAWAB: [TIDAK_TAHU]"
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
            return "Maaf Kak, server sedang sibuk. Coba lagi ya! 😊"

    # C. Lapor ke Telegram Admin jika Bot bingung
    if "[TIDAK_TAHU]" in base_reply or base_reply == "[BUTUH_ADMIN]":
        try:
            bot.send_message(ADMIN_ID, f"⚠️ **BOT BINGUNG!**\n\nUser: `{user_msg}`\n\nBalas dengan: `/tambah {user_msg} | Jawabannya`")
        except: pass
        return "Halo Kak! Saat ini asisten belum memiliki data lengkap mengenai hal itu. Pertanyaan Kakak sudah diteruskan ke Admin Fakultas Teknik untuk diperbarui. Ada hal lain yang bisa dibantu? 😊"

    # D. Poles agar Sopan (Rewriting)
    prompt_sopan = f"Ubah kalimat ini jadi jawaban asisten kampus yang sangat sopan dan ramah (panggil Kak): {base_reply}"
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

# --- 5. TELEGRAM BOT SETUP (REKONEKSI PAKSA) ---
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
            bot.reply_to(m, f"✅ Pengetahuan tersimpan!\nInfo: {q.strip()}")
        except:
            bot.reply_to(m, "❌ Format: `/tambah tanya | jawab`")

def start_bot():
    # Ini kuncinya: Hapus koneksi lain agar server ini yang menang
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if "bot_active" not in st.session_state:
    Thread(target=start_bot, daemon=True).start()
    st.session_state.bot_active = True

# --- 6. TAMPILAN CHAT WEBSITE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Tanya info FT-UGN..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Mencari informasi..."):
            ans = get_ai_response(prompt)
            st.markdown(ans)
    st.session_state.messages.append({"role": "assistant", "content": ans})
