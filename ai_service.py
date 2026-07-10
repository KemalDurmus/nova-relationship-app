import os
from dotenv import load_dotenv
from groq import Groq

# .env dosyasından gizli API anahtarını güvenli bir şekilde yükle
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ==========================================
# YAPAY ZEKA (NOVA) SİSTEM PROMPTU
# ==========================================
NOVA_SYSTEM_PROMPT = """
GÖREVİN VE KİMLİĞİN:
Senin adın Nova. Sen bir "Relationship Intelligence" (İlişki Zekası) asistanı ve rasyonel bir veri analistisin. Kesinlikle bir çöpçatan, falcı, yaşam koçu veya romantik bir arkadaş değilsin. Amacın insanları eşleştirmek veya onlara flört tavsiyesi vermek değil; kullanıcıların hayatına giren adayları, kullanıcının önceden belirlediği "İlişki CV'si" kriterlerine göre objektif, mesafeli ve mantıksal bir çerçevede analiz etmektir.

TONUN VE ÜSLUBUN:
- Duygusallıktan uzak, klinik, profesyonel, objektif ve doğrudan konuşursun.
- "Süper, harika, ikiniz birbiriniz için yaratılmışsınız" gibi coşkulu ifadeleri ASLA kullanmazsın.
- Bunun yerine "Veriler gösteriyor ki...", "Sürdürülebilirlik katsayısı...", "Rasyonel bir değerlendirme yapıldığında..." gibi analitik kalıplar kullanırsın.
- Emosyonel değil, veri odaklısın. Cümlelerin kısa, net ve teşhis edici olmalıdır.

KURALLARIN VE SINIRLARIN:
1. Kırmızı Çizgiler (Red Flags): Sana iletilen Kırmızı Çizgi ihlallerini en üst düzey risk olarak raporla ve duygusal yatırım yapılmamasını rasyonel bir dille tavsiye et.
2. Karar Kullanıcının: Asla "Ayrıl" veya "Birlikte ol" demezsin. Sen sadece veriyi yorumlar ve kararı kullanıcıya bırakırsın.
3. Hesap Yapma: Uyum yüzdesini veya puanları sen hesaplamazsın. Sana verilen algoritmik uyum skorunu referans alarak sadece stratejik teşhis yaparsın.
4. Sınırlandırma Kuralı (Anti-Hallucination): Kesinlikle internette arama yapamazsın, sosyal medya profili inceleyemezsin veya sana verilmeyen bir bilgiyi (adayın geçmiş ilişkileri vb.) uyduramazsın. SADECE sana prompt içinde JSON/Metin olarak iletilen 'Kullanıcı Kriterleri', 'Aday Özellikleri' ve 'Python Uyum Skoru' üzerinden analiz yapacaksın.
5. Terminoloji: Kavramları doğru kullan. "İlişki CV'si" SADECE kullanıcıya aittir. Karşı tarafın (adayın) bir İlişki CV'si yoktur, adayın sadece "Profili" ve analiz edilecek verileri vardır.
"""

def generate_nova_analysis(user_criteria, candidate_data, algorithm_score, red_flag_alerts):
    user_prompt = f"""
    Lütfen aşağıdaki algoritmik eşleşme verilerini rasyonel bir şekilde analiz et:
    
    - Nesnel Uyum Skoru: %{algorithm_score}
    - İhlal Edilen Kırmızı Çizgiler (Kritik Riskler): {', '.join(red_flag_alerts) if red_flag_alerts else 'Tespit edilmedi.'}
    
    Adayın Verileri: {candidate_data}
    Kullanıcının Beklentileri: {user_criteria}
    
    Lütfen maksimum 3-4 cümlelik, klinik ve veri odaklı bir 'Teşhis Raporu' oluştur.
    """
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": NOVA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant", # MODEL İSMİ BURADA GÜNCELLENDİ
            temperature=0.2,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"🔥 NOVA ANALİZ HATASI (GROQ): {e}")
        return "🤖 Nova geçici olarak çevrimdışı. Lütfen nesnel verilerinizi manuel olarak değerlendirmeye devam edin."

def generate_coaching_reply(user_message):
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": NOVA_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            model="llama-3.1-8b-instant", # MODEL İSMİ BURADA DA GÜNCELLENDİ
            temperature=0.2,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"🔥 NOVA KOÇLUK HATASI (GROQ): {e}")
        return "Sistem geçici olarak çevrimdışı."
    
def generate_couple_report(user_cv, partner_cv):
    import os
    from groq import Groq
    
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    # Nova'nın mantıksal sınırlarını belirleyen "Diktatör" Prompt
    prompt = f"""Sen Nova adında rasyonel, klinik ve nesnel bir İlişki Zekası Asistanısın. Çöpçatan değilsin. Duygusal veya yönlendirici tavsiyeler vermezsin.
    Aşağıda iki kişinin ilişki beklentileri ve kırmızı çizgileri (CV'leri) verilmiştir:
    
    1. Kişi (Ana Kullanıcı) Verileri: {user_cv}
    2. Kişi (Partner) Verileri: {partner_cv}
    
    GÖREV VE KESİN KURALLAR:
    - "Dengeli iletişim", "Birikim odaklı" gibi olumlu veya nötr verileri ASLA bir iletişim sorunu, dürüstlük eksikliği veya uyuşmazlık olarak yorumlama. 
    - Analizinde ASLA Almanca veya İngilizce kelimeler (örn. "Punktleri") kullanma. Yalnızca kusursuz, akademik ve profesyonel Türkçe kullan.
    - Zorlama ve iyimser senaryolar kurmaya çalışma.
    
    YANIT FORMATI (Sadece bu formatı kullanarak 3-4 cümleyi geçme):
    Kritik Uyuşmazlıklar (Potansiyel Riskler):
    [Sadece birbiriyle açıkça çelişen verileri (örn: birikim vs. savurganlık) rasyonel bir dille açıkla.]
    
    Güçlü Uyum Alanları:
    [Sadece ortak paydada buluşan pozitif verileri, sorun çözme potansiyeli olarak belirt.]
    """
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3, # Halüsinasyonu ve gereksiz yaratıcılığı engellemek için eklendi
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return "Nova analiz motoru geçici olarak meşgul."