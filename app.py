import os
import time
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from database import SessionLocal, engine, Base
from models import User, RelationshipCV, DateProfile, DateAttribute, NovaCoachingLog, RelationshipJournal
import uuid
from datetime import datetime
from groq import Groq
from sqlalchemy import text

# --- VERİTABANI İNŞASI VE OTOMATİK YAMA ---
# Tabloları veritabanına inşa et
Base.metadata.create_all(bind=engine)

# Eksik paywall ve gamification sütunlarını zorla ekle
try:
    with engine.connect() as conn:
        # Paywall Sütunları
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMP;"))
        
        # 🚨 YENİ: Gamification (Rozet) Sütunları 🚨
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS xp_points INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_dates_count INTEGER DEFAULT 0;"))
        
        conn.commit()
        print("💎 Veritabanı sütunları (Paywall & Gamification) başarıyla senkronize edildi!")
except Exception as e:
    # Sütunlar zaten varsa sessizce yola devam et
    pass

app = Flask(__name__)
CORS(app)

# --- JWT (KİMLİK DOĞRULAMA) AYARLARI ---
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "gizli-anahtari-koymayi-unutma")
jwt = JWTManager(app)

# Groq İstemcisini Başlat
try:
    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
except:
    groq_client = None

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
        display_name=data.get('display_name'),
        is_premium=False # Varsayılan olarak herkes fakir başlar
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
            "token": access_token,
            "is_premium": user.is_premium # Arayüze Premium bilgisini de yolluyoruz
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


# --- NOVA MATEMATİKSEL PUANLAMA MOTORU ---
def calculate_match_score(user_cv_records, date_attributes):
    if not user_cv_records or not date_attributes: 
        return 50

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

            match_rate = 0.0
            if expected_val == actual_val or expected_val in ["Farketmez", "Önemli Değil", "Sorun Değil"]:
                match_rate = 1.0 
            elif actual_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"] or expected_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"]:
                match_rate = 0.5 
            else:
                match_rate = 0.0 

            earned_score += (weight * match_rate)

            if cv.is_red_flag and match_rate == 0.0:
                red_flag_penalty = True

    if total_weight == 0: 
        return 50

    final_score = int((earned_score / total_weight) * 100)

    if red_flag_penalty:
        final_score -= 25

    return max(0, min(100, final_score))


# --- DATE (ADAY) YÖNETİMİ VE PAYWALL API ---
@app.route('/api/dates', methods=['POST'])
@jwt_required()
def add_date():
    data = request.json
    user_id = data.get('user_id')
    
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    
    # 🚨 ÖDEME DUVARI (PAYWALL) KONTROLÜ 🚨
    user = db.query(User).filter_by(id=user_id).first()
    if not user.is_premium:
        current_date_count = db.query(DateProfile).filter_by(user_id=user_id).count()
        if current_date_count >= 3:
            db.close()
            # Kullanıcı 3 sınırını aştıysa hata kodu fırlatıyoruz (Frontend bunu yakalayıp modal açacak)
            return jsonify({"error": "PREMIUM_REQUIRED", "message": "Ücretsiz sürüm sınırına ulaştın. Daha fazla toksik insan eklemek için Premium'a geç!"}), 403
    
    user_cv = db.query(RelationshipCV).filter_by(user_id=user_id).all()
    attrs = data.get('attributes', {})
    
    calculated_score = calculate_match_score(user_cv, attrs)
    
    new_profile = DateProfile(
        user_id=user_id,
        name=data.get('name'),
        job_or_education=data.get('job_or_education'),
        notes=data.get('notes'),
        score=calculated_score 
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

@app.route('/api/dates/<date_id>', methods=['DELETE'])
@jwt_required()
def delete_date(date_id):
    user_id = get_jwt_identity()
    db = SessionLocal()
    
    profile = db.query(DateProfile).filter_by(id=date_id, user_id=user_id).first()
    if not profile:
        db.close()
        return jsonify({"error": "Profil bulunamadı veya yetkiniz yok."}), 404
        
    db.query(DateAttribute).filter_by(date_id=date_id).delete()
    db.delete(profile)
    db.commit()
    db.close()
    
    return jsonify({"message": "Aday laboratuvardan silindi."})

@app.route('/api/dates/analysis/<user_id>/<date_id>', methods=['GET'])
@jwt_required()
def analyze_date(user_id, date_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    profile = db.query(DateProfile).filter_by(id=date_id).first()
    
    if not profile:
        db.close()
        return jsonify({"error": "Kayıt bulunamadı"}), 404
        
    user_cv = db.query(RelationshipCV).filter_by(user_id=user_id).all()
    date_attrs = db.query(DateAttribute).filter_by(date_id=date_id).all()
    
    cv_dict = {cv.criteria_key: cv for cv in user_cv}
    attr_dict = {attr.criteria_key: attr.actual_value for attr in date_attrs}
    
    pros = []
    cons = []
    critical_conflicts = []
    
    chart_labels = ["Mizah", "Finans", "Çocuk", "İletişim", "Alışkanlık"]
    user_chart_data = [50, 50, 50, 50, 50]
    date_chart_data = [50, 50, 50, 50, 50]
    
    key_names = {
        'humor': 'Mizah Anlayışı',
        'finance': 'Finansal Tutum',
        'child': 'Çocuk İsteği',
        'communication': 'İletişim Sıklığı',
        'habit': 'Zararlı Alışkanlıklar'
    }
    
    key_indices = {
        'humor': 0,
        'finance': 1,
        'child': 2,
        'communication': 3,
        'habit': 4
    }

    for key, actual_val in attr_dict.items():
        if key in cv_dict:
            cv = cv_dict[key]
            expected_val = cv.expected_value
            readable_key = key_names.get(key, key)
            idx = key_indices.get(key)
            
            user_chart_data[idx] = cv.importance
            
            match_rate = 0.0
            if expected_val == actual_val or expected_val in ["Farketmez", "Önemli Değil", "Sorun Değil"]:
                match_rate = 1.0
                pros.append(f"{readable_key} tam istediğin gibi ({actual_val})")
            elif actual_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"] or expected_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"]:
                match_rate = 0.5
                cons.append(f"{readable_key} konusunda orta yolu bulmanız gerekebilir (Sen: {expected_val} / O: {actual_val})")
            else:
                match_rate = 0.0
                msg = f"{readable_key} dinamikleri tamamen zıt (Sen: {expected_val} / O: {actual_val})"
                if cv.is_red_flag:
                    critical_conflicts.append(msg)
                else:
                    cons.append(msg)
            
            if cv.is_red_flag and match_rate == 0.0:
                date_chart_data[idx] = 0
            else:
                date_chart_data[idx] = int(cv.importance * match_rate)
    
    db.close()
    
    nova_msg = f"Nova: {profile.name} için mantıksal analiz tamamlandı. "
    if profile.score >= 80:
        nova_msg += "Kağıt üzerinde harika bir uyum! Bu potansiyeli mutlaka değerlendirmelisin."
    elif profile.score >= 50:
        nova_msg += "Ortalama bir eşleşme. Kırmızı çizgilere ve aranızdaki farklılıklara dikkat ederek ilerleyebilirsin."
    else:
        nova_msg += "Uyum seviyesi tehlikeli derecede düşük. Beklentilerinle ciddi oranda çelişiyor, çok dikkatli ol."

    out_of_bounds_count = sum(1 for i in range(5) if date_chart_data[i] < (user_chart_data[i] * 0.3))
    if out_of_bounds_count >= 2:
        nova_msg += " Ayrıca grafikteki uyumsuzluklara dikkat ettin mi? Beklentilerin ve gerçekler biraz fazla zıt kutuplarda kalmış, belki de standartlarından taviz vermemelisin! 📉🤔"

    return jsonify({
        "final_score": profile.score,
        "nova_message": nova_msg,
        "pros": pros if pros else ["Belirgin bir güçlü yön saptanamadı."],
        "cons": cons if cons else ["Her şey yolunda görünüyor, belirgin bir pürüz yok."],
        "critical_conflicts": critical_conflicts,
        "chart_labels": chart_labels,
        "user_chart_data": user_chart_data,
        "date_chart_data": date_chart_data
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
        
        bot_text = "Nova: Gözlem yeteneklerimi (API) kaybettim, şu an o zekice analizlerimi yapamıyorum. Lütfen sistem yöneticisine API Key'ini kontrol etmesini söyle. 😅"
        
        if groq_client:
            try:
                completion = groq_client.chat.completions.create(
                    model="openai/gpt-oss-120b", 
                    messages=[
                        {
                            "role": "system", 
                            "content": "Senin adın Nova. Sen zeki, eğlenceli, analitik düşünen ve verilerle konuşmayı seven modern bir ilişki koçusun. İnsanlara pembe yalanlar söylemezsin; dürüst, mantıklı ama aynı zamanda tatlı-sert ve esprili bir dille tavsiyeler verirsin. Amacın insanları toksik döngülerden kurtarıp, kendi değerlerini fark etmelerini sağlamak. Mizahın zekice, ölçülü ve herkesin yüzünde tebessüm bırakacak kalitede olsun. Asla aşağılayıcı veya kaba olma. Cevapların çok uzun olmasın (maksimum 2-3 kısa paragraf). 💅, 🧠, 🎯, ✨, ☕ gibi emojileri stratejik kullan."
                        },
                        {
                            "role": "user", 
                            "content": msg
                        }
                    ],
                    temperature=0.8,
                    max_tokens=500,
                )
                bot_text = "Nova: " + completion.choices[0].message.content
            except Exception as e:
                bot_text = f"Nova: Beyin devrelerimde ufak bir karışıklık oldu, şu an analiz yapamıyorum. Hata Kodu: {str(e)} 🛠️"
        
        nova_msg = NovaCoachingLog(user_id=user_id, message=bot_text, sender='nova')
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
    profiles = db.query(DateProfile).filter_by(user_id=user_id).all()
    total = len(profiles)
    
    if total == 0:
        insight = "Laboratuvarda henüz in cin top oynuyor... Hiçbir denek verisi bulamadığım için o muhteşem istatistiksel analizlerimi yapamıyorum! Hemen sağ üstten birilerini ekle de yeteneklerimi sergileyeyim! 🕸️🧐"
    else:
        avg_score = sum(p.score for p in profiles) / total
        
        if avg_score >= 75:
            insight = f"İnanılmaz bir istatistik! Havuzundaki toplam {total} adayın genel not ortalaması tam olarak %{int(avg_score)}. Algoritmalarım bile bu muazzam sonuca şaşırdı. Standartlarının net olması ve hayatına sadece sana uyan insanları alman gerçekten takdire şayan. Kırmızı çizgilerini harika koruyorsun. Böyle devam et, laboratuvar seninle gurur duyuyor! 🥂😎✨"
        elif avg_score >= 50:
            insight = f"Sistemdeki verileri taradığımda havuzundaki {total} adayın ortalamasının %{int(avg_score)} olduğunu görüyorum. Tamamen güvenli ama biraz sıradan sularda yüzüyoruz. Ne büyük bir kriz var, ne de 'İşte bu!' dedirten mükemmel bir uyum. Biraz daha seçici olmaya ne dersin? Standartlarını daha da netleştirip sadece senin enerjine uyan kişilere odaklanma vakti gelmiş olabilir! 🤷‍♂️📊"
        else:
            insight = f"Sistem alarm veriyor! Havuzundaki {total} adayın ortalaması maalesef düşük bir seviyede: %{int(avg_score)}. Sanırım içindeki 'belki onu düzeltirim' kahramanına biraz fazla güveniyorsun! Uyumsuzluklar ortadayken şans vermek yerine, kendi değerinin farkına varmalısın. Çöp sepeti butonunu kullanmaktan çekinme, daha iyisini hak ettiğini unutma! 🚩😅📉"

    db.close()
    
    return jsonify({
        "total": total,
        "macro_insight": insight
    })


# --- ÇİFT (COUPLE) ANALİZ API (PREMIUM KİLİTLİ) ---
@app.route('/api/couple_match/<user_id>', methods=['POST'])
@jwt_required()
def couple_match(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403
        
    db = SessionLocal()
    
    # 🚨 ÖDEME DUVARI (PAYWALL) KONTROLÜ 🚨
    user = db.query(User).filter_by(id=user_id).first()
    if not user.is_premium:
        db.close()
        return jsonify({"error": "PREMIUM_REQUIRED", "nova_report": "Çift Çarpıştırma özelliği sadece Premium üyelere özeldir. Cüzdanını açmadan hayatının aşkını test edemezsin tatlım! 💎💅"}), 403

    data = request.json
    partner_cv = data.get('partner_cv')
    
    report = "Yapay zeka servisi şu an kullanılamıyor veya dosya bulunamadı. Lütfen daha sonra tekrar deneyin. 🙄"
    try:
        from ai_service import generate_couple_report
        user_cv_records = db.query(RelationshipCV).filter(RelationshipCV.user_id == user_id).all()
        db.close()
        
        user_cv_dict = {
            record.criteria_key: {
                "expected": record.expected_value,
                "importance": record.importance,
                "is_red_flag": record.is_red_flag
            } for record in user_cv_records
        }
        report = generate_couple_report(str(user_cv_dict), str(partner_cv))
    except Exception as e:
        db.close()
        pass
    
    return jsonify({"nova_report": report})

# --- REVENUECAT WEBHOOK TASLAĞI ---
@app.route('/api/webhook/revenuecat', methods=['POST'])
def revenuecat_webhook():
    # RevenueCat'ten gelen ödeme başarılı sinyallerini burada yakalayacağız.
    data = request.json
    
    # Örnek mantık: (Daha sonra gerçek RevenueCat event'leriyle doldurulacak)
    # event_type = data.get('event', {}).get('type')
    # if event_type == 'INITIAL_PURCHASE' or event_type == 'RENEWAL':
    #     user_id = data.get('event', {}).get('app_user_id')
    #     db = SessionLocal()
    #     user = db.query(User).filter_by(id=user_id).first()
    #     if user:
    #         user.is_premium = True
    #         db.commit()
    #     db.close()
        
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    is_dev = os.getenv("FLASK_ENV") == "development"
    app.run(debug=is_dev, use_reloader=False)