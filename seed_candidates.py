import uuid
import random
from database import SessionLocal
from models import DataType, CriteriaCatalog, Candidate, CandidateAttribute, CandidatePreference, MatchInteraction

def seed_data():
    db = SessionLocal()
    try:
        print("🚀 Sistem hafızası sıfırlanıyor ve yeni adaylar yaratılıyor...")

        # 1. VERİ TİPLERİ VE KRİTERLER (Değişmedi)
        text_type = db.query(DataType).filter(DataType.name == "Metin").first()
        if not text_type:
            text_type = DataType(name="Metin")
            db.add(text_type)
            db.commit()
            db.refresh(text_type)

        number_type = db.query(DataType).filter(DataType.name == "Sayı").first()
        if not number_type:
            number_type = DataType(name="Sayı")
            db.add(number_type)
            db.commit()
            db.refresh(number_type)

        criteria_list = [
            ("Cinsiyet", text_type.id),
            ("Yaş", number_type.id),
            ("Boy", number_type.id),
            ("Aranan Cinsiyet", text_type.id),
            ("İlişki Hedefi", text_type.id)
        ]

        cat_map = {}
        for name, dt_id in criteria_list:
            catalog = db.query(CriteriaCatalog).filter(CriteriaCatalog.name == name).first()
            if not catalog:
                catalog = CriteriaCatalog(name=name, data_type_id=dt_id)
                db.add(catalog)
                db.commit()
                db.refresh(catalog)
            cat_map[name] = catalog.id

        # 2. ESKİ ETKİLEŞİMLERİ VE ADAYLARI TEMİZLE (Kilit Nokta Burası!)
        db.query(MatchInteraction).delete()
        db.query(CandidateAttribute).delete()
        db.query(CandidatePreference).delete()
        db.query(Candidate).delete()
        db.commit()

        # 3. YENİ YAPAY ADAYLARI OLUŞTURMA
        first_names = ["Melis", "Can", "Ece", "Burak", "Zeynep", "Mert", "Damla", "Kaan", "Aslı", "Deniz", 
                       "Selin", "Emre", "Buse", "Arda", "Gözde", "Tolga", "İrem", "Oğuz", "Gamze", "Yiğit"]
        
        genders = ["Kadın", "Erkek"]
        goals = ["Ciddi İlişki", "Flört", "Sadece Sohbet"]

        print("👥 20 Taze aday vitrine ekleniyor...")
        for i in range(20):
            cand_id = str(uuid.uuid4())
            cand_name = f"{first_names[i]} #{random.randint(100, 999)}"
            
            cand_gender = genders[i % 2]
            cand_age = random.randint(19, 26)
            cand_height = random.randint(160, 190) if cand_gender == "Erkek" else random.randint(155, 178)
            
            cand_pref_gender = "Erkek" if cand_gender == "Kadın" else "Kadın"
            if random.random() > 0.85: cand_pref_gender = "Farketmez"
            cand_goal = random.choice(goals)

            new_cand = Candidate(id=cand_id, candidate_name=cand_name)
            db.add(new_cand)

            db.add(CandidateAttribute(candidate_id=cand_id, criteria_id=cat_map["Cinsiyet"], value=cand_gender))
            db.add(CandidateAttribute(candidate_id=cand_id, criteria_id=cat_map["Yaş"], value=str(cand_age)))
            db.add(CandidateAttribute(candidate_id=cand_id, criteria_id=cat_map["Boy"], value=str(cand_height)))

            db.add(CandidatePreference(candidate_id=cand_id, criteria_id=cat_map["Aranan Cinsiyet"], value=cand_pref_gender, importance=1.0))
            db.add(CandidatePreference(candidate_id=cand_id, criteria_id=cat_map["İlişki Hedefi"], value=cand_goal, importance=random.choice([0.5, 0.8, 1.0])))

        db.commit()
        print("🎉 BAŞARILI: Hafıza temizlendi, 20 yeni aday eklendi!")

    except Exception as e:
        db.rollback()
        print(f"❌ HATA: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()