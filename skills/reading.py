from flask import Blueprint, render_template, request, jsonify
import os, logging, json,difflib
from openai import OpenAI
from services.lesson_pipeline import generate_lesson
from utils import current_user,placement_completed_required
from database import get_user_levels
from skills.xp_manager import process_xp_gain, check_exam_eligibility


reading_bp = Blueprint("reading", __name__)

# OpenAI Başlatma
try:
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
except Exception as e:
    logging.warning(f"OpenAI Client yüklenirken hata: {e}")
    client = None



@reading_bp.route('/reading')
@placement_completed_required
def reading_page():
    user_id = current_user()
    levels = get_user_levels(user_id) or {}
    level = levels.get("reading", {}).get("level", "B1")
    print("Current User Reading Level:", level)
    exam_needed = check_exam_eligibility(user_id, 'reading')
    return render_template('reading.html', level=level, exam_needed=exam_needed)

@reading_bp.route('/api/generate_reading', methods=['GET'])
@placement_completed_required
def generate_reading():
    
    try:
        level = request.args.get('level', 'B1')
        print("Generating reading passage for level:", level)
        data = generate_lesson(skill="reading", level=level)
    except Exception as e:
        logging.error(f"Generate Reading Error: {e}")
        return jsonify({'error': 'Ders oluşturulurken hata oluştu.'}), 500
    print("Generated reading passage:", data)
    return jsonify(data)

@reading_bp.route('/api/assess_reading', methods=['POST'])
@placement_completed_required
def assess_reading():
    data = request.json
    text = data.get('original_text', '')
    summary = data.get('user_summary', '')
    level = data.get('level', 'B1')
    title = data.get('title', '')
    print("Reading puanlama topic:", title)
    print("Reading puanlama level:", level)

    quiz_correct = data.get('quiz_correct_count') 
    quiz_total = data.get('quiz_total_questions')
 
    if quiz_correct is not None and quiz_total and quiz_total > 0:
        quiz_score = (int(quiz_correct) / int(quiz_total)) * 100

    # Kopya kontrolü
    s = difflib.SequenceMatcher(None, text.lower(), summary.lower())
    match = s.find_longest_match(0, len(text), 0, len(summary))
    if match.size > 20:
        return jsonify({
            "status": "cheat",
            "feedback": "Metinden doğrudan kopyalama yapmışsın. Lütfen kendi cümlelerinle özetle."
        })

    try:
        system_message = f"""
        You are an English teacher assessing a student's reading comprehension.

        Level: {level}
        The following text has the title: "{title}"


        Evaluation criteria:
        - Correctly reflects the main idea of the text
        - Coverage of key points
        - Relevance to the title
        - Appropriateness for the given level

        You MUST return ONLY a valid JSON object.
        JSON schema:
        {{
            "score": "Overall comprehension score, must be number (0-100)",
            "feedback": "Turkish feedback explaining the score"
            
        }}
        """

        user_message = f"""
       Original Text:
       {text}

       The student summary is written in Turkish and should be evaluated for comprehension, not translation accuracy.
       Student Summary(Turkish):
       {summary}
       """

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.2
        )
        raw = resp.choices[0].message.content
        try:
            parsed = json.loads(raw)
            ai_score = parsed.get('score', 0)
            feedback = parsed.get('feedback', 'Geri bildirim bulunamadı.')
            # Quiz ve AI skorlarını birleştir
            if quiz_total and quiz_total > 0:
                final_score = (ai_score * 0.6) + (quiz_score * 0.4)
            else:
                final_score = ai_score
            xp_result = process_xp_gain(current_user(), 'reading', final_score, level)
            return jsonify(
                {
            "status": "success",
            "ai_score": ai_score,
            "quiz_score": int(quiz_score),
            "final_score": final_score,
            "feedback": feedback,
            "xp_gain": xp_result  # Frontend'de göstereceğimiz değer
           }
            )
        except json.JSONDecodeError as e:
            logging.error("Reading JSON decode error", exc_info=e)
            return jsonify({
                "final_score": 0,
                "feedback": {"Bir hata oluştu, lütfen tekrar dene."
                }
            }), 500
        
       

    except Exception as e:
        return jsonify({'error': str(e)}), 500    