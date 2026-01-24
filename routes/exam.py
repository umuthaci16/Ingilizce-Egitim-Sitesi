from flask import Blueprint, request, jsonify, render_template
import os, json, time, subprocess, logging, difflib
from datetime import datetime
from openai import OpenAI
import azure.cognitiveservices.speech as speechsdk
from utils import current_user,placement_completed_required
from database import get_user_levels, check_skill_cooldown
# EKLENDİ: LEVEL_THRESHOLDS import edilmeli
from skills.xp_manager import upgrade_user_level, apply_exam_failure, LEVEL_THRESHOLDS

exam_bp = Blueprint("exam", __name__)

# --- API AYARLARI ---
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    client = None
    logging.error("OpenAI Client başlatılamadı.")

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ==============================================================================
# 0. SAYFAYI GÖSTER (HTML RENDER)
# ==============================================================================
@exam_bp.route('/exam_page')
@placement_completed_required
def exam_page_render():
    # URL'den ?skill=reading parametresini frontend JS okuyacak
    return render_template('level_up_exam.html')

# ==============================================================================
# 1. DURUM KONTROL (Kilitli mi?)
# ==============================================================================
@exam_bp.route('/api/exam/status', methods=['GET'])
@placement_completed_required
def check_exam_status():
    # DEBUG MODU
    if request.args.get('debug') == '1':
        forced_level = request.args.get('test_level', 'A1') 
        return jsonify({
            "can_enter": True,
            "current_level": forced_level,
            "message": f"[DEBUG MODE] {forced_level} Sınavı Aktif"
        })

    user_id = current_user() # utils.py yapına göre .id kullanımı
    skill = request.args.get('skill')
    
    # 1. Verileri Çek
    stats = get_user_levels(user_id) or {}
    skill_data = stats.get(skill, {})
    
    current_level = skill_data.get('level', 'A1')
    current_xp = skill_data.get('xp', 0)
    
    # --- EKLENEN KISIM BAŞLANGIÇ (XP Kontrolü) ---
    # C2 ise sınav yok
    if current_level == 'C2':
        return jsonify({"can_enter": False, "reason": "max_level", "message": "Zaten en üst seviyedesiniz."})

    # Matematiksel Kontrol: XP Tavana Vurdu mu?
    # Mevcut seviyenin tavan puanını al (Örn: A1 -> 499)
    threshold_max = LEVEL_THRESHOLDS.get(current_level, (0, 999999))[1]
    
    # Eğer XP tavanın altındaysa sınava giremez
    if current_xp < threshold_max:
        return jsonify({
            "can_enter": False, 
            "reason": "xp_low", 
            "message": "Henüz yeterli XP'ye ulaşmadınız.",
            "current_xp": current_xp,
            "required_xp": threshold_max
        })
    # --- EKLENEN KISIM BİTİŞ ---

    # 2. Cooldown Kontrolü (XP yetiyor ama cezalı mı?)
    cooldown_until = check_skill_cooldown(user_id, skill)
    if cooldown_until:
        remaining = cooldown_until - datetime.now()
        minutes = int(remaining.total_seconds() / 60)
        
        if minutes > 0:
            return jsonify({
                "can_enter": False,
                "reason": "cooldown",
                "message": f"Sınav kilitli! {minutes} dakika beklemeniz gerekiyor."
            })

    # Her şey tamam: XP dolu, Ceza yok.
    return jsonify({
        "can_enter": True,
        "current_level": current_level,
        "message": f"{current_level} -> {skill.upper()} Final Sınavı Hazır"
    })

# ==============================================================================
# 2. SINAV İÇERİĞİ OLUŞTURMA (GENERATE)
# ==============================================================================
@exam_bp.route('/api/exam/start', methods=['POST'])
@placement_completed_required
def start_exam():
    data = request.json
    skill = data.get('skill')
    level = data.get('level')

    try:
        if skill in ['reading', 'listening']:
            return generate_reading_listening_exam(skill, level)
        elif skill == 'writing':
            return generate_writing_exam(level)
        elif skill == 'speaking':
            return generate_speaking_exam(level)
        else:
            return jsonify({"error": "Geçersiz yetenek"}), 400
    except Exception as e:
        logging.error(f"Exam Generate Error: {e}")
        return jsonify({"error": str(e)}), 500

def generate_reading_listening_exam(skill, level):
    # Prompt Güncellemesi: Çakışmayı (Overlap) önleyen kurallar eklendi.
    prompt = f"""
    Create a STRICT Level Up Exam for English {skill.upper()} (Level: {level}).
    
    STRUCTURE:
    - Generate 2 DIFFERENT texts (Part 1 and Part 2).
    - Text length: { '150 words' if level in ['A1','A2'] else '300 words' }.
    - Topic: Academic or complex daily life.
    
    FOR EACH TEXT (Part 1 & Part 2), generate questions with NO OVERLAP in content:
    
    1. The Text (or Transcript for listening).
    
    2. 5 Multiple Choice Questions (Focus on MAIN IDEAS and INFERENCE). 
       - Do NOT test simple word matching.
       
    3. 5 Fill-in-the-Blank sentences.
       - Focus on VOCABULARY and GRAMMAR within context.
       - The missing word MUST NOT be the answer to any Multiple Choice question.
       
    4. 5 True/False/Not Given questions.
       - Focus on DETAILS and SPECIFIC FACTS.
       - Do NOT reuse the same facts from MC or FIB.
    
    OUTPUT JSON FORMAT:
    {{
        "parts": [
            {{
                "id": 1,
                "text": "Full text here...",
                "mc_questions": [ {{"question": "...", "options": ["A","B","C","D"], "correct_index": 0}} ],
                "fib_questions": [ {{"sentence": "She went to ___ store.", "correct_word": "the"}} ],
                "tf_questions": [ {{"statement": "...", "answer": "True"}} ]
            }},
            {{
                "id": 2,
                "text": "...", 
                "mc_questions": [...], 
                "fib_questions": [...], 
                "tf_questions": [...]
            }}
        ]
    }}
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.4, # Biraz daha yaratıcı olsun ki sorular çeşitlensin
        response_format={"type": "json_object"}
    )
    return jsonify(json.loads(resp.choices[0].message.content))

def generate_writing_exam(level):
    prompt = f"""
    Create a WRITING EXAM for Level {level} with 2 distinct tasks.
    
    Task 1: Functional Writing (Email, Letter, Note) - Approx 80-100 words.
    Task 2: Essay / Article / Story - Approx { '150' if level in ['A1','A2'] else '250' } words.
    
    Include specific CONSTRAINTS for each (e.g., "Use 3 past tense verbs", "Use 'However' and 'Therefore'").
    
    OUTPUT JSON:
    {{
        "tasks": [
            {{ "id": 1, "topic": "...", "instructions": "...", "constraints": "..." }},
            {{ "id": 2, "topic": "...", "instructions": "...", "constraints": "..." }}
        ]
    }}
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.5, response_format={"type": "json_object"}
    )
    return jsonify(json.loads(resp.choices[0].message.content))

def generate_speaking_exam(level):
    prompt = f"""
    Create a SPEAKING EXAM for Level {level} with 2 tasks.
    
    Task 1: Interview Style (3 related questions).
    Task 2: Long Turn (Topic card with 3 bullet points).
    
    OUTPUT JSON:
    {{
        "tasks": [
            {{ "id": 1, "type": "interview", "prompt": "Answer these: 1... 2... 3..." }},
            {{ "id": 2, "type": "long_turn", "prompt": "Talk about [Topic]. You should say: - What... - Who... - Why..." }}
        ]
    }}
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.5, response_format={"type": "json_object"}
    )
    return jsonify(json.loads(resp.choices[0].message.content))

# ==============================================================================
# 3. SINAV DEĞERLENDİRME (SUBMIT & GRADE)
# ==============================================================================
@exam_bp.route('/api/exam/submit', methods=['POST'])
@placement_completed_required
def submit_exam():
    user_id = current_user() # utils.id kullanımı
    
    # 1. Speaking (FormData ile gelir)
    if 'audio_task_1' in request.files:
        return grade_speaking_exam(user_id, request)

    # 2. Diğerleri (JSON ile gelir)
    data = request.json
    skill = data.get('skill')
    level = data.get('level')
    
    final_score = 0
    feedback_msg = ""
    
    try:
        if skill in ['reading', 'listening']:
            final_score, feedback_msg = grade_reading_listening_exam(data, level)
        elif skill == 'writing':
            final_score, feedback_msg = grade_writing_exam(data, level)
            
        # --- KARAR MEKANİZMASI ---
        # Baraj: 70
        passed = final_score >= 70
        
        if passed:
            up_res = upgrade_user_level(user_id, skill)
            return jsonify({
                "passed": True,
                "score": final_score,
                "message": "TEBRİKLER! Sınavı geçtiniz.",
                "details": feedback_msg,
                "new_level": up_res.get('new_level')
            })
        else:
            fail_res = apply_exam_failure(user_id, skill)
            return jsonify({
                "passed": False,
                "score": final_score,
                "message": "Sınavdan kaldınız.",
                "details": feedback_msg,
                "penalty": fail_res
            })
            
    except Exception as e:
        logging.error(f"Grading Error: {e}")
        return jsonify({"error": "Puanlama hatası"}), 500

# ------------------------------------------------------------------------------
# A. READING & LISTENING PUANLAMA
# ------------------------------------------------------------------------------
def grade_reading_listening_exam(data, level):
    total_objective_score = 0
    total_summary_score = 0
    feedback_log = []
    
    parts = data.get('answers', [])
    
    for part in parts:
        # 1. Objektif Puanlama
        obj_correct = 0
        for q_type in ['mc', 'fib', 'tf']:
            questions = part.get(f'{q_type}_answers', [])
            for q in questions:
                if str(q.get('user', '')).strip().lower() == str(q.get('correct', '')).strip().lower():
                    obj_correct += 1
        
        total_objective_score += (obj_correct * 2)

        # 2. Özet Puanlama (GPT)
        summary = part.get('user_summary', '')
        original_text = part.get('text', '')
        
        if len(summary.split()) < 5:
            gpt_score = 0
        else:
            gpt_score = grade_summary_with_gpt(original_text, summary, level)
            
        total_summary_score += (gpt_score * 0.2)
        feedback_log.append(f"Part {part.get('id')} Summary: {gpt_score}/100")

    final_score = int(total_objective_score + total_summary_score)
    final_score = min(100, final_score)
    
    return final_score, "; ".join(feedback_log)

def grade_summary_with_gpt(text, summary, level):
    prompt = f"""
    Grade this summary (0-100) for Reading Comprehension Level {level}.
    Original Text: "{text[:300]}..."
    Student Summary: "{summary}"
    OUTPUT JSON: {{ "score": (int) }}
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content).get('score', 0)
    except:
        return 50

# ------------------------------------------------------------------------------
# B. WRITING PUANLAMA
# ------------------------------------------------------------------------------
def grade_writing_exam(data, level):
    tasks = data.get('tasks', [])
    scores = []
    
    for task in tasks:
        essay = task.get('answer', '')
        topic = task.get('topic', '')
        constraints = task.get('constraints', '')
        
        if len(essay.split()) < 10:
            scores.append(0)
            continue
            
        prompt = f"""
        Strictly grade this WRITING EXAM TASK (Level {level}).
        Topic: {topic}
        Constraints: {constraints}
        Student Essay: "{essay}"
        OUTPUT JSON: {{ "score": (0-100) }}
        """
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            scores.append(json.loads(resp.choices[0].message.content).get('score', 0))
        except:
            scores.append(40)
            
    final_score = int(sum(scores) / len(scores)) if scores else 0
    return final_score, f"Task Scores: {scores}"

# ------------------------------------------------------------------------------
# C. SPEAKING PUANLAMA (HİBRİT)
# ------------------------------------------------------------------------------
def grade_speaking_exam(user_id, request):
    tasks_scores = []
    
    for i in [1, 2]:
        file_key = f'audio_task_{i}'
        prompt_key = f'prompt_task_{i}'
        level = request.form.get('level', 'B1')
        
        if file_key not in request.files:
            continue
            
        file = request.files[file_key]
        task_prompt = request.form.get(prompt_key, "")
        
        temp_id = f"exam_{user_id}_{i}_{int(time.time())}"
        webm_path = os.path.join(UPLOAD_FOLDER, f"{temp_id}.webm")
        wav_path = os.path.join(UPLOAD_FOLDER, f"{temp_id}.wav")
        file.save(webm_path)
        
        try:
            subprocess.run(["ffmpeg", "-i", webm_path, "-ac", "1", "-ar", "16000", "-y", wav_path], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            az_res = analyze_audio_internal(wav_path)
            if az_res.get('error'):
                tasks_scores.append(0)
                continue
                
            az_score = (az_res['scores']['accuracy'] + az_res['scores']['fluency'] + az_res['scores']['pronunciation']) / 3
            gpt_score = evaluate_speaking_content_strict(az_res['text'], task_prompt, level)
            
            tasks_scores.append((az_score + gpt_score) / 2)
            
        except Exception as e:
            logging.error(f"Speaking Exam Error {i}: {e}")
            tasks_scores.append(0)
        finally:
            if os.path.exists(webm_path): os.remove(webm_path)
            if os.path.exists(wav_path): os.remove(wav_path)

    final_score = int(sum(tasks_scores) / len(tasks_scores)) if tasks_scores else 0
    passed = final_score >= 70
    
    if passed:
        up_res = upgrade_user_level(user_id, 'speaking')
        return jsonify({"passed": True, "score": final_score, "message": "Geçtiniz!", "new_level": up_res.get('new_level')})
    else:
        fail_res = apply_exam_failure(user_id, 'speaking')
        return jsonify({"passed": False, "score": final_score, "message": "Kaldınız.", "penalty": fail_res})

# --- YARDIMCI FONKSİYONLAR ---
def analyze_audio_internal(wav_path):
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    speech_region = os.getenv("AZURE_SPEECH_REGION")
    
    if not speech_key: return {"error": "No Key"}
    
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    audio_config = speechsdk.audio.AudioConfig(filename=wav_path)
    pron_config = speechsdk.PronunciationAssessmentConfig(
        reference_text="", grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
    )
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    pron_config.apply_to(recognizer)
    
    result = recognizer.recognize_once_async().get()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        pr = speechsdk.PronunciationAssessmentResult(result)
        return {"text": result.text, "scores": {"accuracy": pr.accuracy_score, "fluency": pr.fluency_score, "pronunciation": pr.pronunciation_score}}
    return {"error": "No Match"}

def evaluate_speaking_content_strict(text, task, level):
    prompt = f"""
    Grade this Speaking Exam Answer (Level {level}) strictly 0-100.
    Task: {task}
    Transcript: "{text}"
    OUTPUT JSON: {{ "score": (int) }}
    """
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(r.choices[0].message.content).get('score', 0)
    except:
        return 0