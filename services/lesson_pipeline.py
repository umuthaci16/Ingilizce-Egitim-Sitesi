from services.lesson_topic_selector import select_lesson_topics
from services.target_word_selector import get_target_words
from services.prompt_builder import build_prompt
from dotenv import load_dotenv
from openai import OpenAI
import json, os
import logging

load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

logger = logging.getLogger(__name__)

def generate_lesson(skill,level):
    """
    skill:
        reading
        writing
        listening
        speaking
    """

    try:
        # 1️⃣ Topic seçimi
        primary_topic, secondary_topic = select_lesson_topics(level, skill)

        # 2️⃣ Target words seçimi
        target_words = get_target_words(
            level=level,
            primary_topic=primary_topic,
            secondary_topic=secondary_topic
        )

        
        if not target_words:
            return {"error": "Content could not be generated for this level and topic. (level={level}, topic={primary_topic}, secondary_topic={secondary_topic})"}


      
        print("FİNAL skill:", skill)
        # 4️⃣ Prompt oluştur
        messages = build_prompt(
            skill=skill,
            level=level,
            primary_topic=primary_topic,
            secondary_topic=secondary_topic,
            target_words=target_words
        )
        
        # 5️⃣ GPT çağrısı
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.9,
            response_format=(
                {"type": "json_object"}
                if skill in ["reading", "listening", "speaking"]
                else None
            )

        )

        content = response.choices[0].message.content

        if skill  in ["reading", "listening", "speaking"]:
            return json.loads(content)

        # 7️⃣ Writing / sentence → text
        return content.strip().replace('"', '')

    except Exception as e:
        logger.exception("Lesson generation failed")
        raise e
