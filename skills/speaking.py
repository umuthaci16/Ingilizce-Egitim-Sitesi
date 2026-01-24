from flask import Blueprint, render_template, request, jsonify
import os, logging, json, time, subprocess
import azure.cognitiveservices.speech as speechsdk
from openai import OpenAI
from services.lesson_pipeline import generate_lesson
from utils import current_user,placement_completed_required
from database import get_user_levels
from skills.xp_manager import process_xp_gain, check_exam_eligibility


speaking_bp = Blueprint("speaking", __name__)


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



@speaking_bp.route('/speaking')
@placement_completed_required
def speaking_page():
    user_id = current_user()
    levels = get_user_levels(user_id) or {}
    level = levels.get("speaking", {}).get("level", "B1")
    print("Current User Speaking Level:", level)
    exam_needed = check_exam_eligibility(user_id, 'speaking')
    return render_template('speaking.html', level=level, exam_needed=exam_needed)

@speaking_bp.route('/api/generate_speaking_task', methods=['GET'])
@placement_completed_required
def generate_speaking_task():
    level = request.args.get('level', 'B1')
    print("Generating speaking task for level:", level)

    try:
        task_data = generate_lesson(skill="speaking",level=level)
        if "task" not in task_data:
            logging.warning("Generated speaking task missing 'task' field.")
            task_data["task"] = task_data.get("prompt", "Please describe your last holiday.")
            
    except Exception as e:
        logging.error(f"Generate Speaking Task Error: {e}")
        task_data = {
            "title": "Topic Generation Error",
            "task": "Could not generate a specific topic."
        }

    return jsonify(task_data)

@speaking_bp.route('/api/assess_speaking', methods=['POST'])
@placement_completed_required
def assess_speaking():
    # 1. DOSYA KONTROLÜ
    if 'audio' not in request.files:
        return jsonify({"error": "Ses dosyası bulunamadı"}), 400
        
    audio_file = request.files['audio']
    task_prompt = request.form.get('task_prompt', '')
    level = request.form.get('level', 'B1')
    print("Assessing speaking task:", task_prompt)
    print("Assessing speaking level:", level)

    # Dosya İsimlendirme (Çakışmayı önlemek için timestamp + random)
    temp_id = f"audio_{int(time.time())}_{os.urandom(2).hex()}"
    webm_path = f"{temp_id}.webm"  # Geçici webm
    wav_path = f"{temp_id}.wav"    # Azure için wav


    try:
        # 2. DOSYAYI KAYDET VE DÖNÜŞTÜR
        audio_file.save(webm_path)

        # FFmpeg: WebM -> WAV (16kHz, Mono)
        command = [
            "ffmpeg", "-i", webm_path, "-ac", "1", "-ar", "16000", "-y", wav_path
        ]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 3. AZURE ANALİZİ (Kulak)
        # Sesi metne çevirir + Telaffuz puanlarını alır
        azure_result = analyze_audio_with_azure(wav_path)
        
        if azure_result.get("error"):
            # Azure sesi hiç anlamadıysa süreci durdur
            logging.error(f"Azure Analysis Error: {azure_result['error']}")
            raise Exception(azure_result["error"])

        transcript = azure_result["text"]
        azure_scores = azure_result["scores"]

        # 4. GPT ANALİZİ (Beyin)
        # Metni alır + İçerik puanlarını ve Feedback'i üretir
        gpt_result = evaluate_speaking_with_gpt(transcript, task_prompt, level)
        
        if gpt_result.get("error") and gpt_result.get("error") != "Short text":
             print(f"GPT Warning: {gpt_result['error']}")

        gpt_scores_data = gpt_result["gpt_scores"]

        # 5. PUAN HESAPLAMA (Hibrit Sistem)
        
        # Azure Ortalaması (Accuracy + Fluency + Pronunciation) / 3
        # Eğer puanlar gelmediyse 0 kabul et
        az_acc = azure_scores.get("accuracy", 0)
        az_flu = azure_scores.get("fluency", 0)
        az_pro = azure_scores.get("pronunciation", 0)
        az_prosody = azure_scores.get("prosody", 0)
        avg_azure = (az_acc + az_flu + az_pro) / 3 if azure_scores else 0

        # GPT Ortalaması (Grammar + Vocab + Coherence + Task) / 4
        gpt_gram = gpt_scores_data.get("grammar", 0)
        gpt_voc = gpt_scores_data.get("vocabulary", 0)
        gpt_coh = gpt_scores_data.get("coherence", 0)
        gpt_task = gpt_scores_data.get("task_achievement", 0)
        avg_gpt = (gpt_gram + gpt_voc + gpt_coh + gpt_task) / 4

        # GENEL SKOR (%50 Azure + %50 GPT)
        final_score = (avg_azure + avg_gpt) / 2
        rounded_score = round(final_score)
        xp_result = process_xp_gain(current_user(), 'speaking', rounded_score, level)

        # 6. SONUÇ PAKETİ (Frontend Uyumu)
        response_data = {
            "transcription": transcript,
            "corrected_text": gpt_result["corrected_text"],
            "feedback_tr": gpt_result["feedback_tr"],
            
            # GPT Puanları
            "grammar_score": gpt_gram,
            "relevance_score": gpt_task,
            "vocabulary_score": gpt_voc,
            "coherence_score": gpt_coh,
            
            # Azure Puanları (Bunları ekliyoruz)
            "fluency_score": az_flu,
            "pronunciation_score": az_pro,
            "accuracy_score": az_acc,       # YENİ
            "prosody_score": az_prosody,
            
            # Genel Skor
            "total_score": round(final_score),

            "xp_gain": xp_result
        }
        return jsonify(response_data)

    except subprocess.CalledProcessError:
        return jsonify({"error": "Ses formatı dönüştürülemedi (FFmpeg hatası)."}), 500
    except Exception as e:
        # Hata durumunda bile en azından transkripsiyon varsa onu dönmeye çalış
        # Ama genelde 500 dönmek daha güvenlidir.
        print(f"Genel Hata: {str(e)}")
        return jsonify({
            "transcription": "(Hata oluştu)", 
            "corrected_text": "-", 
            "feedback_tr": f"İşlem sırasında bir hata oluştu: {str(e)}",
            "grammar_score": 0,
            "relevance_score": 0
        })

    finally:
        # 7. TEMİZLİK
        # Dosyaları sil
        if os.path.exists(webm_path):
            try: os.remove(webm_path)
            except: pass
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except: pass

def analyze_audio_with_azure(audio_file_path, hints=None):
    """
    Azure Speech SDK kullanarak sesi analiz eder.
    Hem Speech-to-Text (Metne çevirme) yapar 
    hem de Pronunciation Assessment (Telaffuz puanlama) gerçekleştirir.
    
    Dönüş Formatı (Dict):
    {
        "text": "Kullanıcının söylediği cümle.",
        "scores": {
            "accuracy": 0-100,
            "fluency": 0-100,
            "pronunciation": 0-100,
            "prosody": 0-100 (Opsiyonel, tonlama)
        },
        "error": None veya Hata Mesajı
    }
    """
    
    # 1. API Anahtarlarını Al
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    speech_region = os.getenv("AZURE_SPEECH_REGION")

    if not speech_key or not speech_region:
        return {"error": "Azure API anahtarları eksik.", "text": "", "scores": {}}

    try:
        # 2. Temel Konfigürasyon
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.speech_recognition_language = "en-US"
        
        # Sesten okuyacak şekilde ayarla
        audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)

        # 3. KRİTİK NOKTA: Telaffuz Değerlendirme Ayarları (Unscripted)
        # reference_text boş bırakılırsa Azure bunun doğaçlama olduğunu anlar (SDK sürümüne bağlı olarak)
        # Ancak en garantisi, önce sesi tanımak sonra puanlamaktır. 
        # Azure'un yeni SDK'larında unscripted desteklenir.
        

        # 4. Tanıyıcıyı Oluştur ve Config'i Uygula
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        if hints and len(hints) > 0:
            phrase_list_grammar = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
            for phrase in hints:
            # Her bir kelimeyi/ifadeyi ekle
                phrase_list_grammar.addPhrase(phrase)

        pronunciation_config = speechsdk.PronunciationAssessmentConfig(
        reference_text="",
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme
        )

        pronunciation_config.apply_to(recognizer)

        # 5. İşlemi Başlat (Tek seferlik okuma)
        # recognize_once_async() kısa konuşmalar (30sn altı) için idealdir.
        result = recognizer.recognize_once_async().get()

        # 6. Sonuçları İşle
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            
            # Telaffuz sonuçlarını çek
            pron_result = speechsdk.PronunciationAssessmentResult(result)
            
            return {
                "text": result.text,
                "scores": {
                    "accuracy": pron_result.accuracy_score,
                    "fluency": pron_result.fluency_score,
                    "pronunciation": pron_result.pronunciation_score,
                    "prosody": pron_result.prosody_score 
                },
                "error": None
            }
            
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return {"error": "Ses anlaşılamadı (NoMatch).", "text": "", "scores": {}}
            
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            return {"error": f"İptal: {cancellation.reason}. Detay: {cancellation.error_details}", "text": "", "scores": {}}

    except Exception as e:
        return {"error": f"Azure Hatası: {str(e)}", "text": "", "scores": {}}

    return {"error": "Bilinmeyen hata", "text": "", "scores": {}}


def evaluate_speaking_with_gpt(transcript, task_prompt, level="B1"):
    """
    Öğrencinin konuşma metnini (transcript) GPT ile analiz eder.
    OpenAI çağrısını doğrudan kendi içinde yapar.
    
    Argümanlar:
    - transcript (str): Azure'dan gelen metin.
    - task_prompt (str): Öğrenciye sorulan soru/görev.
    - level (str): Hedef seviye (A1, A2, B1...).
    
    Dönüş (Dict):
    {
        "gpt_scores": { "grammar": ..., "vocabulary": ..., "coherence": ..., "task_achievement": ... },
        "corrected_text": "...",
        "feedback_tr": "...",
        "error": None
    }
    """

    # 1. KELİME SAYISI FİLTRESİ (Maliyet ve Kalite Kontrolü)
    # Eğer metin 3 kelimeden kısaysa GPT'ye gitme, direkt hata dön.
    word_count = len(transcript.split())
    if word_count < 3:
        return {
            "gpt_scores": {
                "grammar": 0,
                "vocabulary": 0,
                "coherence": 0,
                "task_achievement": 0
            },
            "corrected_text": "-",
            "feedback_tr": "Sesiniz algılandı ancak anlamlı bir cümle kurulamadı. Lütfen tekrar deneyin.",
            "error": "Short text"
        }


    # 3. PROMPT HAZIRLIĞI
    system_msg = (
        "You are an expert English Speaking Examiner. "
        "Evaluate the student response based on the CEFR level provided. "
        "Return ONLY a valid JSON object."
    )

    user_msg = f"""
    Evaluate this speaking attempt.
    
    TARGET LEVEL: {level}
    TASK GIVEN: "{task_prompt}"
    STUDENT RESPONSE: "{transcript}"
    
    SCORING CRITERIA (0-100):
    1. Grammar: Accuracy suitable for {level}.
    2. Vocabulary: Range and appropriateness.
    3. Coherence: Flow and linking.
    4. Task Achievement: Did they answer the specific question?
    
    OUTPUT JSON FORMAT:
    {{
        "scores": {{
            "grammar": (int),
            "vocabulary": (int),
            "coherence": (int),
            "task_achievement": (int)
        }},
        "corrected_text": "Rewrite the student's response exactly as a NATIVE SPEAKER would say it (natural, idiomatic). Keep the meaning but upgrade the quality.",
        "feedback_tr": "Constructive advice in TURKISH. Mention strengths and weaknesses. Be encouraging."
    }}
    """

    try:
        # 4. GPT ÇAĞRISI (Direkt İşlem)
        response = client.chat.completions.create(
            model="gpt-4o-mini",  
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        # 5. JSON PARSE VE DÜZENLEME
        content = response.choices[0].message.content
        data = json.loads(content)
        
        scores = data.get("scores", {})
        
        # Dönüş yapısını standartlaştırıyoruz
        return {
            "gpt_scores": {
                "grammar": scores.get("grammar", 0),
                "vocabulary": scores.get("vocabulary", 0),
                "coherence": scores.get("coherence", 0),
                "task_achievement": scores.get("task_achievement", 0)
            },
            "corrected_text": data.get("corrected_text", "Düzeltme oluşturulamadı."),
            "feedback_tr": data.get("feedback_tr", "Geri bildirim oluşturulamadı."),
            "error": None
        }

    except Exception as e:
        print(f"GPT Eval Hatası: {e}")
        return {
            "gpt_scores": {"grammar": 0, "vocabulary": 0, "coherence": 0, "task_achievement": 0},
            "corrected_text": transcript,
            "feedback_tr": "Yapay zeka analizi sırasında teknik bir hata oluştu.",
            "error": str(e)
        }
