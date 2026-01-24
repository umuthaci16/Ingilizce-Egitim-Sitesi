from flask import Blueprint, render_template, request, jsonify
import os, logging, json, difflib
from openai import OpenAI
from services.lesson_pipeline import generate_lesson
from utils import current_user,placement_completed_required
from database import get_user_levels
listening_bp = Blueprint("listening", __name__)
from skills.xp_manager import process_xp_gain,check_exam_eligibility

# OpenAI Başlatma
try:
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
except Exception as e:
    logging.warning(f"OpenAI Client yüklenirken hata: {e}")
    client = None


@listening_bp.route('/listening')
@placement_completed_required
def listening_page():
    user_id = current_user()
    levels = get_user_levels(user_id) or {}
    level = levels.get("listening", {}).get("level", "B1")
    exam_needed = check_exam_eligibility(user_id, 'listening')

    return render_template('listening.html', level=level, exam_needed=exam_needed)

@listening_bp.route("/api/generate_listening", methods=["POST"])
@placement_completed_required
def generate_listening():
    try:
        data = request.json
        level = data.get("level", "B1")
        print("Listening generate leveli:", level)

        raw_lesson = generate_lesson(skill="listening",level=level)   

        processed_lesson = {
            "title": raw_lesson.get("title", "Listening Exercise"),
            "listening_text": raw_lesson.get("audio_text", raw_lesson.get("listening_text", ""))
        }

        processed_blanks = []
        raw_blanks = raw_lesson.get("fill_in_the_blanks", raw_lesson.get("blanks", []))
        
        for item in raw_blanks:
            if "sentence" in item and "___" in item["sentence"]:
                parts = item["sentence"].split("___")
                prefix = parts[0] if len(parts) > 0 else ""
                suffix = parts[1] if len(parts) > 1 else ""
                correct = item.get("answer", "")
            else:
                prefix = item.get("prefix", "")
                suffix = item.get("suffix", "")
                correct = item.get("correct", item.get("answer", ""))
            
            processed_blanks.append({
                "prefix": prefix,
                "correct": correct,
                "suffix": suffix
            })
        
        processed_lesson["blanks"] = processed_blanks

        processed_mc = []
        raw_mc = raw_lesson.get("multiple_choice", raw_lesson.get("mc", []))

        for item in raw_mc:

            correct_val = ""
            options = item.get("options", [])
            
           
            if "correct_index" in item:
                idx = item["correct_index"]
                if isinstance(idx, int) and 0 <= idx < len(options):
                    correct_val = options[idx]
          
            elif "correct" in item:
                correct_val = item["correct"]
            
            processed_mc.append({
                "question": item.get("question", ""),
                "options": options,
                "correct": correct_val
            })

        processed_lesson["mc"] = processed_mc

       
        return jsonify({
            "status": "ok",
            "lesson": processed_lesson
        })

    except Exception as e:
        
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": "Ders oluşturulurken bir hata oluştu."
        }), 500

@listening_bp.route("/api/assess_listening", methods=["POST"])
@placement_completed_required
def assess_listening():
    data = request.json

    gist = assess_listening_gist(
        data["listening_text"],
        data["gist_answer"],
        data["level"],
        data["title"]
    )

    blanks = assess_blanks(data["blanks"])
    mc = assess_mc(data["mc"])

    final_score = int(
        gist["score"] * 0.4 +
        blanks["score"] * 0.3 +
        mc["score"] * 0.3
    )
    task_level = data.get("level", "B1")
    xp_result = process_xp_gain(current_user(), 'listening', final_score, task_level)

    return jsonify({
        "gist": gist,
        "blanks": blanks,
        "multiple_choice": mc,
        "final_score": final_score,
        "xp_gain": xp_result
    })

def assess_listening_gist(text, summary, level, title):
    print("Listening asses leveli:", level)
    system_message = f"""
    You are an English teacher assessing listening comprehension.

    Level: {level}
    Listening text title: "{title}"

    The student summary is written in Turkish.
    Evaluate comprehension, not translation accuracy.

    Return ONLY valid JSON:
    {{
      "score": 0-100,
      "feedback": "Turkish feedback"
    }}
    """

    user_message = f"""
    Listening Text:
    {text}

    Student Summary (Turkish):
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

    return json.loads(resp.choices[0].message.content)


def assess_blanks(blanks):
    correct = 0
    for b in blanks:
        if b["user"].strip().lower() == b["correct"].strip().lower():
            correct += 1

    score = int((correct / len(blanks)) * 100)

    return {
        "score": score,
        "correct": correct,
        "total": len(blanks)
    }

def assess_mc(mc):
    correct = sum(1 for q in mc if q["user"] == q["correct"])
    score = int((correct / len(mc)) * 100)

    return {
        "score": score,
        "correct": correct,
        "total": len(mc)
    }