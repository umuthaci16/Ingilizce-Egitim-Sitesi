def build_prompt(
    skill,
    level,
    primary_topic,
    secondary_topic=None,
    target_words=None
):   
    if skill == "speaking":
        print("speaking primary_topic:", primary_topic)
        print("speaking secondary_topic:", secondary_topic)
        print("speaking target_words:", target_words)
        print("level:", level)
        return build_speaking_prompt(level, primary_topic, secondary_topic, target_words)
    
    if skill == "listening":
        print("listening primary_topic:", primary_topic)
        print("listening secondary_topic:", secondary_topic)
        print("listening target_words:", target_words)
        print("level:", level)
        return build_listening_prompt(level, primary_topic, secondary_topic, target_words)

    if skill == "reading":
        print("reading primary_topic:", primary_topic)
        print("reading secondary_topic:", secondary_topic)
        print("reading", "target_words:", target_words)
        print("level:", level)
        return build_reading_prompt(level, primary_topic, secondary_topic, target_words)

    if skill == "writing":
        print("writing primary_topic:", primary_topic)
        print("writing secondary_topic:", secondary_topic)
        print("writing target_words:", target_words)
        print("level:", level)
        return build_writing_prompt(level, primary_topic, secondary_topic, target_words)

    raise ValueError("Unknown skill")



def build_reading_prompt(level, primary_topic, secondary_topic, target_words):
    target_word_list = [w["word"] for w in target_words]
    vocab_str = ", ".join(target_word_list)

    if target_words:
      example_word = target_words[0]["word"]
      example_meaning = target_words[0]["meaning"]
    else:
      example_word = "example"
      example_meaning = "örnek"

    system_message = (
        "You are an English teacher creating structured reading lessons.\n"
        "Return ONLY a valid JSON object. Do not add explanations."
    )

    user_message = f"""
Create a reading lesson for an English learner.

Level: {level}

PRIMARY TOPIC (DO NOT CHANGE):
{primary_topic}

SECONDARY TOPIC (background only):
{secondary_topic}

Target words for this lesson:
{vocab_str}

Instructions:
- The reading text MUST clearly be about the PRIMARY topic
- The title and the FIRST sentence must reflect the primary topic
- The secondary topic may appear lightly but must not replace the main topic
- Target words are the learning focus; use each naturally
- Vocabulary and grammar must stay at {level} level
- Do NOT define or translate words in the text
- Write a clear, coherent, neutral reading passage

After the text:
- Create exactly 5 comprehension questions
- Each question must have 4 options (A, B, C, D)
- Only ONE option is correct
- Provide the exact sentence from the text as evidence

Output JSON format:
{{
  "title": "...",
  "text": "...",
  "challenge_words": [
    {{ "word": "{example_word}", "meaning_tr": "{example_meaning}" }}
  ],
  "questions": [
    {{
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "evidence": "exact sentence"
    }}
  ]
}}
"""

    return [ 
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

def build_writing_prompt(level, primary_topic, secondary_topic, target_words):
    target_word_list = [w["word"] for w in target_words]
    vocab_str = ", ".join(target_word_list)

    system_message = (
        "You are an English writing instructor.\n"
        "You help learners practice writing through clear, focused tasks."
    )

    user_message = f"""
Create a writing assignment for a student learning English on the given topics.

Level: {level}
Primary topic: {primary_topic}
Secondary topic: {secondary_topic}

Target words for this writing task:
{vocab_str}

Instructions:
- Write ONE clear writing question or task
- The task MUST focus on the primary topic
- The task should invite personal opinion, experience, or simple reasoning
- Do NOT write a sample answer
- Do NOT explain the target words
- Keep the task appropriate for {level} level
- Output ONLY the writing task text
"""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]


def build_sentence_listening_prompt(level, primary_topic, target_words):
    target_word_list = [w["word"] for w in target_words]
    vocab_str = ", ".join(target_word_list)

    system_message = (
        "You are a native English speaker creating listening practice sentences.\n"
        "Output ONLY one sentence. No explanations."
    )

    user_message = f"""
Generate ONE natural listening sentence.

Level: {level}

MANDATORY CONTEXT:
The sentence MUST clearly take place in the context of:
{primary_topic}

Do NOT use generic openings such as:
- "A student wants to..."
- "Someone talks about..."
- "People think that..."

Target words:
{vocab_str}

Rules:
- Natural spoken English
- Clear real-life situation
- Use some target words naturally
- Max 22 words
"""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

def build_sentence_pronunciation_prompt(level, primary_topic, target_words):
    target_word_list = [w["word"] for w in target_words]
    vocab_str = ", ".join(target_word_list)

    system_message = (
        "You are an English pronunciation coach.\n"
        "Output ONLY one short sentence. No explanations."
    )

    user_message = f"""
Generate ONE short sentence for pronunciation practice.

Level: {level}

Context:
The sentence should clearly relate to:
{primary_topic}

Target words:
{vocab_str}

Rules:
- Short and clear sentence
- Easy to pronounce
- Natural rhythm
- Prefer simple structure
- Max 14 words
"""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]


def build_listening_prompt(level, primary_topic, secondary_topic, target_words):
    target_word_list = [w["word"] for w in target_words]
    vocab_str = ", ".join(target_word_list)

    system_message = (
        "You are an English teacher creating a complete listening lesson.\n"
        "Return ONLY a valid JSON object. Do not add explanations or comments."
    )

    user_message = f"""
Create a listening lesson for an English learner.

Level: {level}

PRIMARY TOPIC (main focus – MUST dominate the text):
{primary_topic}

SECONDARY TOPIC (background only – optional, light support):
{secondary_topic}

Target words (use SOME naturally, do NOT force all):
{vocab_str}

Listening text rules:
- 80–120 words
- Natural spoken English
- Clear real-life situation
- MUST clearly relate to the PRIMARY topic
- Secondary topic may appear lightly but must NOT replace the main topic
- Do NOT define or translate words
- Do NOT mention "student", "exercise", or "listening task"

After the listening text:

1) Create EXACTLY 5 fill-in-the-blank questions
   - Blanks MUST come directly from the listening text
   - Each blank replaces ONE important word or short phrase
   - Do NOT invent new sentences

2) Create EXACTLY 5 multiple-choice questions
   - Questions must test understanding of the listening text
   - Each question has 4 options (A, B, C, D)
   - Only ONE correct answer

Output JSON format (STRICT):
{{
  "title": "Short clear title",
  "audio_text": "Full listening text",
  "fill_in_the_blanks": [
    {{ "sentence": "... ___ ...", "answer": "..." }}
  ],
  "multiple_choice": [
    {{
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0
    }}
  ]
}}
"""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

def build_speaking_prompt(level, primary_topic, secondary_topic, target_words):
    target_word_list = [w["word"] for w in target_words]
    vocab_str = ", ".join(target_word_list)

    system_message = (
        "You are an English teacher creating a speaking task.\n"
        "Return ONLY a valid JSON object. Do not add explanations or markdown formatting."
    )

    user_message = f"""
Create a speaking task for an English learner.

Level: {level}
PRIMARY TOPIC: {primary_topic}
SECONDARY TOPIC (background only): {secondary_topic}
Target words (do NOT mention them in the task): {vocab_str}

Task rules:
- Create ONE speaking prompt
- Require 20–30 seconds of speaking
- Encourage explanation, opinion, or personal experience
- Topic MUST clearly reflect the PRIMARY topic
- Do NOT ask the student to read or repeat anything
- Do NOT mention target words explicitly

Output JSON format:
{{
  "title": "Speaking Task",
  "task": "The actual question or instruction for the student to speak about.",
}}
"""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]
