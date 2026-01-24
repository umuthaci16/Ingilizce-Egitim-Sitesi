from flask import Blueprint, render_template, request, jsonify
import os, logging, json
from openai import OpenAI
from services.lesson_pipeline import generate_lesson
from utils import current_user,placement_completed_required
from database import get_user_levels
from skills.xp_manager import process_xp_gain, check_exam_eligibility

writing_bp = Blueprint("writing", __name__)

try:
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
except Exception as e:
    logging.warning(f"OpenAI Client yüklenirken hata: {e}")
    client = None


@writing_bp.route('/writing')
@placement_completed_required
def writing_page():
    user_id = current_user()
    levels = get_user_levels(user_id) or {}
    level = levels.get("writing", {}).get("level", "B1")
    print("Current User Writing Level:", level)
    exam_needed = check_exam_eligibility(user_id, 'writing')
    return render_template('writing.html', level=level, exam_needed=exam_needed)

@writing_bp.route('/api/generate_writing_topic', methods=['GET'])
@placement_completed_required
def generate_writing_topic():
    try:
        level = request.args.get('level', 'B1')
        print("Generating writing topic for level:", level)
        text= generate_lesson(skill="writing", level=level)
    except Exception as e:
        logging.error(f"Generate Writing Topic Error: {e}")
        return jsonify({'error': 'Konu oluşturulurken hata oluştu.'}), 500
    
    print("Generated writing topic:", text)
    return jsonify({"topic": text})
    

@writing_bp.route('/api/assess_writing', methods=['POST'])
@placement_completed_required
def assess_writing():
    data = request.json
    text = data.get('text', '').strip()
    topic = data.get('topic', '').strip()
    level = data.get('level', 'B1')

    print("Writing puanlama topic:", topic)
    print("Writing puanlama level:", level)

    if len(text.split()) < 3:
        return jsonify({"status": "invalid", "feedback_points": ["Çok kısa."]})

    try:
        # Prompt: Anlama odaklı (Meaning over Mechanics)
        system_instructions = f"""
        You are an English teacher grading a student (Level {level}). Topic: "{topic}".
        If the text is mostly unrelated to the topic, reduce the score significantly.
        If the text is clearly above or below the given level, reflect this in the coherence_score.

        If it is completely unrelated, set status to "invalid".
        If status is "invalid", score must be 0 and corrected_text must be empty.
        The final score should be consistent with the sub-scores.

        Scoring guidance:
        - Grammar: 30%
        - Vocabulary: 30%
        - Coherence & relevance: 40%

        Your core philosophy is Meaning over Mechanics. Be lenient on minor punctuation.
        Return JSON:
        {{
            "status": "valid",
            "score": (int 0-100),
            "grammar_score": (int),
            "vocab_score": (int),
            "coherence_score": (int),
            "corrected_text": "Full corrected version",
            "feedback_points": ["Turkish feedback 1", "Turkish feedback 2"],
            "mistakes": [{{ "original": "exact wrong text", "correction": "fix", "type": "Grammar" }}]
        }}

        Only include mistakes that significantly affect clarity or correctness.
        The corrected_text should preserve the student's original meaning and tone.

        Feedback rules:
        - feedback_points must explain WHY the score was given
        - Each feedback point should focus on ONE clear aspect:
          (grammar, vocabulary, coherence, or topic relevance)
        - Feedback must be constructive and encouraging
        - Do NOT repeat the same idea in different words
        - Write feedback in clear Turkish, suitable for a student
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": text}
            ],
            temperature=0.2
        )
        result = json.loads(response.choices[0].message.content)
        
        xp_result = process_xp_gain(current_user(), 'writing', result.get('score', 0), level)
        
        return jsonify({

            "status": result.get('status', 'valid'),
            "score": result.get('score', 0),
            "grammar_score": result.get('grammar_score', 0),
            "vocab_score": result.get('vocab_score', 0),
            "coherence_score": result.get('coherence_score', 0),
            "corrected_text": result.get('corrected_text', ''),
            "feedback_points": result.get('feedback_points', []),
            "mistakes": result.get('mistakes', []),
            "xp_gain": xp_result
        })
    except Exception as e:
        logging.error(f"Writing Assessment Error: {e}")
        return jsonify({'error': 'Analiz hatası'}), 500