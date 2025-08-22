import os
import json

# Tries to deduce a public base URL for media links.
# 1) BASE_URL env if set (e.g., your ngrok URL)
# 2) ngrok local API if available
# 3) fallback to http://127.0.0.1:8000

def get_public_base_url() -> str:
    base = os.getenv("BASE_URL")
    if base:
        return base.rstrip("/")
    # Try ngrok API
    try:
        import requests
        resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1)
        data = resp.json()
        tunnels = data.get("tunnels", [])
        for t in tunnels:
            if t.get("proto") == "https" and t.get("public_url"):
                return t["public_url"].rstrip("/")
    except Exception:
        pass
    return "http://127.0.0.1:8000"
