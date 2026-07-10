from google import genai

API_KEY = "BURAYA_API_KEY_GELECEK"

try:
    client = genai.Client(api_key=API_KEY)
    print("Google sunucularındaki erişilebilir modeller taranıyor...\n")
    
    # Sistemin bize sunduğu tüm modelleri listeliyoruz
    for model in client.models.list():
        # Sadece işimize yarayacak 'gemini' modellerini filtrele
        if "gemini" in model.name:
            print(model.name)
            
except Exception as e:
    print("HATA:", e)