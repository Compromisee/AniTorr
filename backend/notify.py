import requests, json

def discord(webhook_url: str, content: str, title: str = "ANITorr"):
    if not webhook_url: return False
    try:
        requests.post(webhook_url, json={"username": title, "content": content}, timeout=8)
        return True
    except Exception: return False

def ntfy(url: str, topic: str, msg: str, title: str = "ANITorr"):
    try:
        requests.post(f"{url.rstrip('/')}/{topic}", data=msg.encode(),
                      headers={"Title": title}, timeout=8); return True
    except Exception: return False

def telegram(token: str, chat_id: str, msg: str):
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": msg}, timeout=8); return True
    except Exception: return False
