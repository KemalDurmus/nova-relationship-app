from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    display_name = Column(String)

class RelationshipCV(Base):
    __tablename__ = "relationship_cv"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    criteria_key = Column(String)
    expected_value = Column(String)
    importance = Column(Integer)
    is_red_flag = Column(Boolean, default=False)

class DateProfile(Base):
    __tablename__ = "date_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String) # Eğer user_id string(UUID) geliyorsa burayı da String yapman gerekebilir
    name = Column(String)
    age = Column(Integer, nullable=True)
    job_or_education = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow) # EKLENEN SATIR

class DateAttribute(Base):
    __tablename__ = "date_attributes"
    id = Column(Integer, primary_key=True, index=True)
    date_id = Column(Integer, ForeignKey("date_profiles.id"))
    criteria_key = Column(String)
    actual_value = Column(String)

class NovaCoachingLog(Base):
    __tablename__ = "nova_coaching_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    sender = Column(String) # 'user' veya 'nova'
    timestamp = Column(DateTime, default=datetime.utcnow)

class RelationshipJournal(Base):
    __tablename__ = "relationship_journals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    entry_text = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)   