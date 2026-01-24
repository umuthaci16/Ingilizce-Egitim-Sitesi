import logging
from database import get_user_levels, update_user_skill_stats, set_skill_cooldown
from flask import Blueprint
# ==========================================
# KONFİGÜRASYON
# ==========================================

xp_manager_bp = Blueprint("xp_manager", __name__)   

# 1. Kümülatif Seviye Eşikleri (Thresholds)
LEVEL_THRESHOLDS = {
    'A1': (0, 499),
    'A2': (500, 1499),
    'B1': (1500, 3499),
    'B2': (3500, 7499),
    'C1': (7500, 15499),
    'C2': (15500, 999999999) 
}

# Seviye Sırası (Bir sonrakini bulmak için)
LEVEL_ORDER = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']

# 2. Zorluk Katsayıları
XP_MULTIPLIERS = {
    'A1': 0.3, 'A2': 0.4, 'B1': 0.5, 
    'B2': 0.6, 'C1': 0.7, 'C2': 0.8  
}

def process_xp_gain(user_id, skill, score, task_level):
    """
    Normal pratik sonrası XP hesaplar.
    Eğer seviye sınırına ulaşılırsa XP'yi sabitler (Cap) ve 'exam_needed' döner.
    """
    user_stats = get_user_levels(user_id)
    if not user_stats: 
        logging.error(f"XP İşleme Hatası: Kullanıcı {user_id} için seviye verisi bulunamadı.")
        return None

    # Mevcut veriler
    # Yapı: {'reading': {'level': 'A1', 'xp': 450}, ...}
    current_data = user_stats.get(skill, {})
    current_xp = current_data.get('xp', 0)
    current_level = current_data.get('level', 'A1')
    
    # C2 ise zaten son seviye, sınav yok, direkt XP artır (Sonsuz mod)
    if current_level == 'C2':
        multiplier = XP_MULTIPLIERS.get(task_level, 0.8)
        gained = int(score * multiplier)
        new_xp = current_xp + gained
        update_user_skill_stats(user_id, skill, 'C2', new_xp)
        return {"gained_xp": gained, "total_xp": new_xp, "new_level": "C2", "exam_needed": False}

    # Mevcut seviyenin XP sınırını bul (Örn: A1 için 499)
    # LEVEL_THRESHOLDS['A1'] -> (0, 499) -> 499'u alıyoruz
    current_max_xp = LEVEL_THRESHOLDS.get(current_level, (0, 999999))[1]

    # XP Hesapla
    multiplier = XP_MULTIPLIERS.get(task_level, 0.3)
    gained_xp = int(score * multiplier) if score > 0 else 0
    potential_total_xp = current_xp + gained_xp

    # --- KRİTİK KONTROL: SINIR AŞILDI MI? ---
    if potential_total_xp > current_max_xp:
        # Sınırı aşıyor! XP'yi tavana sabitle (Cap)
        final_xp = current_max_xp          
        # Veritabanını güncelle (Sınırda bırak)
        update_user_skill_stats(user_id, skill, current_level, final_xp)
        return gained_xp
    else:
        # Sınır aşılmadı, normal devam et
        update_user_skill_stats(user_id, skill, current_level, potential_total_xp)
        return gained_xp

# ==========================================
# SINAV SONUCU İŞLEMLERİ
# ==========================================

def upgrade_user_level(user_id, skill):
    """
    Sınavı GEÇİNCE çağrılır. 
    Seviyeyi bir üstüne taşır ve XP kilidini açar (+1 XP ekler).
    """
    user_stats = get_user_levels(user_id)
    current_level = user_stats.get(skill, {}).get('level', 'A1')
    current_xp = user_stats.get(skill, {}).get('xp', 0)

    # Bir sonraki seviyeyi bul
    try:
        idx = LEVEL_ORDER.index(current_level)
        if idx < len(LEVEL_ORDER) - 1:
            next_level = LEVEL_ORDER[idx + 1]
            # XP'yi bir tık artır ki bir sonraki seviyenin bandına girsin (Örn: 499 -> 500)
            new_xp = current_xp + 1 
            
            update_user_skill_stats(user_id, skill, next_level, new_xp)
            return {"success": True, "new_level": next_level, "new_xp": new_xp}
    except ValueError:
        pass
    
    return {"success": False}

def apply_exam_failure(user_id, skill):
    """
    Sınavdan KALINCA çağrılır.
    XP'den %15 düşer ve 3 saat ceza (cooldown) verir.
    """
    user_stats = get_user_levels(user_id)
    current_xp = user_stats.get(skill, {}).get('xp', 0)
    current_level = user_stats.get(skill, {}).get('level', 'A1')

    # %15 Ceza Kes
    penalty = int(current_xp * 0.15)
    new_xp = max(0, current_xp - penalty) # 0'ın altına düşmesin

    # 1. XP'yi Düşür
    update_user_skill_stats(user_id, skill, current_level, new_xp)
    
    # 2. Cooldown Bas (Database'deki fonksiyonu kullanıyoruz)
    set_skill_cooldown(user_id, skill, hours=3)

    return {
        "dropped_xp": penalty,
        "current_xp": new_xp,
        "cooldown_hours": 3
    }

# skills/xp_manager.py EN ALTINA:

def check_exam_eligibility(user_id, skill):
    """
    Sayfa yüklenirken çağrılır.
    Kullanıcının XP'si o seviyenin tavanına (Cap) ulaşmış mı kontrol eder.
    
    Returns:
        bool: True (Sınav Gerekli) / False (Gerekli Değil)
    """
    user_stats = get_user_levels(user_id)
    if not user_stats: return False

    current_data = user_stats.get(skill, {})
    current_level = current_data.get('level', 'A1')
    current_xp = current_data.get('xp', 0)

    # C2 ise sınav yok
    if current_level == 'C2':
        return False

    # XP Sınırını bul
    threshold_max = LEVEL_THRESHOLDS.get(current_level, (0, 999999))[1]

    # Eğer XP sınıra eşit veya büyükse sınav gereklidir
    return current_xp >= threshold_max