import requests
import json
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from threading import Thread
from thefuzz import process, fuzz
from duckduckgo_search import DDGS
from datetime import datetime, timedelta
from collections import Counter

app = Flask(__name__)
CORS(app)

# ==================== KONFIGURASI ====================
OPENROUTER_API_KEY = "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"
TELEGRAM_TOKEN = "8675575036:AAHsgOKOhudzTxbCDPV8qP9DuYRv6vwmRcc"
ADMIN_CHAT_ID = 5290553066
MODEL_NAME = "google/gemini-2.0-flash-001" 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "knowledge.json")
LOG_FILE = os.path.join(BASE_DIR, "arsip_chat.json")

LINK_PMB = "https://pmb.ugn.ac.id" 
LINK_MAPS = "https://maps.app.goo.gl/3Xp5wWJjFvUj6S9T9"
# =====================================================

bot_telegram = telebot.TeleBot(TELEGRAM_TOKEN)

# --- DATABASE & ANALYTICS ---
def load_knowledge():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_knowledge(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except: return False

def simpan_ke_arsip(user_query, bot_reply):
    """Menyimpan chat dengan label TOPIK otomatis dari AI Gemini"""
    arsip = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                arsip = json.load(f)
        except: arsip = []
    
    # AI Menentukan Label Topik (Normalisasi)
    try:
        prompt_topik = (
            f"Tentukan SATU KATA kategori/topik untuk pertanyaan ini: '{user_query}'. "
            "Pilihan: pendaftaran, ukt, lokasi, beasiswa, akreditasi, fasilitas, atau umum. "
            "HANYA BERIKAN SATU KATA SAJA."
        )
        res_topik = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt_topik}]},
            timeout=5
        )
        topik_final = res_topik.json()['choices'][0]['message']['content'].strip().lower().replace('.', '')
    except:
        topik_final = "umum"

    arsip.append({
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_query,
        "topik": topik_final,
        "bot": bot_reply
    })
    
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(arsip, f, indent=4, ensure_ascii=False)

# --- TELEGRAM ADMIN CONTROL ---
@bot_telegram.message_handler(commands=['start', 'help', 'statistik'])
def handle_commands(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    
    if message.text.startswith('/statistik'):
        if not os.path.exists(LOG_FILE):
            bot_telegram.reply_to(message, "Belum ada data chat.")
            return

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        now = datetime.now()
        hari, minggu, bulan = [], [], []

        for item in data:
            tgl = datetime.strptime(item['waktu'], "%Y-%m-%d %H:%M:%S")
            tp = item.get('topik', 'umum')
            if tgl.date() == now.date(): hari.append(tp)
            if now - tgl <= timedelta(days=7): minggu.append(tp)
            if tgl.month == now.month and tgl.year == now.year: bulan.append(tp)

        def top_tp(daftar):
            if not daftar: return "Tidak ada data"
            counts = Counter(daftar).most_common(3)
            return "\n".join([f"• {k.upper()} ({v}x)" for k, v in counts])

        msg = (
            "📊 **ANALISIS TREN TOPIK UGN**\n\n"
            f"📅 **HARI INI:**\n{top_tp(hari)}\n\n"
            f"🗓️ **MINGGU INI:**\n{top_tp(minggu)}\n\n"
            f"🏢 **BULAN INI:**\n{top_tp(bulan)}\n\n"
            f"**Total Chat:** {len(data)}"
        )
        bot_telegram.reply_to(message, msg, parse_mode="Markdown")
    else:
        bot_telegram.reply_to(message, "🤖 **Admin Bot UGN**\n\n🔹 `/tambah Tanya | Jawab`\n🔹 `/hapus Kata`\n🔹 `/statistik` (Laporan AI)")

@bot_telegram.message_handler(func=lambda message: message.reply_to_message is not None)
def handle_admin_reply(message):
    if message.chat.id == ADMIN_CHAT_ID:
        original_msg = message.reply_to_message.text
        question = ""
        for line in original_msg.split('\n'):
            if "User nanya:" in line:
                question = line.split("User nanya:")[1].strip().lower()
                break
        if question:
            proses_dan_simpan(message, question, message.text)

@bot_telegram.message_handler(commands=['tambah'])
def tambah_manual(message):
    if message.chat.id == ADMIN_CHAT_ID:
        isi = message.text.replace('/tambah', '').strip()
        if "|" not in isi:
            bot_telegram.reply_to(message, "❌ Gunakan tanda | sebagai pemisah.")
            return
        parts = isi.split("|")
        proses_dan_simpan(message, parts[0].strip().lower(), parts[1].strip())

def proses_dan_simpan(message, question, jawaban_singkat):
    try:
        bot_telegram.send_chat_action(message.chat.id, 'typing')
        prompt = f"Pertanyaan: '{question}'. Jawaban: '{jawaban_singkat}'. Buat 1 kalimat ramah, panggil Kak, sebut dari Admin Fakultas Teknik UGN. JANGAN beri opsi atau [Foto]."
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}]},
            timeout=15
        )
        jawaban_final = res.json()['choices'][0]['message']['content'].strip().replace('"', '')
        data = load_knowledge()
        data[question] = jawaban_final
        if save_knowledge(data):
            bot_telegram.reply_to(message, f"✅ **TERSIMPAN!**\n\n📖 {jawaban_final}")
    except: bot_telegram.reply_to(message, "❌ Gagal merapikan jawaban.")

def cari_internet(query):
    try:
        with DDGS(timeout=10) as ddgs:
            text_gen = ddgs.text(query, max_results=2)
            return "\n".join([f"- {r['body']}" for r in text_gen])
    except: return ""

# --- ROUTE UTAMA CHAT (GUARDRAIL & ANALYTICS) ---
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_msg = data.get('message', '').lower().strip()
        knowledge = load_knowledge()
        
        # 1. CEK DATABASE LOKAL
        if knowledge:
            match = process.extractOne(user_msg, knowledge.keys(), scorer=fuzz.token_set_ratio)
            if match and match[1] >= 65:
                simpan_ke_arsip(user_msg, knowledge[match[0]])
                return jsonify({"reply": knowledge[match[0]]})
        
        # 2. LAPOR TELEGRAM
        if len(user_msg.split()) > 1:
            bot_telegram.send_message(ADMIN_CHAT_ID, f"❓ *USER NANYA:* {user_msg}")

        # 3. FALLBACK AI + GUARDRAIL (BATAS KAMPUS UGN)
        data_internet = cari_internet(user_msg)
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "system", 
                    "content": (
                        "Kamu asisten UGN. Ramah, panggil 'Kak', NETRAL. "
                        "HANYA jawab seputar UGN, Fakultas Teknik, PMB, UKT, dan informasi kampus UGN. "
                        "Jika di luar topik UGN, JAWAB: 'Maaf Kak, saya hanya dapat membantu seputar UGN. Ada lagi yang bisa dibantu?' "
                        f"Info Pendaftaran: {LINK_PMB}, Lokasi: {LINK_MAPS}. "
                        "DILARANG kirim [Foto]. "
                        f"Internet: {data_internet}. Jika buntu jawab: MAAF_TIDAK_TAHU"
                    )
                },
                {"role": "user", "content": user_msg}
            ]
        }
        res = requests.post(url="https://openrouter.ai/api/v1/chat/completions",
                            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                            data=json.dumps(payload), timeout=20)
        ai_reply = res.json()['choices'][0]['message']['content']
        
        if "MAAF_TIDAK_TAHU" in ai_reply:
            ai_reply = f"Halo Kak! Maaf asisten belum tahu jawabannya. Cek pendaftaran di {LINK_PMB} ya! 😊"
        
        simpan_ke_arsip(user_msg, ai_reply)
        return jsonify({"reply": ai_reply})
    except:
        return jsonify({"reply": "Duh Kak, server lagi sibuk sebentar ya!"})

def run_telebot():
    bot_telegram.infinity_polling()

if __name__ == '__main__':
    Thread(target=run_telebot, daemon=True).start()
    print(f"--- SERVER UGN AKTIF (DEV: PUTRA HALOMOAN HSB) ---")
    app.run(debug=True, port=5000, use_reloader=False)