from database import engine, Base, SessionLocal
import models
from models import DataType, CriteriaCatalog

# 1. SİHİRLİ KOMUT: Veritabanında tabloları sıfırdan oluşturur
print("Tablolar kontrol ediliyor ve oluşturuluyor...")
Base.metadata.create_all(bind=engine)

def seed_criteria():
    db = SessionLocal()
    try:
        # 2. DATA TYPE (Veri Tipleri) KONTROLÜ VE EKLENMESİ
        print("Veri tipleri (DataType) ayarlanıyor...")
        
        types_to_add = ["MULTIPLE_CHOICE", "RANGE", "TEXT", "BOOLEAN"]
        type_objects = {}
        
        for type_name in types_to_add:
            dt = db.query(DataType).filter(DataType.name == type_name).first()
            if not dt:
                dt = DataType(name=type_name)
                db.add(dt)
                db.flush() # ID'nin hemen oluşması için veritabanına itiyoruz
            type_objects[type_name] = dt
        
        db.commit()

        # 3. CRITERIA CATALOG (Kriterler) KONTROLÜ VE EKLENMESİ
        print("Temel kriterler (CriteriaCatalog) ekleniyor...")
        
        default_criteria = [
            {"name": "Cinsiyet", "data_type_id": type_objects["MULTIPLE_CHOICE"].id},
            {"name": "Aranan Cinsiyet", "data_type_id": type_objects["MULTIPLE_CHOICE"].id},
            {"name": "Yaş", "data_type_id": type_objects["RANGE"].id},
            {"name": "Boy", "data_type_id": type_objects["RANGE"].id},
            {"name": "Sigara Kullanımı", "data_type_id": type_objects["MULTIPLE_CHOICE"].id},
            {"name": "İlişki Hedefi", "data_type_id": type_objects["MULTIPLE_CHOICE"].id},
            {"name": "Hobiler ve İlgi Alanları", "data_type_id": type_objects["TEXT"].id}
        ]

        for crit in default_criteria:
            exists = db.query(CriteriaCatalog).filter(CriteriaCatalog.name == crit["name"]).first()
            if not exists:
                new_criteria = CriteriaCatalog(
                    name=crit["name"], 
                    data_type_id=crit["data_type_id"]
                )
                db.add(new_criteria)
                
        db.commit()
        print("🎉 Başarılı! Veritabanı tabloları ve temel veriler (Seed) kusursuz bir şekilde oluşturuldu!")

    except Exception as e:
        db.rollback() # Hata çıkarsa işlemleri geri al
        print(f"❌ Bir hata oluştu: {str(e)}")
    finally:
        db.close() # İşimiz bitince bağlantıyı kapat

if __name__ == "__main__":
    print("Seed işlemi başlatılıyor...")
    seed_criteria()