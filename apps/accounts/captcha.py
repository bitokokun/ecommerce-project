"""
Cloudflare Turnstile verification (free CAPTCHA alternative).

The browser shows the Turnstile widget and gets back a one-time token; the
server must confirm that token with Cloudflare using the SECRET key. Checking
only in the browser would prove nothing, since a script can skip the page.

If TURNSTILE_SECRET_KEY is not set (local dev, or before you've created keys),
verification is skipped so nothing breaks. Once it IS set, a missing or
invalid token is rejected.
"""
import json
import os
import urllib.parse
import urllib.request

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token, remote_ip=None):
    secret = os.environ.get("TURNSTILE_SECRET_KEY")
    if not secret:
        return True
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
        # Can't reach Cloudflare: refuse rather than let signups through unchecked.
        return False
