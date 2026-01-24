import os
from openai import OpenAI
import json

# Eğer .env kullanıyorsanız oradan çeker, yoksa buraya string olarak yazabilirsiniz (güvenlik için env önerilir)
# os.environ["OPENAI_API_KEY"] = "sk-..." 
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def get_gpt_response(prompt):
    """
    Verilen prompt'u GPT'ye gönderir ve JSON formatında yanıt almaya zorlar.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # veya gpt-3.5-turbo-1106 (json modu destekleyen bir model seçin)
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" } # JSON garantisi için
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API Hatası: {e}")
        # Hata durumunda boş bir JSON string dönelim ki kod patlamasın
        return "{}"