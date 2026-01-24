from database import db
from sqlalchemy import text
import logging
from services.fallback_policy import FallbackPolicy

logger = logging.getLogger(__name__)

POS_MAP = {
    "noun": "%n.%",
    "verb": "%v.%",
    "adjective": "%adj%",
    "adverb": "%adv%",
    "any": "%"
}

RELAX_MAP = {
    "adverb": ["adjective", "any"],
    "adjective": ["noun", "any"],
    "verb": ["any"],
    "noun": ["any"]
}

pos_plan = [
    ("noun", 3),
    ("verb", 3),
    ("adjective", 2),
    ("adverb", 2),
]

def get_target_words(level, primary_topic, secondary_topic=None, limit=10):
    policy = FallbackPolicy()
    attempts = policy.get_attempts(primary_topic, secondary_topic)

    try:
        with db.engine.connect() as conn:

            for attempt in attempts:
                results = []

                for pos, count in pos_plan:
                    pos_pattern = POS_MAP.get(pos, "%")

                    words = _fetch_words(
                        conn,
                        level,
                        attempt["topic"],
                        pos_pattern,
                        count
                    )
                    if len(words) < count:
                        relaxed_chain = RELAX_MAP.get(pos, [])
                        for relaxed_pos in relaxed_chain:
                            missing = count - len(words)
                            relaxed_pattern = POS_MAP.get(relaxed_pos, "%")

                            relaxed_words = _fetch_words(
                                conn,
                                level,
                                attempt["topic"],
                                relaxed_pattern,
                                missing
                            )
                            words.extend(relaxed_words)
                            if len(words) >= count:
                                break
                            
                    results.extend(words)

                # yeterli kelime bulunduysa → DUR
                if len(results) >= policy.min_words:
                    logger.info(
                        f"Target words selected | topic={attempt['topic']} | pos_strict={attempt['pos_strict']}"
                    )
                    return results

    except Exception:
        logger.exception("Target word selector error")

    # hiçbir deneme başarılı değilse
    logger.warning(
        f"Target word fallback failed | level={level} | primary={primary_topic}"
    )
    return []


def _fetch_words(conn, level, topic, pos_pattern, limit):
    sql = """
        SELECT v.word, v.word_type, v.meaning
        FROM vocab v
        JOIN vocab_topics vt ON v.id = vt.vocab_id
        JOIN topics t ON vt.topic_id = t.id
        WHERE v.level = :level
          AND t.slug = :topic
          AND v.word_type LIKE :pos
        ORDER BY RAND()
        LIMIT :limit
    """

    rows = conn.execute(
        text(sql),
        {
            "level": level,
            "topic": topic,
            "pos": pos_pattern,
            "limit": limit
        }
    ).fetchall()

    return [
        {"word": r[0], "pos": r[1], "meaning": r[2]}
        for r in rows
    ]
