from database import engine
from models import Base

print("🚀 Yeni İlişki Zekası (Relationship Intelligence) tabloları oluşturuluyor...")

# Yeni modellerdeki tüm tabloları veritabanına işler
Base.metadata.create_all(bind=engine)

print("✅ Veritabanı başarıyla güncellendi! Artık 'python app.py' komutuyla sistemi başlatabilirsin.")