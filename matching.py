from database import SessionLocal
from models import RelationshipCV, DateAttribute, DateProfile
from ai_service import generate_nova_analysis

CRITERIA_LABELS = {
    "humor": "Mizah Anlayışı",
    "finance": "Finansal Tutum",
    "child": "Gelecek Planı (Çocuk)",
    "communication": "Zaman Ayırma / İletişim",
    "habit": "Zararlı Alışkanlıklar"
}

def calculate_compatibility(user_id, date_id):
    db = SessionLocal()
    try:
        date_prof = db.query(DateProfile).filter_by(id=date_id).first()
        date_name = date_prof.name if date_prof else "Aday"

        cv_records = db.query(RelationshipCV).filter_by(user_id=user_id).all()
        attr_records = db.query(DateAttribute).filter_by(date_id=date_id).all()

        cv_dict = {c.criteria_key: {"expected": c.expected_value, "weight": c.importance, "red": c.is_red_flag} for c in cv_records}
        attr_dict = {a.criteria_key: a.actual_value for a in attr_records}

        total_weight = 0
        earned_score = 0
        
        pros = []
        cons = []
        critical_conflicts = []
        red_flag_count = 0

        for key, label in CRITERIA_LABELS.items():
            cv = cv_dict.get(key)
            actual = attr_dict.get(key)

            if cv and cv["expected"] and actual:
                w = cv["weight"]
                total_weight += w

                if cv["expected"] == actual:
                    earned_score += w
                    if w >= 75:
                        pros.append(f"Güçlü Ortak Nokta: {label} ({actual})")
                else:
                    if cv["red"]:
                        red_flag_count += 1
                        critical_conflicts.append(f"{label} Kırmızı Çizgisi: Sen '{cv['expected']}' beklerken, o '{actual}'.")
                    else:
                        if w >= 60:
                            cons.append(f"Önemli Uyuşmazlık Risk: {label} (Beklenti: {cv['expected']}, Mevcut: {actual})")

        if total_weight > 0:
            raw_percent = (earned_score / total_weight) * 100
        else:
            raw_percent = 50.0

        final_score = raw_percent - (red_flag_count * 40.0)
        final_score = max(0.0, min(100.0, final_score))
        final_score = round(final_score, 1)

        # YAPAY ZEKA API ÇAĞRISI BURADA YAPILIYOR
        analysis_text = generate_nova_analysis(cv_dict, attr_dict, final_score, critical_conflicts)

        return {
            "final_score": final_score,
            "pros": pros if pros else ["Belirgin bir güçlü ortak nokta saptanmadı."],
            "cons": cons if cons else ["Belirgin bir risk saptanmadı."],
            "critical_conflicts": critical_conflicts,
            "nova_message": analysis_text
        }
    finally:
        db.close()