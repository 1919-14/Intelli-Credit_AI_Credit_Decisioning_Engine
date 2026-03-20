import os
import threading

_groq_key_lock = threading.Lock()
_current_groq_index = 0

def get_rotated_groq_key():
    """Returns the next sequential general API key (API_KEY to API_KEY12)."""
    global _current_groq_index
    key_names = ["API_KEY"] + [f"API_KEY{i}" for i in range(1, 13)]
    
    with _groq_key_lock:
        start_index = _current_groq_index
        while True:
            key_name = key_names[_current_groq_index]
            key_val = os.getenv(key_name, "").strip()
            
            _current_groq_index = (_current_groq_index + 1) % len(key_names)
            
            if key_val:
                return key_val
            
            if _current_groq_index == start_index:
                return ""

def get_content_generation_key():
    """Returns the dedicated API key for content/decision generation (API_KEY13)."""
    return os.getenv("API_KEY13", "").strip()

def get_chatbot_key():
    """Returns the dedicated API key for chatbot streaming (API_KEY14)."""
    return os.getenv("API_KEY14", "").strip()
