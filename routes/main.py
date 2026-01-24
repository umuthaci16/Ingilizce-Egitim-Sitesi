from flask import Blueprint, app, render_template, request, jsonify, redirect, flash, send_from_directory, current_app, url_for
import os, logging, json, time, subprocess, difflib,string
import azure.cognitiveservices.speech as speechsdk
from openai import OpenAI
from utils import is_user_logged_in, fetch_google_translation, login_required, current_user, placement_completed_required
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_user_by_id, update_user_info, update_user_password

# --- VERİTABANI VE YARDIMCI FONKSİYONLAR ---
# Artık her şeyi database.py'den çekiyoruz
from database import (
    get_all_vocabs_with_details, 
    get_vocab_details,
    get_user_levels 
)


main_bp = Blueprint('main', __name__)

# --- AYARLAR ---
UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# OpenAI Başlatma
try:
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
except Exception as e:
    logging.warning(f"OpenAI Client yüklenirken hata: {e}")
    client = None

# Senaryoları Yükle
SCENARIOS_PATH = os.path.join("data", "scenarios.json")
SCENARIOS = {}
if os.path.exists(SCENARIOS_PATH):
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
        SCENARIOS = json.load(f)

# ==========================================
# TEMEL SAYFALAR
# ==========================================

@main_bp.route('/translate')
@placement_completed_required
def index():
    return render_template('index.html')

# ==========================================
# CHAT (SOHBET)
# ==========================================

@main_bp.route('/data/scenarios.json')
@placement_completed_required
def serve_scenarios_json():
    try:
        # data klasörü projenin kök dizininde olduğu varsayılıyor
        return send_from_directory(os.path.join(current_app.root_path, '..', 'data'), 'scenarios.json')
    except Exception:
        return send_from_directory('data', 'scenarios.json')

@main_bp.route('/select_scenario')
@placement_completed_required
def practice():
    scenarios = SCENARIOS
    return render_template('select_scenario.html', scenarios=scenarios)

@main_bp.route("/chat/<scenario>")
@placement_completed_required
def chat(scenario):
    data = SCENARIOS.get(scenario)
    if not data:
        return "Scenario not found", 404
    return render_template("chat.html", scenario=scenario, title=data["title"], is_logged_in=is_user_logged_in())

@main_bp.route("/conversation", methods=["POST"])
@placement_completed_required
def conversation():
    data = request.json
    user_text = data.get("text", "").strip()
    scenario = data.get("scenario", "")
    context = SCENARIOS.get(scenario, {})

    if not user_text or not context:
        return jsonify({"error": "Invalid input"}), 400
    try:
        # Max tokens ile yanıtı kısa tutarak hızı artırıyoruz
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are a friendly English tutor. Topic: {context['title']}. {context['context']}. Correct grammar mistakes gently before replying. Keep answers concise (max 2-3 sentences)."},
                {"role": "assistant", "content": context["intro"]},
                {"role": "user", "content": user_text}
            ],
            temperature=0.7,
            max_tokens=200 
        )
        return jsonify({"reply": response.choices[0].message.content.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# SES YÜKLEME & STT (AZURE CONTINUOUS)
# ==========================================

@main_bp.route('/upload', methods=['POST'])
@placement_completed_required
def upload_audio():
    if 'audio' not in request.files: return jsonify({'error': 'Ses dosyası yok'}), 400
    file = request.files['audio']
    if file.filename == '': return jsonify({'error': 'Dosya seçilmedi'}), 400
    
    temp_id = f"audio_{int(time.time())}_{os.urandom(2).hex()}"
    webm_path = os.path.join(UPLOAD_FOLDER, f"{temp_id}.webm")
    wav_path = os.path.join(UPLOAD_FOLDER, f"{temp_id}.wav")

    recognizer = None
    
    try:
        file.save(webm_path)

        # 1. FFmpeg Dönüşümü
        subprocess.run(
            ["ffmpeg", "-i", webm_path, "-ac", "1", "-ar", "16000", wav_path, "-y"], 
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
        )

        # 2. Azure Yapılandırması
        speech_config = speechsdk.SpeechConfig(subscription=os.getenv("AZURE_SPEECH_KEY"), region=os.getenv("AZURE_SPEECH_REGION"))
        speech_config.speech_recognition_language = "en-US"
        audio_config = speechsdk.audio.AudioConfig(filename=wav_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        # --- SÜREKLİ TANIMA (CONTINUOUS RECOGNITION) ---
        # Bu yöntem duraksamaları tolere eder ve dosya bitene kadar bekler.
        
        all_results = []
        done = False
        
        # Azure Callback'leri
        def handle_result(evt):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                all_results.append(evt.result.text)

        def stop_cb(evt):
            nonlocal done
            done = True

        # Olayları bağla
        recognizer.recognized.connect(handle_result)
        recognizer.session_stopped.connect(stop_cb)
        recognizer.canceled.connect(stop_cb)

        # Başlat
        recognizer.start_continuous_recognition()

        # Dosya bitene kadar bekle (Dosya okuduğu için işlem bitince session_stopped tetiklenir)
        while not done:
            time.sleep(0.1)

        # Durdur
        recognizer.stop_continuous_recognition()
        
        full_transcription = " ".join(all_results).strip()
        
        if not full_transcription:
            return jsonify({'error': 'Ses anlaşılamadı veya boş.'}), 400
            
        return jsonify({'message': 'Success', 'transcription': full_transcription})

    except Exception as e:
        logging.error(f"Upload Error: {e}")
        return jsonify({'error': f'Sistem hatası: {str(e)}'}), 500
        
    finally:
        # Temizlik
        if recognizer: del recognizer
        time.sleep(0.1)
        try:
            if os.path.exists(webm_path): os.remove(webm_path)
            if os.path.exists(wav_path): os.remove(wav_path)
        except Exception as e:
            logging.warning(f"Dosya silinemedi: {e}")

# ==========================================
# GRAMER KONTROL
# ==========================================

@main_bp.route('/check-grammar', methods=['POST'])
@placement_completed_required
def check_grammar():
    data = request.json
    text = data.get('text', '').strip()
    if not text: return jsonify({'error': 'Metin yok'}), 400

    try:
        # JSON formatında yanıt zorluyoruz
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system", 
                    "content": "You are a grammar correction assistant. Return JSON: {'corrected': 'Full corrected text', 'mistakes': [{'wrong': 'exact substring', 'suggestion': 'correction'}]}. If no errors, return empty mistakes list."
                },
                {"role": "user", "content": text}
            ],
            temperature=0.3
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Frontend'in beklediği 'errors' listesini oluştur (offset hesaplaması)
        corrected = result.get("corrected", "")
        mistakes = result.get("mistakes", [])
        errors = []

        for m in mistakes:
            wrong = m.get("wrong", "")
            if wrong:
                offset = text.find(wrong)
                if offset == -1: offset = text.lower().find(wrong.lower())
                
                if offset != -1:
                    errors.append({
                        "offset": offset,
                        "length": len(wrong),
                        "message": m.get("suggestion", "")
                    })

        return jsonify({
            "original": text,
            "corrected": corrected,
            "errors": errors
        })

    except Exception as e:
        logging.error(f"Grammar Error: {e}")
        return jsonify({'error': str(e)}), 500

# ==========================================
# KELİME & ÇEVİRİ (OPTIMIZE EDİLDİ)
# ==========================================

@main_bp.route('/vocab_practice')
@placement_completed_required
def vocab_practice():
    return render_template('vocab_practice.html', is_logged_in=is_user_logged_in())

@main_bp.route('/all_vocabs')
@placement_completed_required
def all_vocabs_page():
    # 1. URL'den harfi al (?letter=B), yoksa varsayılan 'A' olsun
    selected_letter = request.args.get('letter', 'A').upper()
    
    # 2. İngiliz Alfabesini Oluştur (A-Z)
    alphabet = list(string.ascii_uppercase)
    
    try:
        # 3. Veritabanından SADECE o harfe ait kelimeleri çek
        vocabs = get_all_vocabs_with_details(letter=selected_letter)
    except Exception as e:
        logging.error(f"Vocab list error: {e}")
        vocabs = []
        
    return render_template(
        'all_vocabs.html', 
        vocabs=vocabs, 
        is_logged_in=is_user_logged_in(),
        selected_letter=selected_letter, # Template'te hangi harfin aktif olduğunu göstermek için
        alphabet=alphabet # Harf butonlarını oluşturmak için
    )

@main_bp.route('/translate_word', methods=['POST'])
def translate_word_proxy():
    data = request.json or {}
    return jsonify(fetch_google_translation(data.get('word', ''), data.get('source', 'en'), data.get('target', 'tr')))

@main_bp.route('/get_vocab/<int:vocab_id>', methods=['GET'])
@placement_completed_required
def get_vocab(vocab_id):
    details = get_vocab_details(vocab_id)
    if details:
        # details now: (id, word, meanings, examples, levels, word_types)
        return jsonify({
            'id': details[0],
            'word': details[1],
            'meanings': details[2],
            'examples': details[3],
            'levels': details[4] if len(details) > 4 else [],
            'word_types': details[5] if len(details) > 5 else []
        })
    return jsonify({'error': 'Bulunamadı'}), 404

@main_bp.route('/check_vocab_answer', methods=['POST'])
@placement_completed_required
def check_vocab_answer():
    data = request.json
    vocab_id = data.get('vocab_id')
    user_answer = (data.get('user_answer', '') or '').strip().lower()
    
    details = get_vocab_details(vocab_id)
    if not details: return jsonify({'error': 'Bulunamadı'}), 404
    
    is_correct = any(user_answer == m.strip().lower() for m in details[2])
    return jsonify({'is_correct': is_correct, 'correct_meanings': details[2], 'examples': details[3]})


@main_bp.route('/placement_test')
@login_required
def placement_page():
    # 1. Kullanıcının seviye durumunu çek
    user_lvl = get_user_levels(current_user)
    
    # 2. Eğer sınav daha önce tamamlanmışsa Ana Sayfaya yönlendir
    if user_lvl and user_lvl.get('is_completed'):
        flash("Seviye tespit sınavını zaten tamamladınız.", "info")
        return redirect(url_for('main.index'))

    # 3. Tamamlanmamışsa sınav sayfasını render et
    return render_template('placement.html')


# ==========================================
# PROFİL SAYFASI
# ==========================================    

@main_bp.route('/profile')
def profile_page():
    user_id = current_user()
    user = get_user_by_id(user_id)
    username = user.username if user else "Bilinmeyen Kullanıcı"
    if not user:
        return redirect(url_for('auth.login'))
    return render_template('profile.html', user=user,username=username)

@main_bp.route('/api/profile/update-info', methods=['POST'])
def update_profile_info():
    user_id = current_user()
    data = request.json
    new_name = data.get('name')
    
    if not new_name:
        return jsonify({'error': 'İsim alanı boş bırakılamaz.'}), 400
        
    try:
        update_user_info(user_id, name=new_name)
        return jsonify({'success': True, 'message': 'Bilgiler güncellendi.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/profile/change-password', methods=['POST'])
def change_password():
    user_id = current_user()
    data = request.json
    
    current_pass = data.get('current_password')
    new_pass = data.get('new_password')
    confirm_pass = data.get('confirm_password')
    
    if not current_pass or not new_pass:
        return jsonify({'error': 'Alanlar boş olamaz.'}), 400
    if new_pass != confirm_pass:
        return jsonify({'error': 'Şifreler uyuşmuyor.'}), 400
    if len(new_pass) < 6:
        return jsonify({'error': 'Şifre en az 6 karakter olmalı.'}), 400

    user = get_user_by_id(user_id)
    

    if not check_password_hash(user.password, current_pass):
        return jsonify({'error': 'Mevcut şifre hatalı.'}), 400
    # -----------------------
        
    try:
        new_hash = generate_password_hash(new_pass)
        update_user_password(user_id, new_hash)
        return jsonify({'success': True, 'message': 'Şifre başarıyla değiştirildi.'})
    except Exception as e:
        print(f"Hata detayı: {e}") # Konsola hata basmak debug için iyidir
        return jsonify({'error': 'Veritabanı hatası.'}), 500
    
@main_bp.route('/')
def intro_page():  
    return render_template('intro.html')