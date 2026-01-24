import random

# Anchor topics (lesson taşıyıcılar)
ANCHOR_TOPICS_BY_LEVEL = {
    "A1": ["daily-life", "emotions", "communication-language", "food-cooking", "body-health","nature-environment"],
    "A2": ["daily-life", "emotions", "communication-language", "food-cooking", "body-health","nature-environment"],
    "B1": ["education-learning", "work-business", "personal-traits", "social-states","nature-environment"],
    "B2": ["education-learning", "work-business", "arts-media","technology-digital","abstract-concepts"],
    "C1": ["abstract-concepts", "social-states", "technology-digital", "law-ethics", "politics-society", "spirituality-beliefs"],
}

# Secondary topics (bağlam zenginleştirici)
SECONDARY_TOPICS = [
    "daily-life",
    "education-learning",
    "work-business",
    "communication-language"
]

def select_lesson_topics(level: str, skill: str):
    """
    Returns:
        primary_topic_slug,
        secondary_topic_slug (or None)
    """

    # 1. Anchor topics (level bazlı)
    anchors = ANCHOR_TOPICS_BY_LEVEL.get(level, ANCHOR_TOPICS_BY_LEVEL["A2"])
    primary_topic = random.choice(anchors)

    # 2. Secondary topic (primary ile aynı olamaz)
    secondary_candidates = [
        t for t in SECONDARY_TOPICS if t != primary_topic
    ]

    secondary_topic = random.choice(secondary_candidates) if secondary_candidates else None

    return primary_topic, secondary_topic
