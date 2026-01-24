from flask import Flask, send_from_directory
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import os
from database import init_app
# 1. Ortam Değişkenlerini Yükle
load_dotenv(override=True)

# Yeni Blueprint'leri dahil et
from routes.main import main_bp
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.exam import exam_bp
from routes.placement import placement_bp
from routes.dashboard import dashboard_bp
from skills.speaking import speaking_bp
from skills.listening import listening_bp
from skills.reading import reading_bp
from skills.writing import writing_bp
from skills.xp_manager import xp_manager_bp




app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_default_secret_key')
init_app(app)
# CSRF Korumasını Başlat
csrf = CSRFProtect(app)

# Klasör Kontrolü
os.makedirs("uploads", exist_ok=True)

# 2. Blueprint'leri Kaydet (Register)
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(placement_bp)
app.register_blueprint(exam_bp)
app.register_blueprint(speaking_bp)
app.register_blueprint(listening_bp)    
app.register_blueprint(reading_bp)
app.register_blueprint(writing_bp)
app.register_blueprint(xp_manager_bp)
app.register_blueprint(dashboard_bp)





@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'favicon'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')
if __name__ == '__main__':
    app.run(debug=True, port=5000)