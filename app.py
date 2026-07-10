from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from database import SessionLocal, engine, Base
from models import User, RelationshipCV, DateProfile, DateAttribute, NovaCoachingLog, RelationshipJournal
import uuid
from datetime import datetime

# Tabloları veritabanına inşa et (SQLite dosyası boşsa otomatik kurar)
Base.metadata.create_all(bind=engine)

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

# --- KULLANICI (AUTH) API ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    db = SessionLocal()
    
    existing_user = db.query(User).filter(User.email == data.get('email')).first()
    if existing_user:
        db.close()
        return jsonify({"error": "Bu e-posta zaten kayıtlı."}), 400
    
    new_user = User(
        id=str(uuid.uuid4()), # Karmaşık UUID formatında ID üretir
        email=data.get('email'),
        password_hash=data.get('password'),
        display_name=data.get('display_name')
    )
    db.add(new_user)
    db.commit()
    user_id = new_user.id
    db.close()
    return jsonify({"message": "Kayıt başarılı", "user_id": user_id})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    db = SessionLocal()
    user = db.query(User).filter(User.email == data.get('email'), User.password_hash == data.get('password')).first()
    db.close()
    if user:
        return jsonify({"message": "Giriş başarılı", "user_id": user.id})
    return jsonify({"error": "E-posta veya şifre hatalı."}), 401


# --- İLİŞKİ CV API ---
@app.route('/api/cv/<user_id>', methods=['GET', 'POST'])
def handle_cv(user_id):
    db = SessionLocal()
    if request.method == 'POST':
        data = request.json.get('cv', {})
        # Eski CV verilerini temizle ve yenilerini yaz
        db.query(RelationshipCV).filter_by(user_id=user_id).delete()
        for key, vals in data.items():
            new_cv = RelationshipCV(
                user_id=user_id,
                criteria_key=key,
                expected_value=vals.get('expected'),
                importance=int(vals.get('importance', 50)),
                is_red_flag=vals.get('is_red_flag', False)
            )
            db.add(new_cv)
        db.commit()
        db.close()
        return jsonify({"message": "CV kaydedildi"})
    else:
        records = db.query(RelationshipCV).filter_by(user_id=user_id).all()
        db.close()
        result = {r.criteria_key: {"expected": r.expected_value, "importance": r.importance, "is_red_flag": r.is_red_flag} for r in records}
        return jsonify(result)

# --- DATE (ADAY) LİSTESİ API ---
@app.route('/api/dates', methods=['POST'])
def add_date():
    data = request.json
    db = SessionLocal()
    
    new_profile = DateProfile(
        user_id=data.get('user_id'),
        name=data.get('name'),
        job_or_education=data.get('job_or_education'),
        notes=data.get('notes'),
        score=0 
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    
    attrs = data.get('attributes', {})
    for key, val in attrs.items():
        new_attr = DateAttribute(
            date_id=new_profile.id,
            criteria_key=key,
            actual_value=val
        )
        db.add(new_attr)
    db.commit()
    db.close()
    return jsonify({"message": "Date başarıyla eklendi", "date_id": new_profile.id})

@app.route('/api/dates/list/<user_id>', methods=['GET'])
def list_dates(user_id):
    db = SessionLocal()
    # "created_at" tarihine göre azalan şekilde (en yeniler üstte) sıralar
    profiles = db.query(DateProfile).filter_by(user_id=user_id).order_by(DateProfile.created_at.desc()).all()
    result = [{"id": p.id, "name": p.name, "job_or_education": p.job_or_education, "score": p.score} for p in profiles]
    db.close()
    return jsonify(result)

@app.route('/api/dates/analysis/<user_id>/<date_id>', methods=['GET'])
def analyze_date(user_id, date_id):
    return jsonify({
        "final_score": 85,
        "nova_message": "Nova: Veritabanı profili alındı ve analiz geçici olarak başarılı raporlandı.",
        "pros": ["Finansal beklentiler dengeli"],
        "cons": ["İletişim alışkanlıkları izlenmeli"],
        "critical_conflicts": []
    })


# --- GÜNLÜK, KOÇLUK VE TRENDLER API ---
@app.route('/api/journal/<user_id>', methods=['GET', 'POST'])
def handle_journal(user_id):
    db = SessionLocal()
    if request.method == 'POST':
        text = request.json.get('entry_text')
        new_entry = RelationshipJournal(user_id=user_id, entry_text=text)
        db.add(new_entry)
        db.commit()
        db.close()
        return jsonify({"message": "Günlük kaydedildi"})
    else:
        entries = db.query(RelationshipJournal).filter_by(user_id=user_id).order_by(RelationshipJournal.timestamp.desc()).all()
        result = [{"timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"), "entry_text": e.entry_text} for e in entries]
        db.close()
        return jsonify(result)

@app.route('/api/coaching/<user_id>', methods=['GET', 'POST'])
def handle_coaching(user_id):
    db = SessionLocal()
    if request.method == 'POST':
        msg = request.json.get('message')
        user_msg = NovaCoachingLog(user_id=user_id, message=msg, sender='user')
        db.add(user_msg)
        db.commit()
        
        nova_msg = NovaCoachingLog(user_id=user_id, message="Nova: Senaryonu kaydettim. Karşılaştığın bu duruma klinik bir zihinle yaklaş.", sender='nova')
        db.add(nova_msg)
        db.commit()
        db.close()
        return jsonify({"message": "Mesaj gönderildi"})
    else:
        logs = db.query(NovaCoachingLog).filter_by(user_id=user_id).order_by(NovaCoachingLog.timestamp.asc()).all()
        result = [{"sender": l.sender, "content": l.message} for l in logs]
        db.close()
        return jsonify(result)

@app.route('/api/trends/<user_id>', methods=['GET'])
def get_trends(user_id):
    db = SessionLocal()
    total = db.query(DateProfile).filter_by(user_id=user_id).count()
    db.close()
    return jsonify({
        "total": total,
        "macro_insight": "Veri havuzun öğrenme aşamasında. 5 adaydan sonra anlamlı örüntüler sunabileceğim."
    })


# --- ÇİFT (COUPLE) ANALİZ API (YENİ EKLENEN YAPAY ZEKA BAĞLANTISI) ---
@app.route('/api/couple_match/<user_id>', methods=['POST'])
def couple_match(user_id):
    data = request.json
    partner_cv = data.get('partner_cv')
    
    # Kullanıcının kendi CV'sini veritabanından çekiyoruz
    db = SessionLocal()
    user_cv_records = db.query(RelationshipCV).filter(RelationshipCV.user_id == user_id).all()
    db.close()
    
    # Veriyi yapay zekanın anlayacağı sözlük formatına çevir
    user_cv_dict = {
        record.criteria_key: {
            "expected": record.expected_value,
            "importance": record.importance,
            "is_red_flag": record.is_red_flag
        } for record in user_cv_records
    }
    
    # İki veriyi Groq Llama AI'ye (Nova) gönder
    from ai_service import generate_couple_report
    report = generate_couple_report(str(user_cv_dict), str(partner_cv))
    
    return jsonify({"nova_report": report})


if __name__ == '__main__':
    # use_reloader=False ayarı, OneDrive'ın Flask'ı sonsuz döngüye sokup çökertmesini önler!
    app.run(debug=True, use_reloader=False)