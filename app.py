import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from database import SessionLocal, engine, Base
from models import User, RelationshipCV, DateProfile, DateAttribute, NovaCoachingLog, RelationshipJournal
import uuid
from datetime import datetime

# Tabloları veritabanına inşa et
Base.metadata.create_all(bind=engine)

app = Flask(__name__)
CORS(app)

# --- JWT (KİMLİK DOĞRULAMA) AYARLARI ---
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "gizli-anahtari-koymayi-unutma")
jwt = JWTManager(app)

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
    
    guvenli_sifre = generate_password_hash(data.get('password'))
    
    new_user = User(
        id=str(uuid.uuid4()),
        email=data.get('email'),
        password_hash=guvenli_sifre,
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
    
    user = db.query(User).filter(User.email == data.get('email')).first()
    db.close()
    
    if user and check_password_hash(user.password_hash, data.get('password')):
        access_token = create_access_token(identity=user.id)
        return jsonify({
            "message": "Giriş başarılı", 
            "user_id": user.id, 
            "token": access_token
        })
        
    return jsonify({"error": "E-posta veya şifre hatalı."}), 401


# --- İLİŞKİ CV API ---
@app.route('/api/cv/<user_id>', methods=['GET', 'POST'])
@jwt_required()
def handle_cv(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    if request.method == 'POST':
        data = request.json.get('cv', {})
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


# --- YENİ EKLENEN: NOVA MATEMATİKSEL PUANLAMA MOTORU ---
def calculate_match_score(user_cv_records, date_attributes):
    if not user_cv_records or not date_attributes: 
        return 50 # Veri yoksa ortalama puan

    total_weight = 0
    earned_score = 0
    red_flag_penalty = False

    cv_dict = {cv.criteria_key: cv for cv in user_cv_records}

    for key, actual_val in date_attributes.items():
        if key in cv_dict:
            cv = cv_dict[key]
            expected_val = cv.expected_value
            weight = cv.importance
            total_weight += weight

            # Uyum Yüzdesini Belirleme
            match_rate = 0.0
            if expected_val == actual_val or expected_val in ["Farketmez", "Önemli Değil", "Sorun Değil"]:
                match_rate = 1.0 # Birebir uyum
            elif actual_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"] or expected_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"]:
                match_rate = 0.5 # Kısmi (orta yollu) uyum
            else:
                match_rate = 0.0 # Tam zıtlık

            earned_score += (weight * match_rate)

            # Kırmızı çizgi kuralı: Kısmi uyum bile yoksa cezayı kes
            if cv.is_red_flag and match_rate == 0.0:
                red_flag_penalty = True

    if total_weight == 0: 
        return 50

    final_score = int((earned_score / total_weight) * 100)

    # Kırmızı çizgi cezası (-25 puan)
    if red_flag_penalty:
        final_score -= 25

    # Puanı 0 ile 100 arasına hapsediyoruz
    return max(0, min(100, final_score))


# --- DATE (ADAY) LİSTESİ API ---
@app.route('/api/dates', methods=['POST'])
@jwt_required()
def add_date():
    data = request.json
    user_id = data.get('user_id')
    
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    
    # 1. Kullanıcının CV'sini veritabanından çekiyoruz
    user_cv = db.query(RelationshipCV).filter_by(user_id=user_id).all()
    
    # 2. Adayın özelliklerini form verisinden alıyoruz
    attrs = data.get('attributes', {})
    
    # 3. KİLİT NOKTA: Algoritmayı çalıştırıp puanı hesaplıyoruz!
    calculated_score = calculate_match_score(user_cv, attrs)
    
    new_profile = DateProfile(
        user_id=user_id,
        name=data.get('name'),
        job_or_education=data.get('job_or_education'),
        notes=data.get('notes'),
        score=calculated_score # ARTIK 0 DEĞİL, GERÇEK PUAN YAZILIYOR
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    
    for key, val in attrs.items():
        new_attr = DateAttribute(
            date_id=new_profile.id,
            criteria_key=key,
            actual_value=val
        )
        db.add(new_attr)
    
    db.commit()
    kaydedilen_id = new_profile.id
    db.close()
    
    return jsonify({"message": "Date başarıyla eklendi", "date_id": kaydedilen_id, "score": calculated_score})

@app.route('/api/dates/list/<user_id>', methods=['GET'])
@jwt_required()
def list_dates(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    profiles = db.query(DateProfile).filter_by(user_id=user_id).order_by(DateProfile.created_at.desc()).all()
    result = [{"id": p.id, "name": p.name, "job_or_education": p.job_or_education, "score": p.score} for p in profiles]
    db.close()
    return jsonify(result)

@app.route('/api/dates/analysis/<user_id>/<date_id>', methods=['GET'])
@jwt_required()
def analyze_date(user_id, date_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    # Adayın genel bilgilerini çek
    profile = db.query(DateProfile).filter_by(id=date_id).first()
    
    if not profile:
        db.close()
        return jsonify({"error": "Kayıt bulunamadı"}), 404
        
    # Senin CV'ni ve adayın özelliklerini çek
    user_cv = db.query(RelationshipCV).filter_by(user_id=user_id).all()
    date_attrs = db.query(DateAttribute).filter_by(date_id=date_id).all()
    
    cv_dict = {cv.criteria_key: cv for cv in user_cv}
    attr_dict = {attr.criteria_key: attr.actual_value for attr in date_attrs}
    
    pros = []
    cons = []
    critical_conflicts = []
    
    # Veritabanındaki İngilizce anahtarları Türkçe okunabilir metinlere çeviriyoruz
    key_names = {
        'humor': 'Mizah Anlayışı',
        'finance': 'Finansal Tutum',
        'child': 'Çocuk İsteği',
        'communication': 'İletişim Sıklığı',
        'habit': 'Zararlı Alışkanlıklar'
    }

    # Satır satır CV ve Aday karşılaştırması
    for key, actual_val in attr_dict.items():
        if key in cv_dict:
            cv = cv_dict[key]
            expected_val = cv.expected_value
            readable_key = key_names.get(key, key)
            
            # Tam uyum veya senin için fark etmeyen durumlar (Green Flags)
            if expected_val == actual_val or expected_val in ["Farketmez", "Önemli Değil", "Sorun Değil"]:
                pros.append(f"{readable_key} tam istediğin gibi ({actual_val})")
            
            # Kısmi uyum / Orta yol gereken durumlar (Eksiler/Riskler)
            elif actual_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"] or expected_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"]:
                cons.append(f"{readable_key} konusunda orta yolu bulmanız gerekebilir (Sen: {expected_val} / O: {actual_val})")
            
            # Tam zıtlık durumları
            else:
                msg = f"{readable_key} dinamikleri tamamen zıt (Sen: {expected_val} / O: {actual_val})"
                
                # Eğer bu zıtlık senin kırmızı çizginse, acil durum listesine at!
                if cv.is_red_flag:
                    critical_conflicts.append(msg)
                else:
                    cons.append(msg)
    
    db.close()
    
    # Nova'nın puana göre değişen dinamik teşhis mesajı
    nova_msg = f"Nova: {profile.name} için mantıksal analiz tamamlandı. "
    if profile.score >= 80:
        nova_msg += "Kağıt üzerinde harika bir uyum! Bu potansiyeli mutlaka değerlendirmelisin."
    elif profile.score >= 50:
        nova_msg += "Ortalama bir eşleşme. Kırmızı çizgilere ve aranızdaki farklılıklara dikkat ederek ilerleyebilirsin."
    else:
        nova_msg += "Uyum seviyesi tehlikeli derecede düşük. Beklentilerinle ciddi oranda çelişiyor, çok dikkatli ol."

    return jsonify({
        "final_score": profile.score,
        "nova_message": nova_msg,
        "pros": pros if pros else ["Belirgin bir güçlü yön saptanamadı."],
        "cons": cons if cons else ["Her şey yolunda görünüyor, belirgin bir pürüz yok."],
        "critical_conflicts": critical_conflicts
    })

# --- GÜNLÜK, KOÇLUK VE TRENDLER API ---
@app.route('/api/journal/<user_id>', methods=['GET', 'POST'])
@jwt_required()
def handle_journal(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

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
@jwt_required()
def handle_coaching(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

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
@jwt_required()
def get_trends(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    total = db.query(DateProfile).filter_by(user_id=user_id).count()
    db.close()
    return jsonify({
        "total": total,
        "macro_insight": "Veri havuzun öğrenme aşamasında. 5 adaydan sonra anlamlı örüntüler sunabileceğim."
    })


# --- ÇİFT (COUPLE) ANALİZ API ---
@app.route('/api/couple_match/<user_id>', methods=['POST'])
@jwt_required()
def couple_match(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    data = request.json
    partner_cv = data.get('partner_cv')
    
    db = SessionLocal()
    user_cv_records = db.query(RelationshipCV).filter(RelationshipCV.user_id == user_id).all()
    db.close()
    
    user_cv_dict = {
        record.criteria_key: {
            "expected": record.expected_value,
            "importance": record.importance,
            "is_red_flag": record.is_red_flag
        } for record in user_cv_records
    }
    
    try:
        from ai_service import generate_couple_report
        report = generate_couple_report(str(user_cv_dict), str(partner_cv))
    except ImportError:
        report = "Yapay zeka servisi şu an kullanılamıyor. Lütfen daha sonra tekrar deneyin."
    
    return jsonify({"nova_report": report})


if __name__ == '__main__':
    is_dev = os.getenv("FLASK_ENV") == "development"
    app.run(debug=is_dev, use_reloader=False)