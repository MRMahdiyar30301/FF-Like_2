import requests

LIKE_API = "https://likes-api-lkteam-v3.onrender.com/like"
INFO_API = "https://info-ob49.vercel.app/api/account/"

# ریجن‌های معتبر فری فایر - ایران = ME
VALID_REGIONS = ["sg", "me", "ind", "bd", "pk", "id", "br", "na", "vn", "th", "tw", "ru", "sac", "sic"]
DEFAULT_REGION = "me"

def get_player_info(uid: int, region=DEFAULT_REGION):
    try:
        r = requests.get(INFO_API, params={"uid": uid, "region": region}, timeout=25)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def send_likes(uid: int, region=DEFAULT_REGION, count=165) -> dict:
    region = region.lower() if region else DEFAULT_REGION
    if region not in VALID_REGIONS:
        region = DEFAULT_REGION
    try:
        r = requests.get(
            LIKE_API,
            params={"uid": uid, "region": region, "count": count},
            timeout=120
        )
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                data = {}
            status = str(data.get("status", data.get("success", ""))).lower()
            if status in ("success", "ok", "true", "1"):
                return {"ok": True}
            text = r.text.lower()
            if "success" in text or "liked" in text or "sent" in text:
                return {"ok": True}
            return {"ok": False, "error": str(data) or r.text[:100]}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}