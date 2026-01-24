import os
import json
import time
import subprocess
import logging
from flask import Blueprint, request, jsonify
from utils import login_required, current_user, placement_not_completed_required
from openai import OpenAI
import azure.cognitiveservices.speech as speechsdk
from database import save_user_placement_result, has_user_completed_placement

placement_bp = Blueprint('placement', __name__)


# --- AYARLAR ---
UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# API Kurulumları
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    client = None

def get_azure_config():
    return os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")

# --- YARDIMCI FONKSİYONLAR ---

def load_json_data(filename):
    try:
        file_path = os.path.join(os.getcwd(), 'data', filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def calculate_static_score(user_answers_dict, correct_answers_dict):
    """Reading ve Listening Part-2 için statik hesaplama"""
    correct_count = 0
    total_questions = 0
    
    for level, answers in user_answers_dict.items():
        if level in correct_answers_dict:
            key = correct_answers_dict[level]
            limit = min(len(answers), len(key))
            for i in range(limit):
                if str(answers[i]) == str(key[i]):
                    correct_count += 1
            total_questions += len(key)
            
    if total_questions == 0: return 0
    return int((correct_count / total_questions) * 100)

def determine_final_cefr(score):
    if score >= 85: return "C1"
    if score >= 65: return "B2"
    if score >= 45: return "B1"
    if score >= 25: return "A2"
    return "A1"

# ==============================================================================
# 1. READING & 2. LISTENING (Statik Yapı - Değişmedi)
# ==============================================================================
# ... (Önceki Reading ve Listening kodları aynen kalacak, burayı tekrar yazıp uzatmıyorum) ...
# (Eğer istersen burayı da tam haliyle atabilirim ama sadece Writing/Speaking değiştik)

@placement_bp.route('/api/placement/reading/generate', methods=['POST'])
@login_required
@placement_not_completed_required
def generate_reading():
    
    return jsonify(load_json_data('reading.json'))

@placement_bp.route('/api/placement/reading/assess', methods=['POST'])
@login_required
@placement_not_completed_required
def assess_reading():
    data = request.json
    score = calculate_static_score(data.get('answers', {}), data.get('correct_answers', {}))
    print("Reading Score:", score)
    return jsonify({"score": score, "level": determine_final_cefr(score)})

@placement_bp.route('/api/placement/listening/generate', methods=['POST'])
@login_required
@placement_not_completed_required
def generate_listening():
    data = load_json_data('listening.json')
    return jsonify({"part_1": data.get('announcements_task', {}), "part_2": data.get('levels', {})})

@placement_bp.route('/api/placement/listening/assess', methods=['POST'])
@login_required
@placement_not_completed_required
def assess_listening():
    data = request.json
    # Part 1 Puanı
    p1_ans, p1_cor = data.get('p1_answers', []), data.get('p1_correct', [])
    p1_score = sum([1 for i, a in enumerate(p1_ans) if i < len(p1_cor) and str(a) == str(p1_cor[i])])
    
    # Part 2 Puanı
    p2_score_raw = calculate_static_score(data.get('p2_answers', {}), data.get('p2_correct', {}))
    
    # Toplam (Basit ağırlıklandırma: Part 1'de 5 soru, Part 2'de 15 soru var gibi düşünelim)
    # Daha hassas hesap için soru sayılarını dinamik alabiliriz ama şimdilik ortalama:
    total_score = (p1_score * 5) + (p2_score_raw * 0.8) # Basit formül
    # Not: Gerçekte toplam soru sayısı üzerinden gitmek en iyisidir, önceki kodundaki mantığı korudum.
    
    # Hızlı fix: Direkt toplam soru üzerinden gidelim
    total_correct = p1_score
    total_q = len(p1_cor)
    
    p2_user = data.get('p2_answers', {})
    p2_cor = data.get('p2_correct', {})
    for lvl in ['A1', 'B1', 'C1']:
        if lvl in p2_cor:
            total_q += len(p2_cor[lvl])
            u, c = p2_user.get(lvl, []), p2_cor[lvl]
            total_correct += sum([1 for i, v in enumerate(u) if i < len(c) and str(v) == str(c[i])])
            
    final_score = int((total_correct / total_q) * 100) if total_q > 0 else 0
    print("Listening Score:", final_score)
    return jsonify({"score": final_score, "level": determine_final_cefr(final_score)})


# ==============================================================================
# 3. WRITING (YENİLENMİŞ MANTIK)
# ==============================================================================
@placement_bp.route('/api/placement/writing/generate', methods=['POST'])
@login_required
@placement_not_completed_required
def generate_writing():
    return jsonify(load_json_data('writing.json'))

@placement_bp.route('/api/placement/writing/assess', methods=['POST'])
@login_required
@placement_not_completed_required
def assess_writing():
    data = request.json
    
    # 1. Statik Gramer Puanı
    grammar_score = calculate_static_score(data.get('grammar_answers', {}), data.get('grammar_correct', {}))
    
    # 2. Essay Analizi (Aşamalı Prompt)
    essays = data.get('essays', {}) # { "A1": "...", "B1": "...", "C1": "..." }
    tasks = load_json_data('writing.json').get('writing_tasks', {})
    
    # Prompt'u senin istediğin mantıkla kuruyoruz:
    prompt = f"""
    You are a strict Placement Test Evaluator. 
    Review the student's writing samples for 3 progressive levels.

    --- TASK 1 (Level A1) ---
    Task: {tasks.get('A1', {}).get('topic')}
    Student Answer: "{essays.get('A1', 'NO ANSWER')}"
    
    --- TASK 2 (Level B1) ---
    Task: {tasks.get('B1', {}).get('topic')}
    Student Answer: "{essays.get('B1', 'NO ANSWER')}"

    --- TASK 3 (Level C1) ---
    Task: {tasks.get('C1', {}).get('topic')}
    Student Answer: "{essays.get('C1', 'NO ANSWER')}"

    EVALUATION LOGIC:
    1. Did the student pass the A1 task with basic sentences?
    2. Did the student pass the B1 task with connected text and intermediate vocabulary?
    3. Did the student pass the C1 task with complex structure and advanced arguments?
    
    If they fail A1, the score should be very low (0-20).
    If they pass A1 but fail B1, score should be A2 level (20-45).
    If they pass B1 but fail C1, score should be B1/B2 level (45-75).
    If they handle C1 well, score should be high (75-100).

    Output ONLY a JSON object: {{ "ai_score": (0-100 integer) }}
    """
    
    ai_score = 0
    try:
        gpt_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a grading assistant."}, {"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        ai_score = json.loads(gpt_resp.choices[0].message.content).get('ai_score', 0)
    except Exception as e:
        print(f"Writing AI Error: {e}")
        ai_score = 40 # Fallback
    print("Writing AI Score:", ai_score)
    print("Writing Grammar Score:", grammar_score)
    # Final: %40 Çoktan seçmeli testler + %60 Kompozisyon
    final_score = int((grammar_score * 0.4) + (ai_score * 0.6))
    print("Writing Score:", final_score)
    level = determine_final_cefr(final_score)
    
    return jsonify({"score": final_score, "level": level})


# ==============================================================================
# 4. SPEAKING (AZURE + GPT ENTEGRASYONU - PLACEMENT'A TAŞINDI)
# ==============================================================================
@placement_bp.route('/api/placement/speaking/generate', methods=['POST'])
@login_required
@placement_not_completed_required
def generate_speaking():
    return jsonify(load_json_data('speaking.json'))

@placement_bp.route('/api/placement/speaking/assess', methods=['POST'])
@login_required
@placement_not_completed_required
def assess_speaking():
    # Frontend'den artık Transcript değil, File (Blob) gelmeli!
    # request.files['A1'], request.files['B1']... şeklinde
    
    scores = []
    
    # 3 Seviye için döngü
    for level in ['A1', 'B1', 'C1']:
        audio_file = request.files.get(level)
        if not audio_file:
            scores.append(0) # Dosya yoksa 0
            continue
            
        # 1. Dosyayı Kaydet
        temp_id = f"place_{level}_{int(time.time())}"
        webm_path = os.path.join(UPLOAD_FOLDER, f"{temp_id}.webm")
        wav_path = os.path.join(UPLOAD_FOLDER, f"{temp_id}.wav")
        audio_file.save(webm_path)
        
        try:
            # 2. FFmpeg Dönüşüm (Azure WAV ister)
            subprocess.run(["ffmpeg", "-i", webm_path, "-ac", "1", "-ar", "16000", wav_path, "-y"], 
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 3. Azure Analizi (Main.py'dan alınan mantık)
            azure_res = analyze_audio_internal(wav_path) # Aşağıda tanımlı
            if azure_res.get('error'):
                scores.append(10) # Ses anlaşılamadıysa düşük puan
                continue
                
            transcript = azure_res['text']
            az_scores = azure_res['scores']
            
            # Azure Ortalaması (Pronunciation, Fluency, Accuracy)
            az_avg = (az_scores.get('pronunciation', 0) + az_scores.get('fluency', 0) + az_scores.get('accuracy', 0)) / 3
            
            # 4. GPT İçerik Analizi (Seviyeye Uygunluk)
            gpt_score = evaluate_speaking_content_internal(transcript, level) # Aşağıda tanımlı
            
            # Bu seviyenin puanı (%60 Azure + %40 GPT)
            level_score = (az_avg * 0.6 + gpt_score * 0.4)
            scores.append(level_score)
            
        except Exception as e:
            print(f"Speaking Error {level}: {e}")
            scores.append(0)
        finally:
            # Temizlik
            if os.path.exists(webm_path): os.remove(webm_path)
            if os.path.exists(wav_path): os.remove(wav_path)
            
    # Final Skor: 3 seviyenin ortalaması (veya ağırlıklı ortalaması)
    # A1 kolay, C1 zor. Hepsini başaran yüksek alır.
    # Basit ortalama alıyoruz çünkü Placement'ta hepsini çözmesini istiyoruz.
    final_score = int(sum(scores) / 3) if scores else 0
    print("Speaking Score:", final_score)
    level = determine_final_cefr(final_score)
    
    return jsonify({"score": final_score, "level": level})

# --- SPEAKING İÇİN YARDIMCI FONKSİYONLAR (Main.py'dan İzole Edildi) ---

def analyze_audio_internal(wav_path):
    """Azure STT ve Pronunciation Assessment"""
    key, region = get_azure_config()
    if not key: return {"error": "API Key missing"}
    
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = "en-US"
    audio_config = speechsdk.audio.AudioConfig(filename=wav_path)
    
    # Pronunciation Config
    pron_config = speechsdk.PronunciationAssessmentConfig(
        reference_text="", # Unscripted
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
    )
    
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    pron_config.apply_to(recognizer)
    
    result = recognizer.recognize_once_async().get()
    
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        pron_res = speechsdk.PronunciationAssessmentResult(result)
        return {
            "text": result.text,
            "scores": {
                "accuracy": pron_res.accuracy_score,
                "fluency": pron_res.fluency_score,
                "pronunciation": pron_res.pronunciation_score
            }
        }
    return {"error": "No match"}

def evaluate_speaking_content_internal(transcript, level):
    """GPT: Bu cevap bu seviye için uygun mu?"""
    prompt = f"""
    Evaluate this speaking response for proficiency Level {level}.
    Transcript: "{transcript}"
    
    Criteria:
    - Did they use vocabulary appropriate for {level}?
    - Is the grammar correct for {level}?
    - Is it coherent?
    
    If it's way below {level}, give a low score (0-40).
    If it fits {level} well, give a passing score (50-75).
    If it exceeds {level}, give a high score (80-100).
    
    Output ONLY JSON: {{ "score": (0-100) }}
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content).get('score', 0)
    except:
        return 0

# ==============================================================================
# SAVE
# ==============================================================================
@placement_bp.route('/api/placement/save', methods=['POST'])
@login_required
@placement_not_completed_required
def save_results():
    results = request.json

    print("results to save:", results)
    user_id = current_user()
    # Eğer zaten tamamlamışsa engelle
    if has_user_completed_placement(user_id):
        return jsonify({"error": "placement_already_completed"}), 403

    ok = save_user_placement_result(user_id, results)
    if ok:
        return jsonify({"status": "success"})
    return jsonify({"error": "save_failed"}), 500