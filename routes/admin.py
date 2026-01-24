from flask import Blueprint, render_template, jsonify, request
# DÜZELTME: Gerekli fonksiyonları direkt import ediyoruz
from database import (
    get_all_vocabs, 
    get_all_vocabs_with_details,
    add_vocab_with_details, 
    get_vocab_details, 
    update_vocab_with_details
)
from utils import is_user_logged_in, admin_required 

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/vocab')
@admin_required
def vocab_admin_page():
    return render_template('vocab_admin.html', is_logged_in=is_user_logged_in())

@admin_bp.route('/admin/api/vocabs', methods=['GET'])
@admin_required
def admin_list_vocabs():
    # word_types ve levels ile birlikte tüm kelimeleri alıp sol tarafta gösteriyoruz
    try:
        vocabs = get_all_vocabs_with_details()
    except Exception:
        vocabs = get_all_vocabs()
    return jsonify({'vocabs': vocabs})

@admin_bp.route('/admin/api/vocab', methods=['POST'])
@admin_required
def admin_create_vocab():
    data = request.json or {}
    word = data.get('word', '').strip()
    if not word: return jsonify({'error': 'Kelime giriniz'}), 400
    
    
    vid = add_vocab_with_details(
        word,
        data.get('meanings', []),
        data.get('examples', []),
        data.get('levels', []),
        data.get('word_types', [])
    )
    if vid: return jsonify({'success': True, 'id': vid})
    return jsonify({'error': 'Hata'}), 500

@admin_bp.route('/admin/api/vocab/<int:vocab_id>', methods=['GET', 'PUT'])
@admin_required
def admin_vocab_detail(vocab_id):
    if request.method == 'GET':
        # bir kelimeye tıkladığında detayları getir
        details = get_vocab_details(vocab_id)
        if not details: return jsonify({'error': 'Bulunamadı'}), 404
        return jsonify({
            'id': details[0],
            'word': details[1],
            'meanings': details[2],
            'examples': details[3],
            'levels': details[4] if len(details) > 4 else [],
            'word_types': details[5] if len(details) > 5 else []
        })
    
    data = request.json or {}
    word = data.get('word', '').strip()
    if not word: return jsonify({'error': 'Kelime giriniz'}), 400
    
    # PUT isteği ise güncelleme yap
    if update_vocab_with_details(
        vocab_id,
        word,
        data.get('meanings', []),
        data.get('examples', []),
        data.get('levels', []),
        data.get('word_types', [])
    ):
        return jsonify({'success': True})
    return jsonify({'error': 'Güncelleme hatası'}), 500