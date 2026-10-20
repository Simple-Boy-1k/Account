import os

class Config:
    # Telegram Credentials
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    SESSION_STRING = os.environ.get("SESSION_STRING", "")
    
    # OpenAI Credentials
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    
    # AI System Prompt
    SYSTEM_PROMPT = os.environ.get(
        "SYSTEM_PROMPT", 
        "Aap ek friendly AI assistant ho jo mere behalf par polite aur natural tareeke se Hindi/Hinglish me reply karta hai."
    )
