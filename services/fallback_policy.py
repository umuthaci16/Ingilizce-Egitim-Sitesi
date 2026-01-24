# services/fallback_policy.py

class FallbackPolicy:
    def __init__(self):
        self.min_words = 2
        self.default_limits = [6, 4, 2]
        self.pos_strict = True

    def get_attempts(self, primary_topic, secondary_topic):
        """
        Fallback deneme sırası.
        Her adım bir parametre seti döner.
        """
        attempts = []

        # 1️⃣ Strict: primary topic + strict POS
        attempts.append({
            "topic": primary_topic,
            "use_secondary": False,
            "pos_strict": True
        })

        # 2️⃣ Relax POS
        attempts.append({
            "topic": primary_topic,
            "use_secondary": False,
            "pos_strict": False
        })

        # 3️⃣ Add secondary topic
        if secondary_topic:
            attempts.append({
                "topic": primary_topic,
                "use_secondary": True,
                "pos_strict": False
            })

        # 4️⃣ Fallback to secondary as primary
        if secondary_topic:
            attempts.append({
                "topic": secondary_topic,
                "use_secondary": False,
                "pos_strict": False
            })

        return attempts
