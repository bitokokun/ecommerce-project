import json
import os
import urllib.parse
import urllib.request
from django.conf import settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token, remote_ip=None):
    secret = os.environ.get("TURNSTILE_SECRET_KEY")
    if not secret:
        return bool(settings.DEBUG)
    if not token:
        return False

    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    req = urllib.request.Request(VERIFY_URL, data=urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return bool(json.load(resp).get("success"))
    except Exception:
        return False
