from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import logging
from datetime import datetime, timedelta

LEVEL_BASE_XP = {
    'A1': 0,
    'A2': 500,
    'B1': 1500,
    'B2': 3500,
    'C1': 7500,
    'C2': 15500
}

# SQLAlchemy nesnesini oluşturuyoruz
db = SQLAlchemy()

def init_app(app):
    """
    Flask uygulamasına veritabanını bağlar, havuz ayarlarını yapar ve tabloları oluşturur.
    """
   
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123Umut123@localhost/chatbot_db'
    
    # 2. PERFORMANS VE GÜVENLİK AYARLARI (Connection Pooling)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_size": 10,        # Havuzda sürekli açık tutulacak bağlantı sayısı
        "max_overflow": 20,     # Havuz dolarsa anlık açılabilecek ek bağlantı limiti
        "pool_recycle": 280,    # 280 saniyede bir bağlantıyı yenile (MySQL timeout'u önler)
        "pool_pre_ping": True,  # Her sorgudan önce "Bağlantı yaşıyor mu?" kontrolü yapar
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    
    # Uygulama başladığında tabloları kontrol et
    with app.app_context():
        create_tables_if_not_exist()

def create_tables_if_not_exist():
    """
    Gerekli tablolar yoksa ham SQL ile oluşturur.
    """
    table_queries = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            role VARCHAR(20) DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocab (
            id INT AUTO_INCREMENT PRIMARY KEY,
            word VARCHAR(255) NOT NULL,
            meaning TEXT,
            example TEXT,
            level ENUM('A1', 'A2', 'B1', 'B2', 'C1', 'C2') DEFAULT 'A1',
            word_type VARCHAR(50),
            UNIQUE KEY unique_word (word)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocab_meanings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vocab_id INT NOT NULL,
            meaning TEXT NOT NULL,
            FOREIGN KEY (vocab_id) REFERENCES vocab(id) ON DELETE CASCADE ON UPDATE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocab_examples (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vocab_id INT NOT NULL,
            example TEXT NOT NULL,
            FOREIGN KEY (vocab_id) REFERENCES vocab(id) ON DELETE CASCADE ON UPDATE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocab_levels (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vocab_id INT NOT NULL,
            level ENUM('A1', 'A2', 'B1', 'B2', 'C1', 'C2') NOT NULL,
            FOREIGN KEY (vocab_id) REFERENCES vocab(id) ON DELETE CASCADE ON UPDATE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocab_word_types (
            id INT AUTO_INCREMENT PRIMARY KEY,  
            vocab_id INT NOT NULL,
            word_type VARCHAR(50) NOT NULL,
            FOREIGN KEY (vocab_id) REFERENCES vocab(id) ON DELETE CASCADE ON UPDATE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS topics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name_en VARCHAR(50) NOT NULL,
            name_tr VARCHAR(50) NOT NULL,
            slug VARCHAR(50) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocab_topics (
            vocab_id INT,
            topic_id INT,
            PRIMARY KEY (vocab_id, topic_id),
            FOREIGN KEY (vocab_id) REFERENCES vocab(id) ON DELETE CASCADE,
            FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_levels (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL UNIQUE,
            
            reading_level ENUM('A1', 'A2', 'B1', 'B2', 'C1', 'C2') DEFAULT 'A1',
            reading_xp INT DEFAULT 0,
            reading_cooldown TIMESTAMP NULL DEFAULT NULL,
            
            listening_level ENUM('A1', 'A2', 'B1', 'B2', 'C1', 'C2') DEFAULT 'A1',
            listening_xp INT DEFAULT 0,
            listening_cooldown TIMESTAMP NULL DEFAULT NULL,
            
            writing_level ENUM('A1', 'A2', 'B1', 'B2', 'C1', 'C2') DEFAULT 'A1',
            writing_xp INT DEFAULT 0,
            writing_cooldown TIMESTAMP NULL DEFAULT NULL,
            
            speaking_level ENUM('A1', 'A2', 'B1', 'B2', 'C1', 'C2') DEFAULT 'A1',
            speaking_xp INT DEFAULT 0,
            speaking_cooldown TIMESTAMP NULL DEFAULT NULL,
            
            is_completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """


    ]
    
    try:
        with db.engine.connect() as conn:
            for query in table_queries:
                conn.execute(text(query))
            print("Veritabanı tabloları hazır.")
    except Exception as e:
        print(f"Tablo oluşturma hatası: {e}")

# ==========================================
# KULLANICI İŞLEMLERİ
# ==========================================

def register_user(username, password, email):
    sql = "INSERT INTO users (username, password, email) VALUES (:username, :password, :email)"
    try:
        with db.engine.connect() as conn:
            # Transaction kullanarak ekleme
            with conn.begin():
                conn.execute(text(sql), {"username": username, "password": password, "email": email})
            return True
    except Exception as e:
        print(f"Kullanıcı kayıt hatası: {e}")
        return False

def get_user_by_username(username):
    sql = "SELECT * FROM users WHERE username = :username"
    try:
        with db.engine.connect() as conn:
            # Result mapping ile dönüyoruz, tuple olarak erişilebilir (row[0], row[1]...)
            result = conn.execute(text(sql), {"username": username}).fetchone()
            return result
    except Exception as e:
        print(f"Kullanıcı getirme hatası: {e}")
        return None

def get_user_by_id(user_id):
    sql = "SELECT * FROM users WHERE id = :uid"
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text(sql), {"uid": user_id}).fetchone()
            return result
    except Exception as e:
        print(f"Kullanıcı ID ile getirme hatası: {e}")
        return None
    
def update_user_info(user_id, name=None, new_email=None):
    fields = []
    params = {"uid": user_id}
    
    if name:
        fields.append("username = :username")
        params["username"] = name
    if new_email:
        fields.append("email = :email")
        params["email"] = new_email
    
    if not fields:
        return False  # Güncellenecek bir şey yok

    sql = f"UPDATE users SET {', '.join(fields)} WHERE id = :uid"
    
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(sql), params)
        return True
    except Exception as e:
        print(f"Kullanıcı bilgi güncelleme hatası: {e}")
        return False

def update_user_password(user_id, new_hashed_password):
    sql = "UPDATE users SET password = :password WHERE id = :uid"
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(sql), {"password": new_hashed_password, "uid": user_id})
        return True
    except Exception as e:
        print(f"Kullanıcı şifre güncelleme hatası: {e}")
        return False        
# ==========================================
# KELİME (VOCAB) İŞLEMLERİ
# ==========================================

def get_vocab_details(vocab_id):
    """
    Tek bir kelimenin detaylarını (anlamlar ve örnekler dahil) getirir.
    """
    try:
        with db.engine.connect() as conn:
            # 1. Ana tabloyu çek
            vocab_sql = "SELECT id, word, meaning, example FROM vocab WHERE id = :vid"
            row = conn.execute(text(vocab_sql), {"vid": vocab_id}).fetchone()
            
            if not row: return None
            
            vid, word, single_meaning, single_example = row

            # 2. Anlamları çek
            m_sql = "SELECT meaning FROM vocab_meanings WHERE vocab_id = :vid ORDER BY id"
            meanings = [r[0] for r in conn.execute(text(m_sql), {"vid": vid}).fetchall()]

            # 3. Örnekleri çek
            e_sql = "SELECT example FROM vocab_examples WHERE vocab_id = :vid ORDER BY id"
            examples = [r[0] for r in conn.execute(text(e_sql), {"vid": vid}).fetchall()]

            # 4. Seviyeleri çek (varsayılan olarak alt tabloda saklanıyorsa)
            l_sql = "SELECT level FROM vocab_levels WHERE vocab_id = :vid ORDER BY id"
            levels = [r[0] for r in conn.execute(text(l_sql), {"vid": vid}).fetchall()]

            # 5. Kelime türlerini çek
            t_sql = "SELECT word_type FROM vocab_word_types WHERE vocab_id = :vid ORDER BY id"
            word_types = [r[0] for r in conn.execute(text(t_sql), {"vid": vid}).fetchall()]

            # 6. Eğer alt tablolarda yoksa ana tablodaki stringi parçala (Fallback)
            if not meanings and single_meaning:
                meanings = [m.strip() for m in single_meaning.split(';') if m.strip()]
            if not examples and single_example:
                examples = [e.strip() for e in single_example.split(';') if e.strip()]

            return (vid, word, meanings, examples, levels, word_types)
    except Exception as e:
        print(f"Vocab detay hatası: {e}")
        return None

# Sitenin sözlük kısmı için optimize edilmiş toplu çekme
def get_all_vocabs_with_details(letter=None):
    """
    OPTIMIZE VE SIRALI VERSİYON:
    1. SQL ile harfe göre filtreler.
    2. Python ile A1 -> C1 sırasına göre dizer.
    """
    try:
        # 1. SQL SORGUSU (Aynı kalıyor)
        base_sql = """
            SELECT 
                v.id, 
                v.word,
                GROUP_CONCAT(DISTINCT vm.meaning SEPARATOR '||') as meanings,
                GROUP_CONCAT(DISTINCT ve.example SEPARATOR '||') as examples,
                GROUP_CONCAT(DISTINCT vl.level SEPARATOR '||') as levels,
                GROUP_CONCAT(DISTINCT vt.word_type SEPARATOR '||') as word_types
            FROM vocab v
            LEFT JOIN vocab_meanings vm ON v.id = vm.vocab_id
            LEFT JOIN vocab_examples ve ON v.id = ve.vocab_id
            LEFT JOIN vocab_levels vl ON v.id = vl.vocab_id
            LEFT JOIN vocab_word_types vt ON v.id = vt.vocab_id
        """

        params = {}
        if letter and letter != 'ALL':
            base_sql += " WHERE v.word LIKE :pattern "
            params['pattern'] = f"{letter}%"
        
        base_sql += " GROUP BY v.id "
        
        with db.engine.connect() as conn:
            rows = conn.execute(text(base_sql), params).fetchall()
            
        vocabs = []
        for r in rows:
            vid, word, meanings_str, examples_str, levels_str, types_str = r

            meanings_list = meanings_str.split('||') if meanings_str else []
            examples_list = examples_str.split('||') if examples_str else []
            levels_list = levels_str.split('||') if levels_str else []
            types_list = types_str.split('||') if types_str else []

            vocabs.append({
                'id': vid,
                'word': word,
                'meanings': meanings_list,
                'examples': examples_list,
                'levels': levels_list,
                'word_types': types_list
            })

        # --- YENİ EKLENEN KISIM: SIRALAMA MANTIĞI ---
        
        # Seviye öncelik haritası (Sıralama için puanlama)
        level_priority = {
            'A1': 1, 
            'A2': 2, 
            'B1': 3, 
            'B2': 4, 
            'C1': 5, 
            'C2': 6
        }

        def sort_key(item):
            # 1. Kriter: Seviye (En düşük seviye öne gelir)
            # Eğer kelimenin seviyesi yoksa (boş liste), sona at (99 puan)
            first_level = item['levels'][0] if item['levels'] else None
            priority = level_priority.get(first_level, 99)
            
            # 2. Kriter: Kelimenin kendisi (Alfabetik)
            # Eğer seviyeler aynıysa (örn: iki tane A1 kelimesi), alfabetik sırala
            return (priority, item['word'].lower())

        # Listeyi bu anahtara göre sırala
        vocabs.sort(key=sort_key)
        
        # -------------------------------------------

        return vocabs

    except Exception as e:
        print(f"Toplu vocab çekme hatası: {e}")
        return []

# Admin panelinde sadece liste göstermek için (Daha hafif versiyon)
def get_all_vocabs():
    try:
        sql = "SELECT id, word FROM vocab ORDER BY id"
        with db.engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
            return [{'id': r[0], 'word': r[1]} for r in rows]
    except Exception as e:
        print(f"Vocab listesi hatası: {e}")
        return []

def add_vocab_with_details(word, meanings=None, examples=None, levels=None, word_types=None):
    """
    Yeni kelime, anlamlar ve örnekler ekler. Transaction kullanır.
    
    OTOMATION:
    - Eğer meanings string ve semicolon içeriyorsa, otomatik parse et
    - Eğer levels/word_types None ise, boş bırak
    """
    meanings = meanings or []
    examples = examples or []
    levels = levels or []
    word_types = word_types or []
    
    # Otomation: meanings string ise ve `;` içeriyorsa parse et
    if isinstance(meanings, str) and ';' in meanings:
        meanings = [m.strip() for m in meanings.split(';') if m.strip()]
    elif isinstance(meanings, str):
        meanings = [meanings.strip()] if meanings.strip() else []
    
    # Ana tablo için düz metin versiyonları
    single_meaning = '; '.join(meanings) if meanings else None
    single_example = '; '.join(examples) if examples else None

    try:
        with db.engine.connect() as conn:
            # Transaction Başlat (Hata olursa hepsi iptal olur)
            with conn.begin(): 
                # 1. Kelime var mı kontrol et
                check_sql = "SELECT id FROM vocab WHERE word = :word"
                existing = conn.execute(text(check_sql), {"word": word}).fetchone()
                
                if existing:
                    return existing[0]

                # 2. Ana tabloya ekle
                ins_sql = "INSERT INTO vocab (word, meaning, example) VALUES (:word, :meaning, :example)"
                result = conn.execute(text(ins_sql), {"word": word, "meaning": single_meaning, "example": single_example})
                vid = result.lastrowid

                # 3. Anlamları ekle
                if meanings:
                    m_sql = "INSERT INTO vocab_meanings (vocab_id, meaning) VALUES (:vid, :m)"
                    for m in meanings:
                        conn.execute(text(m_sql), {"vid": vid, "m": m})

                # 4. Örnekleri ekle
                if examples:
                    e_sql = "INSERT INTO vocab_examples (vocab_id, example) VALUES (:vid, :e)"
                    for e in examples:
                        conn.execute(text(e_sql), {"vid": vid, "e": e})

                # 5. Seviyeleri ekle
                if levels:
                    l_sql = "INSERT INTO vocab_levels (vocab_id, level) VALUES (:vid, :lvl)"
                    for lvl in levels:
                        if isinstance(lvl, str) and lvl.strip():
                            conn.execute(text(l_sql), {"vid": vid, "lvl": lvl.strip()})

                # 6. Kelime türlerini ekle
                if word_types:
                    t_sql = "INSERT INTO vocab_word_types (vocab_id, word_type) VALUES (:vid, :wt)"
                    for wt in word_types:
                        if isinstance(wt, str) and wt.strip():
                            conn.execute(text(t_sql), {"vid": vid, "wt": wt.strip()})
            
            return vid
    except Exception as e:
        print(f"Vocab ekleme hatası: {e}")
        return None

def update_vocab_with_details(vocab_id, word, meanings=None, examples=None, levels=None, word_types=None):
    """
    Mevcut kelimeyi günceller. Eski anlam/örnekleri silip yenilerini ekler.
    
    AUTOMATION:
    - Eğer meanings string ve semicolon içeriyorsa, otomatik parse et
    - Eğer levels/word_types None ise, boş bırak
    """
    meanings = meanings or []
    examples = examples or []
    levels = levels or []
    word_types = word_types or []
    
    # Otomation: meanings string ise ve `;` içeriyorsa parse et
    if isinstance(meanings, str) and ';' in meanings:
        meanings = [m.strip() for m in meanings.split(';') if m.strip()]
    elif isinstance(meanings, str):
        meanings = [meanings.strip()] if meanings.strip() else []
    
    single_meaning = '; '.join(meanings) if meanings else None
    single_example = '; '.join(examples) if examples else None

    try:
        with db.engine.connect() as conn:
            with conn.begin():
                # 1. Ana tabloyu güncelle
                upd_sql = "UPDATE vocab SET word = :word, meaning = :sm, example = :se WHERE id = :vid"
                conn.execute(text(upd_sql), {"word": word, "sm": single_meaning, "se": single_example, "vid": vocab_id})

                # 2. Eski detayları sil
                conn.execute(text("DELETE FROM vocab_meanings WHERE vocab_id = :vid"), {"vid": vocab_id})
                conn.execute(text("DELETE FROM vocab_examples WHERE vocab_id = :vid"), {"vid": vocab_id})
                # 2b. Eski seviye ve tür kayıtlarını sil
                conn.execute(text("DELETE FROM vocab_levels WHERE vocab_id = :vid"), {"vid": vocab_id})
                conn.execute(text("DELETE FROM vocab_word_types WHERE vocab_id = :vid"), {"vid": vocab_id})

                # 3. Yeni anlamları ekle
                if meanings:
                    m_sql = "INSERT INTO vocab_meanings (vocab_id, meaning) VALUES (:vid, :m)"
                    for m in meanings:
                        conn.execute(text(m_sql), {"vid": vocab_id, "m": m})

                # 4. Yeni örnekleri ekle
                if examples:
                    e_sql = "INSERT INTO vocab_examples (vocab_id, example) VALUES (:vid, :e)"
                    for e in examples:
                        conn.execute(text(e_sql), {"vid": vocab_id, "e": e})

                # 5. Yeni seviyeleri ekle
                if levels:
                    l_sql = "INSERT INTO vocab_levels (vocab_id, level) VALUES (:vid, :lvl)"
                    for lvl in levels:
                        if isinstance(lvl, str) and lvl.strip():
                            conn.execute(text(l_sql), {"vid": vocab_id, "lvl": lvl.strip()})

                # 6. Yeni kelime türlerini ekle
                if word_types:
                    t_sql = "INSERT INTO vocab_word_types (vocab_id, word_type) VALUES (:vid, :wt)"
                    for wt in word_types:
                        if isinstance(wt, str) and wt.strip():
                            conn.execute(text(t_sql), {"vid": vocab_id, "wt": wt.strip()})
            
            return True
    except Exception as e:
        print(f"Vocab güncelleme hatası: {e}")
        return False


# ==========================================
# KULLANICI SEVİYE (PLACEMENT) İŞLEMLERİ
# ==========================================


#kullanıcı sınavı tamamlamış mı?
def has_user_completed_placement(user_id):
    """
    Kullanıcının placement sınavını tamamlayıp tamamlamadığını kontrol eder.
    """
    sql = "SELECT is_completed FROM user_levels WHERE user_id = :uid"
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(sql), {"uid": user_id}).fetchone()
            if row:
                return row.is_completed
            return False
    except Exception as e:
        print(f"Placement tamamlama kontrol hatası: {e}")
        return False
    
    
def save_user_placement_result(user_id, results):
    """
    Placement sonucunu kaydederken seviyenin taban XP'sini de atar.
    results: {'reading': 'B1', 'listening': 'A2', ...}
    """
    # Seviyeleri al
    r_lvl = results.get('reading', 'A1')
    l_lvl = results.get('listening', 'A1')
    w_lvl = results.get('writing', 'A1')
    s_lvl = results.get('speaking', 'A1')

    # Taban XP'leri belirle (Sabit tablodan çekiyoruz)
    r_xp = LEVEL_BASE_XP.get(r_lvl, 0)
    l_xp = LEVEL_BASE_XP.get(l_lvl, 0)
    w_xp = LEVEL_BASE_XP.get(w_lvl, 0)
    s_xp = LEVEL_BASE_XP.get(s_lvl, 0)

    sql = """
    INSERT INTO user_levels 
    (user_id, reading_level, reading_xp, listening_level, listening_xp, writing_level, writing_xp, speaking_level, speaking_xp, is_completed)
    VALUES (:uid, :rl, :rx, :ll, :lx, :wl, :wx, :sl, :sx, TRUE)
    ON DUPLICATE KEY UPDATE
        reading_level = :rl, reading_xp = :rx,
        listening_level = :ll, listening_xp = :lx,
        writing_level = :wl, writing_xp = :wx,
        speaking_level = :sl, speaking_xp = :sx,
        is_completed = TRUE
    """
    
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(sql), {
                    "uid": user_id,
                    "rl": r_lvl, "rx": r_xp,
                    "ll": l_lvl, "lx": l_xp,
                    "wl": w_lvl, "wx": w_xp,
                    "sl": s_lvl, "sx": s_xp
                })
        return True
    except Exception as e:
        print(f"Placement save error: {e}")
        return False

def get_user_levels(user_id):
    """
    Kullanıcının seviye ve XP bilgilerini getirir.
    Dönüş formatı: { 'reading': {'level': 'B1', 'xp': 1550}, ... }
    """
    sql = "SELECT * FROM user_levels WHERE user_id = :uid"
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(sql), {"uid": user_id}).fetchone()
            if row:
                return {
                    "reading": {"level": row.reading_level, "xp": row.reading_xp},
                    "listening": {"level": row.listening_level, "xp": row.listening_xp},
                    "writing": {"level": row.writing_level, "xp": row.writing_xp},
                    "speaking": {"level": row.speaking_level, "xp": row.speaking_xp},
                    "is_completed": row.is_completed
                }
            return None
    except Exception as e:
        print(f"Seviye getirme hatası: {e}")
        return None

def update_user_skill_stats(user_id, skill, new_level, new_xp):
    """
    XP Manager'dan gelen hesaplanmış veriyi veritabanına yazar.
    skill: 'reading', 'listening', 'writing', 'speaking'
    """
    # Güvenlik kontrolü
    valid_skills = ['reading', 'listening', 'writing', 'speaking']
    if skill not in valid_skills:
        return False

    # Dinamik SQL (Sütun isimleri değişkenden geliyor)
    sql = f"""
        UPDATE user_levels 
        SET {skill}_level = :lvl, {skill}_xp = :xp 
        WHERE user_id = :uid
    """
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(sql), {"lvl": new_level, "xp": new_xp, "uid": user_id})
        return True
    except Exception as e:
        print(f"Skill update hatası: {e}")
        return False    

# ==========================================
# SINAV CEZA (COOLDOWN) YÖNETİMİ
# ==========================================

def set_skill_cooldown(user_id, skill, hours=3):
    """
    Kullanıcıya sınavdan kaldığı için bekleme süresi (ceza) tanımlar.
    skill: 'reading', 'listening' vb.
    hours: Kaç saat ceza verileceği (Varsayılan 3)
    """
    valid_skills = ['reading', 'listening', 'writing', 'speaking']
    if skill not in valid_skills: return False
    
    # Şu anki zamana 3 saat ekle
    cooldown_time = datetime.now() + timedelta(hours=hours)
    
    sql = f"UPDATE user_levels SET {skill}_cooldown = :time WHERE user_id = :uid"
    
    try:
        with db.engine.connect() as conn:
            with conn.begin():
                conn.execute(text(sql), {"time": cooldown_time, "uid": user_id})
        return True
    except Exception as e:
        print(f"Cooldown atama hatası: {e}")
        return False

def check_skill_cooldown(user_id, skill):
    """
    Kullanıcının sınav cezası var mı kontrol eder.
    Dönüş:
        - None: Ceza yok, sınava girebilir.
        - Datetime objesi: Cezası var, bu tarihe kadar beklemeli.
    """
    valid_skills = ['reading', 'listening', 'writing', 'speaking']
    if skill not in valid_skills: return None
    
    sql = f"SELECT {skill}_cooldown FROM user_levels WHERE user_id = :uid"
    
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(sql), {"uid": user_id}).fetchone()
            if row and row[0]:
                limit_time = row[0]
                # Eğer şu anki zaman, limit zamanından küçükse (henüz dolmadıysa)
                if datetime.now() < limit_time:
                    return limit_time # Hala cezalı
                
                # Süre dolmuşsa, veritabanındaki kaydı temizleyelim (Clean up)
                # Bu opsiyoneldir ama veritabanını temiz tutar.
                with conn.begin():
                     conn.execute(text(f"UPDATE user_levels SET {skill}_cooldown = NULL WHERE user_id = :uid"), {"uid": user_id})
                return None
                
            return None # Kayıt yok veya NULL
    except Exception as e:
        print(f"Cooldown kontrol hatası: {e}")
        return None    