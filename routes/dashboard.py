from flask import Blueprint, render_template
from utils import current_user,current_user_name,placement_completed_required
from database import get_user_levels
from skills.xp_manager import LEVEL_THRESHOLDS

dashboard_bp = Blueprint("dashboard", __name__)

# C2 ÇIKARILDI: A1'den C1'e kadar 5 seviye
ALL_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1']
LEVEL_MAP = {lvl: i + 1 for i, lvl in enumerate(ALL_LEVELS)} # {'A1': 1 ... 'C1': 5}

# Rozet Ayarları (C2 Kaldırıldı)
BADGES_CONFIG = {
    'reading': {
        'A1': {'name': 'Kelime Avcısı', 'icon': 'search', 'color': 'text-blue-500', 'bg': 'bg-blue-100 dark:bg-blue-900/30'},
        'A2': {'name': 'Cümle Kurdu', 'icon': 'book-open', 'color': 'text-blue-600', 'bg': 'bg-blue-100 dark:bg-blue-900/30'},
        'B1': {'name': 'Metin Gezgini', 'icon': 'map', 'color': 'text-blue-700', 'bg': 'bg-blue-100 dark:bg-blue-900/30'},
        'B2': {'name': 'Kitap Kurdu', 'icon': 'library', 'color': 'text-indigo-500', 'bg': 'bg-indigo-100 dark:bg-indigo-900/30'},
        'C1': {'name': 'Analiz Uzmanı', 'icon': 'glasses', 'color': 'text-indigo-600', 'bg': 'bg-indigo-100 dark:bg-indigo-900/30'},
    },
    'listening': {
        'A1': {'name': 'Ses Tanıdığı', 'icon': 'ear', 'color': 'text-yellow-600', 'bg': 'bg-yellow-100 dark:bg-yellow-900/30'},
        'A2': {'name': 'Kulak Misafiri', 'icon': 'radio', 'color': 'text-yellow-700', 'bg': 'bg-yellow-100 dark:bg-yellow-900/30'},
        'B1': {'name': 'Dikkatli Dinleyici', 'icon': 'headphones', 'color': 'text-orange-500', 'bg': 'bg-orange-100 dark:bg-orange-900/30'},
        'B2': {'name': 'Podcast Fanı', 'icon': 'music', 'color': 'text-orange-600', 'bg': 'bg-orange-100 dark:bg-orange-900/30'},
        'C1': {'name': 'Usta Dinleyici', 'icon': 'volume-2', 'color': 'text-red-500', 'bg': 'bg-red-100 dark:bg-red-900/30'},
    },
    'writing': {
        'A1': {'name': 'Not Tutucu', 'icon': 'pen-tool', 'color': 'text-green-500', 'bg': 'bg-green-100 dark:bg-green-900/30'},
        'A2': {'name': 'Mektup Arkadaşı', 'icon': 'send', 'color': 'text-green-600', 'bg': 'bg-green-100 dark:bg-green-900/30'},
        'B1': {'name': 'Hikaye Anlatıcısı', 'icon': 'feather', 'color': 'text-emerald-500', 'bg': 'bg-emerald-100 dark:bg-emerald-900/30'},
        'B2': {'name': 'Yazıcı', 'icon': 'edit-3', 'color': 'text-emerald-600', 'bg': 'bg-emerald-100 dark:bg-emerald-900/30'},
        'C1': {'name': 'Yazma Ustası', 'icon': 'file-text', 'color': 'text-teal-500', 'bg': 'bg-teal-100 dark:bg-teal-900/30'},
    },
    'speaking': {
        'A1': {'name': 'Merhaba Diyen', 'icon': 'smile', 'color': 'text-pink-500', 'bg': 'bg-pink-100 dark:bg-pink-900/30'},
        'A2': {'name': 'Sohbet Sever', 'icon': 'message-circle', 'color': 'text-pink-600', 'bg': 'bg-pink-100 dark:bg-pink-900/30'},
        'B1': {'name': 'Konuşkan', 'icon': 'mic', 'color': 'text-rose-500', 'bg': 'bg-rose-100 dark:bg-rose-900/30'},
        'B2': {'name': 'Hatip Adayı', 'icon': 'users', 'color': 'text-rose-600', 'bg': 'bg-rose-100 dark:bg-rose-900/30'},
        'C1': {'name': 'Söz Üstadı', 'icon': 'award', 'color': 'text-fuchsia-500', 'bg': 'bg-fuchsia-100 dark:bg-fuchsia-900/30'},
    }
}

@dashboard_bp.route('/dashboard')
@placement_completed_required
def dashboard_page():
    user_id = current_user()
    username=current_user_name() 
    stats = get_user_levels(user_id) or {}
    
    dashboard_data = {
        'skills': [],
        'badge_groups': [], 
        'chart_data': []
    }
    
    for skill in ['reading', 'listening', 'writing', 'speaking']:
        s_data = stats.get(skill, {'level': 'A1', 'xp': 0})
        user_lvl = s_data.get('level', 'A1')
        xp = s_data.get('xp', 0)
        
        # XP İlerleme
        min_xp, max_xp = LEVEL_THRESHOLDS.get(user_lvl, (0, 100))
        range_span = max_xp - min_xp + 1
        progress = int(((xp - min_xp) / range_span) * 100) if range_span > 0 else 100
        progress = max(0, min(100, progress))
        
        # Eğer kullanıcı yanlışlıkla C2 görünüyorsa C1'e fixle (Fallback)
        display_lvl = user_lvl if user_lvl in BADGES_CONFIG[skill] else 'C1'
        current_badge = BADGES_CONFIG[skill].get(display_lvl, BADGES_CONFIG[skill]['A1'])
        
        dashboard_data['skills'].append({
            'name': skill.capitalize(),
            'level': display_lvl,
            'xp': xp,
            'next_xp': max_xp,
            'progress': progress,
            'icon': current_badge['icon'],
            'bg_color': current_badge['bg'],
            'text_color': current_badge['color']
        })
        
        # Grafik Verisi
        dashboard_data['chart_data'].append(LEVEL_MAP.get(display_lvl, 1))

        # Rozet Grubu
        group_badges = []
        # Eğer level listede yoksa (örn C2 ise) en son indexi al (C1)
        try:
            user_lvl_idx = ALL_LEVELS.index(user_lvl)
        except ValueError:
            user_lvl_idx = len(ALL_LEVELS) - 1 # Max level kabul et

        for lvl in ALL_LEVELS:
            b_def = BADGES_CONFIG[skill].get(lvl)
            is_unlocked = (ALL_LEVELS.index(lvl) <= user_lvl_idx)
            
            group_badges.append({
                'level': lvl,
                'name': b_def['name'],
                'icon': b_def['icon'],
                'bg_color': b_def['bg'],
                'text_color': b_def['color'],
                'is_unlocked': is_unlocked
            })
            
        dashboard_data['badge_groups'].append({
            'skill_name': skill.capitalize(),
            'badges': group_badges
        })

    return render_template('dashboard.html', data=dashboard_data, username=username)