import sys
from app.config.settings import settings
from google import genai

print("API Key len:", len(settings.GEMINI_API_KEY))
print("Model:", settings.GEMINI_MODEL)

if not settings.GEMINI_API_KEY:
    print("API Key is empty!")
    sys.exit(1)

client = genai.Client(api_key=settings.GEMINI_API_KEY)
try:
    res = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents="Hello! Please confirm model working.",
    )
    print("SUCCESS:", res.text)
except Exception as e:
    print("ERROR:", type(e).__name__, ":", e)
