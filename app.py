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


# --- DATE (ADAY) YÖNETİMİ API ---
@app.route('/api/dates', methods=['POST'])
@jwt_required()
def add_date():
    data = request.json
    user_id = data.get('user_id')
    
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    
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
    
    key_names = {
        'humor': 'Mizah Anlayışı',
        'finance': 'Finansal Tutum',
        'child': 'Çocuk İsteği',
        'communication': 'İletişim Sıklığı',
        'habit': 'Zararlı Alışkanlıklar'
    }

    for key, actual_val in attr_dict.items():
        if key in cv_dict:
            cv = cv_dict[key]
            expected_val = cv.expected_value
            readable_key = key_names.get(key, key)
            
            if expected_val == actual_val or expected_val in ["Farketmez", "Önemli Değil", "Sorun Değil"]:
                pros.append(f"{readable_key} tam istediğin gibi ({actual_val})")
            elif actual_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"] or expected_val in ["Dengeli", "Orta", "Sosyal İçici", "Kararsız"]:
                cons.append(f"{readable_key} konusunda orta yolu bulmanız gerekebilir (Sen: {expected_val} / O: {actual_val})")
            else:
                msg = f"{readable_key} dinamikleri tamamen zıt (Sen: {expected_val} / O: {actual_val})"
                if cv.is_red_flag:
                    critical_conflicts.append(msg)
                else:
                    cons.append(msg)
    
    db.close()
    
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

# 🚨 DÜZELTİLEN YER 1: NOVA DEDİKODU ASİSTANI (UZUN VE DETAYLI METİNLER) 🚨
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
        
        time.sleep(0.3) # Cevap geliyormuş hissi için biraz daha bekletiyoruz
        
        msg_lower = msg.lower()
        if "analiz" in msg_lower:
            bot_text = "Nova: Hemen laboratuvar kayıtlarını ve geçmiş verileri tarıyorum... Açık konuşmak gerekirse algoritmalarım bu kişi için tehlike çanları çalıyor. Kağıt üzerinde bir iki olumlu özelliği gözünü boyamasın, benim acımasız kırmızı çizgi tarayıcılarım bu profilde ciddi uyumsuzluklar tespit etti. Geçmişteki hatalarını tekrar etmek istemiyorsan, bu kişiyle arana acilen bir Çin Seddi çekmeli ve mantığını devreye sokmalısın. Onu sadece bir denek olarak gör, duygusal bir yatırım yapma! 🕵️‍♀️📉"
        elif "yazar mı" in msg_lower or "döner mi" in msg_lower:
            bot_text = "Nova: İstatistiklere ve benim yanılmaz veritabanıma göre, o mesajın gelme ihtimali maalesef oldukça düşük. Gelse bile, bu aranızdaki sorunların çözüldüğü anlamına gelmez; büyük ihtimalle sadece anlık bir can sıkıntısı veya ufak bir ego tatmini arayışıdır. Gerçekten o toksik döngüye tekrar girip kendi kusursuz uyum puanlarını sabote etmek istiyor musun? Telefonu yavaşça masaya bırak, derin bir nefes al ve kendine senin standartlarını gerçekten hak eden, daha yüksek puanlı kurbanlar bulmaya odaklan. 💅📵"
        elif "engelle" in msg_lower or "sil" in msg_lower:
            bot_text = "Nova: İşte tam olarak duymak istediğim o kararlı, soğukkanlı ve muhteşem ses! Hiç durma, saniye bile düşünme ve anında engelle. Bu laboratuvarda zayıflığa, gereksiz nostaljiye ve geri vitese asla yer yok. Sen sistemde %90 üstü uyum arayan birisin, böyle düşük puanlı ve vizyonsuz deneklerle vakit kaybetmek senin eşsiz veri havuzunu kirletmekten başka hiçbir işe yaramaz. Arşivden siliyoruz, temiz bir sayfa açıyoruz. Sıradaki denek gelsin! 🛑🗑️✨"
        else:
            bot_text = "Nova: Seni çok iyi anlıyorum tatlım, ama olaya biraz daha mantıksal, analitik ve tamamen soğukkanlı yaklaşman gerekiyor. Duygularının senin o güzel zihnini yönetmesine izin verirsen, o titizlikle hazırladığımız uyum puanları ve kırmızı çizgiler hiçbir işe yaramaz. Lütfen bana detaylardan, hareketlerinden ve o kişinin somut eylemlerinden bahset ki sana çok daha acımasız, nokta atışı ve doğru bir teşhis koyabileyim. Sınırlarını koru ve asla gardını indirme! 🧠✨"
        
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

# 🚨 DÜZELTİLEN YER 2: TRENDLER BÖLÜMÜ (UZUN VE DETAYLI METİNLER) 🚨
@app.route('/api/trends/<user_id>', methods=['GET'])
@jwt_required()
def get_trends(user_id):
    if get_jwt_identity() != user_id:
        return jsonify({"error": "Yetkisiz erişim."}), 403

    db = SessionLocal()
    profiles = db.query(DateProfile).filter_by(user_id=user_id).all()
    total = len(profiles)
    
    if total == 0:
        insight = "Laboratuvarda henüz in cin top oynuyor... Hiçbir denek verisi bulamadığım için sana laf bile sokamıyorum! Sistemdeki algoritmalarım paslanmadan önce hemen sağ üstten birilerini ekle de, şöyle detaylı bir analiz yapıp hep beraber o kişileri biraz kınayalım! 🕸️🧐"
    else:
        avg_score = sum(p.score for p in profiles) / total
        
        if avg_score >= 75:
            insight = f"İnanılmaz bir istatistik! Havuzundaki toplam {total} adayın genel not ortalaması tam olarak %{int(avg_score)}. Açıkçası zor beğenen algoritmalarım bile bu muazzam sonuca şaşırdı. Helal olsun sana! Standartların gerçekten çok yüksek ve hayatına sadece senin kalitende, beklentilerini karşılayabilecek insanları alıyorsun. Kırmızı çizgilerini harika bir şekilde koruyorsun. Bu gidişle o kusursuz %100 eşleşmeyi yakalaman sadece an meselesi. Aynen böyle dik durmaya devam et, laboratuvar senin bu üstün performansınla gurur duyuyor! 🥂😎✨"
        elif avg_score >= 50:
            insight = f"Sistemdeki verileri taradığımda havuzundaki {total} adayın ortalamasının %{int(avg_score)} olduğunu görüyorum. Ne desem bilemedim... Tamamen ortalama, sıradan ve 'güvenli ama fena halde sıkıcı' sularda yüzüyoruz. Ne tam bir felaket diyebileceğimiz bir facia var ortada, ne de heyecandan ekranımı parlatacak o 'İşte bu!' dedirten efsanevi profil. Standartlarını biraz daha mı netleştirsen acaba? Yoksa böyle sadece 'idare eder' puanlı profillerle veri havuzunu doldurmaya ve zaman kaybetmeye devam mı edeceksin? Daha acımasız ve seçici olma vakti çoktan geldi de geçiyor! 🤷‍♂️📊"
        else:
            insight = f"Sistem alarm veriyor! Havuzundaki {total} adayın ortalaması maalesef felaket bir seviyede: %{int(avg_score)}. Gerçekten inanılmaz... Usta sen dışarıda nerede senin kırmızı çizgilerini ihlal eden, toksik, sorunlu ve sana tamamen zıt (Red Flag) insan varsa hepsini bir mıknatıs gibi hayatına çekmişsin! Şımarık egoistlerden tut, iletişim fukaralarına kadar hepsi burada. Veritabanım bu düşük eşleşmeleri analiz ederken adeta acı çekiyor. Acil olarak hayatındaki bu taktiği değiştirmemiz ve senin o içindeki 'belki onu düzeltirim' kompleksinden kurtulman lazım. Yoksa bu gidişle laboratuvardan sağ çıkamayacağız. Acilen kendine gel ve çöp sepetini kullanmaya başla! 🚩😅📉"

    db.close()
    
    return jsonify({
        "total": total,
        "macro_insight": insight
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