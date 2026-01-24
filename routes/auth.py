from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils import login_required
from werkzeug.security import generate_password_hash, check_password_hash
from database import register_user, get_user_by_username,get_user_levels

# Blueprint Tanımlama
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # DÜZELTME: db.get_user... yerine direkt fonksiyon ismi
        user = get_user_by_username(username)
        
        if user:
            # user verisi şöyledir: (id, username, password, email, role, created_at)
            # role 4. indekste (0'dan başlarsak)
            # password 2. indekste
            
            db_password_hash = user[2]
            
            if check_password_hash(db_password_hash, password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                # Kullanıcı rolünü session'a ekleme
                try:
                    session['role'] = user[4] 
                except IndexError:
                    session['role'] = 'student'
                
                user_lvl = get_user_levels(user[0])

                if user_lvl and user_lvl.get('is_completed'):
                    flash('Başarıyla giriş yaptınız!')
                    return redirect(url_for('dashboard.dashboard_page'))
                else:
                    return redirect(url_for('main.placement_page')) 
                
                
                
            else:
                flash('Şifre hatalı!')
        else:
            flash('Kullanıcı bulunamadı!')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']
        email = request.form['email']
        
        if password != confirm:
            flash('Şifreler eşleşmiyor!')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        
        # DÜZELTME: db.register_user yerine direkt fonksiyon ismi
        if register_user(username, hashed_password, email):
            flash('Kayıt başarılı! Şimdi giriş yapabilirsiniz.')
            return redirect(url_for('auth.login'))
        else:
            flash('Kayıt hatası: Kullanıcı adı veya email kullanımda olabilir.')
    return render_template('register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Başarıyla çıkış yaptınız.')
    return redirect(url_for('auth.login'))