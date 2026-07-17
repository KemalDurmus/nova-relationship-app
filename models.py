import uuid
import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

# --- KULLANICI TABLOSU ---
class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String)
    
    # 💸 Paywall (Ödeme Duvarı) Alanları
    is_premium = Column(Boolean, default=False)
    subscription_end_date = Column(DateTime, nullable=True)
    
    # 🎮 Oyunlaştırma (Gamification) Alanları
    xp_points = Column(Integer, default=0)
    deleted_dates_count = Column(Integer, default=0)
    
    # 🔗 Veritabanı İlişkileri (Kullanıcı silinirse ona ait her şey silinir)
    badges = relationship("UserBadge", back_populates="user", cascade="all, delete-orphan")
    cv_records = relationship("RelationshipCV", back_populates="user", cascade="all, delete-orphan")
    dates = relationship("DateProfile", back_populates="user", cascade="all, delete-orphan")
    coaching_logs = relationship("NovaCoachingLog", back_populates="user", cascade="all, delete-orphan")
    journals = relationship("RelationshipJournal", back_populates="user", cascade="all, delete-orphan")

# --- KULLANICI ROZETLERİ (GAMIFICATION) ---
class UserBadge(Base):
    __tablename__ = 'user_badges'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    badge_code = Column(String, nullable=False) # Örn: 'TOXIC_MAGNET', 'SURGEON'
    badge_name = Column(String, nullable=False) # Örn: 'Toksik Mıknatısı 🚩'
    earned_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="badges")

# --- İLİŞKİ CV'Sİ (KULLANICI BEKLENTİLERİ) ---
class RelationshipCV(Base):
    __tablename__ = 'relationship_cv'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    criteria_key = Column(String, nullable=False)
    expected_value = Column(String, nullable=False)
    importance = Column(Integer, default=50)
    is_red_flag = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="cv_records")

# --- DATE PROFİLİ (EKLENEN ADAYLAR) ---
class DateProfile(Base):
    __tablename__ = 'date_profiles'
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    job_or_education = Column(String)
    notes = Column(Text)
    score = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="dates")
    attributes = relationship("DateAttribute", back_populates="profile", cascade="all, delete-orphan")

# --- ADAYIN DETAYLI ÖZELLİKLERİ ---
class DateAttribute(Base):
    __tablename__ = 'date_attributes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    date_id = Column(String, ForeignKey('date_profiles.id'), nullable=False)
    criteria_key = Column(String, nullable=False)
    actual_value = Column(String, nullable=False)
    
    profile = relationship("DateProfile", back_populates="attributes")

# --- NOVA YAPAY ZEKA KOÇLUK GEÇMİŞİ ---
class NovaCoachingLog(Base):
    __tablename__ = 'nova_coaching_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    sender = Column(String, nullable=False) # 'user' veya 'nova'
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="coaching_logs")

# --- TERAPİ GÜNLÜĞÜ ---
class RelationshipJournal(Base):
    __tablename__ = 'relationship_journals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    entry_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="journals")