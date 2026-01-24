from functools import wraps
from flask import session, flash, redirect, url_for
import requests, urllib.parse, re
from database import has_user_completed_placement

# --- Login Kontrolü ---
def is_user_logged_in():
    return 'user_id' in session

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_user_logged_in():
            return redirect(url_for('auth.login')) # Dikkat: auth.login oldu
        return f(*args, **kwargs)
    return decorated_function

# utils.py içine ekle:

def current_user():
    if is_user_logged_in():
        return session.get('user_id')
        
    return None

def current_user_name():
    if is_user_logged_in():
        return session.get('username')
        
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Giriş yapmış mı?
        if not is_user_logged_in():
            return redirect(url_for('auth.login'))
        
        # 2. Rolü 'admin' mi?
        if session.get('role') != 'admin':
            flash("Bu sayfaya erişim yetkiniz yok.")
            return redirect(url_for('main.index'))
            
        return f(*args, **kwargs)
    return decorated_function


def placement_completed_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Giriş yapmış mı?
        if not is_user_logged_in():
            flash("Lütfen önce giriş yapınız.")
            return redirect(url_for('auth.login'))
        
        user_id = session.get('user_id')
        if not has_user_completed_placement(user_id):
            flash("Lütfen önce seviye belirleme testini tamamlayınız.")
            return redirect(url_for('main.placement_page'))
            
        return f(*args, **kwargs)
    return decorated_function


# --- Placement sayfasına zaten tamamlamış kullanıcıların girememesi ---
def placement_not_completed_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Giriş yapmış mı?
        if not is_user_logged_in():
            flash("Lütfen önce giriş yapınız.")
            return redirect(url_for('auth.login'))

        user_id = session.get('user_id')
        # Eğer bitirmişse erişimi engelle
        if has_user_completed_placement(user_id):
            flash("Seviye tespit sınavını zaten tamamladınız. Tekrar giremezsiniz.", "info")
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)
    return decorated_function

# --- Google Translate Fonksiyonu ---
def fetch_google_translation(word, source='en', target='tr'):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        q = urllib.parse.quote_plus(word)
        g_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source}&tl={target}&dt=t&dt=bd&q={q}"
        
        gresp = requests.get(g_url, headers=headers, timeout=5)
        if gresp.status_code != 200:
            return {'error': f'Service status {gresp.status_code}'}

        gjson = gresp.json()
        primary = ''
        if isinstance(gjson, list) and len(gjson) > 0 and isinstance(gjson[0], list):
            primary = ''.join([seg[0] for seg in gjson[0] if isinstance(seg, list) and len(seg) > 0 and isinstance(seg[0], str)])

        word_count = len(word.strip().split())
        is_sentence = word_count > 3 or (word_count > 1 and any(char in word for char in ".?!,;"))

        if is_sentence:
            return {'translatedText': primary, 'alternatives': [], 'pos': [], 'ok': True}

        pos_list = []
        if isinstance(gjson, list) and len(gjson) > 1 and isinstance(gjson[1], list):
            for entry in gjson[1]:
                if isinstance(entry, list) and len(entry) > 1:
                    pos = entry[1]
                    if pos and isinstance(pos, str):
                        pos_list.append(pos)
        pos_list = list(dict.fromkeys([p.strip().lower() for p in pos_list if p]))[:3]

        candidates = []
        def collect(o):
            if isinstance(o, str): candidates.append(o)
            elif isinstance(o, list): 
                for x in o: collect(x)
        collect(gjson)

        alternatives = []
        seen = set()
        loworig = word.lower()
        lowprimary = primary.lower()

        for c in candidates:
            s = c.strip()
            if not s or len(s) <= 1: continue
            sl = s.lower()
            if sl == loworig or sl == lowprimary or sl in ['en', 'tr', 'en-us', 'tr-tr']: continue
            if re.search(r"\b[0-9a-f]{12,}\b", s, re.IGNORECASE): continue
            if '.md' in sl or re.search(r"https?://", s): continue
            
            if s not in seen:
                seen.add(s)
                alternatives.append(s)
                if len(alternatives) >= 4: break

        if not primary and alternatives:
            primary = alternatives[0]

        return {'translatedText': primary, 'alternatives': alternatives, 'pos': pos_list, 'ok': True}
    except Exception as e:
        return {'error': str(e)}