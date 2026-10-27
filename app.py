"""Small, single-process prototype for photo-assisted electrical service requests."""
import base64
import hmac
import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 9 * 1024 * 1024
DB = os.getenv("DATABASE_PATH", "volt.db")
Path(DB).parent.mkdir(parents=True, exist_ok=True)
SERVICES = {"outlet": "Socket installation", "lighting": "Lighting installation", "fault": "Electrical fault", "other": "Other"}


def database():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, name TEXT NOT NULL,
        contact TEXT NOT NULL, postcode TEXT NOT NULL, service TEXT NOT NULL,
        description TEXT NOT NULL, assessment TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new', price_eur INTEGER
    )""")
    return con


def assess(service, description, photos):
    """AI drafts an assessment; it never certifies safety or chooses a price."""
    key = os.getenv("OPENAI_API_KEY")
    if not key or not photos:
        return "Needs manual review (AI not configured or no photos provided)."
    content = [{"type": "text", "text": (
        f"Electrical service: {SERVICES[service]}. Customer says: {description}. "
        "Summarize only clearly visible facts, possible work scope, missing information, "
        "and safety concerns. Do not diagnose hidden wiring, provide repair instructions, "
        "declare installations safe, or invent prices. Under 150 words."
    )}]
    for kind, data in photos:
        content.append({"type": "image_url", "image_url": {"url": f"data:{kind};base64,{base64.b64encode(data).decode()}"}})
    payload = json.dumps({"model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                          "messages": [{"role": "user", "content": content}],
                          "max_tokens": 250}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.load(response)
        return result["choices"][0]["message"]["content"][:1500]
    except (OSError, KeyError, ValueError, IndexError, TypeError):
        return "AI assessment unavailable. Needs manual review."


def require_admin(func):
    @wraps(func)
    def protected(*args, **kwargs):
        password = os.getenv("ADMIN_PASSWORD", "")
        credentials = request.authorization
        if not password or not credentials or not hmac.compare_digest(credentials.password or "", password):
            return ("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Volt admin"'})
        return func(*args, **kwargs)
    return protected


def csrf_for(job_id):
    return hmac.new(os.environ["SECRET_KEY"].encode(), job_id.encode(), "sha256").hexdigest()


@app.get("/health")
def health():
    return "ok"


@app.get("/")
def index():
    return render_template("index.html", services=SERVICES)


@app.post("/requests")
def create_request():
    service = request.form.get("service", "")
    fields = {k: request.form.get(k, "").strip() for k in ("name", "contact", "postcode", "description")}
    if service not in SERVICES or any(not v for v in fields.values()) or any(len(v) > 2000 for v in fields.values()):
        abort(400, "All fields are required; check their length.")
    uploaded = [f for f in request.files.getlist("photos") if f.filename]
    if len(uploaded) > 3:
        abort(400, "Maximum 3 photos.")
    photos = []
    for f in uploaded:
        data = f.read(3 * 1024 * 1024 + 1)
        if len(data) > 3 * 1024 * 1024:
            abort(400, "Maximum 3 MB per photo.")
        kind = "image/jpeg" if data.startswith(b"\xff\xd8\xff") else "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else None
        if not kind:
            abort(400, "Only JPEG or PNG photos are supported.")
        photos.append((kind, data))
    summary = assess(service, fields["description"], photos)
    job_id = uuid4().hex[:12]
    with database() as con:
        con.execute("INSERT INTO jobs(id,created_at,name,contact,postcode,service,description,assessment) VALUES(?,?,?,?,?,?,?,?)",
                    (job_id, datetime.now(timezone.utc).isoformat(), fields["name"], fields["contact"], fields["postcode"], service, fields["description"], summary))
    return render_template("thanks.html", job_id=job_id), 201


@app.get("/admin")
@require_admin
def admin():
    with database() as con:
        jobs = con.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return render_template("admin.html", jobs=jobs, services=SERVICES, csrf_for=csrf_for)


@app.post("/admin/<job_id>/review")
@require_admin
def review(job_id):
    if not hmac.compare_digest(request.form.get("csrf", ""), csrf_for(job_id)):
        abort(403)
    price = request.form.get("price_eur", "").strip()
    if price and (not price.isdigit() or not 1 <= int(price) <= 1000000):
        abort(400, "Invalid price")
    with database() as con:
        cur = con.execute("UPDATE jobs SET status='reviewed',price_eur=? WHERE id=?", (int(price) if price else None, job_id))
        if not cur.rowcount:
            abort(404)
    return redirect(url_for("admin"))


if __name__ == "__main__":
    if not os.getenv("SECRET_KEY"):
        raise SystemExit("Set SECRET_KEY in your environment (see .env.example)")
    app.run(debug=False)
