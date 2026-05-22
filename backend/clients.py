"""Torrent client adapters."""
import os, requests, base64

class QBitClient:
    def __init__(self, host, user, password, category="anime", save_path=""):
        self.host = host.rstrip("/")
        self.user, self.password = user, password
        self.category, self.save_path = category, save_path
        self.s = requests.Session()
        self._logged_in = False

    def login(self):
        try:
            r = self.s.post(f"{self.host}/api/v2/auth/login",
                            data={"username": self.user, "password": self.password}, timeout=8)
            self._logged_in = r.text.strip() == "Ok."
            return self._logged_in
        except Exception:
            return False

    def add(self, magnet_or_url: str, paused=False) -> bool:
        if not self._logged_in and not self.login(): return False
        data = {"urls": magnet_or_url, "category": self.category,
                "paused": "true" if paused else "false"}
        if self.save_path: data["savepath"] = self.save_path
        try:
            r = self.s.post(f"{self.host}/api/v2/torrents/add", data=data, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

def save_torrent_file(url: str, dest_dir: str) -> str | None:
    os.makedirs(dest_dir, exist_ok=True)
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200: return None
        name = url.rsplit("/", 1)[-1].split("?")[0] or "download.torrent"
        path = os.path.join(dest_dir, name)
        with open(path, "wb") as f: f.write(r.content)
        return path
    except Exception:
        return None

def magnet_to_file(magnet: str, dest_dir: str, name: str = "link.magnet") -> str:
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, name)
    with open(path, "w") as f: f.write(magnet)
    return path
