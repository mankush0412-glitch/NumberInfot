import sqlite3
from fastapi import FastAPI, Header, HTTPException, Depends
from config import load_config
import key_store

cfg = load_config()
key_store.init_db(cfg.keys_db)

app = FastAPI(title="Private Users API", docs_url=None, redoc_url=None, openapi_url=None)

def verify_key(x_api_key: str | None = Header(None, alias="X-API-Key")):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if not key_store.validate_key(cfg.keys_db, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or disabled API key")

def db():
    if not cfg.production_db.exists():
        raise HTTPException(status_code=503, detail="Database not installed")
    conn = sqlite3.connect(
        f"file:{cfg.production_db}?mode=ro",
        uri=True,
        timeout=10,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/")
def health():
    return {"status": "ok"}

@app.get("/user/{mobile}", dependencies=[Depends(verify_key)])
def user(mobile: str):
    if not mobile.isdigit() or len(mobile) != 10:
        raise HTTPException(status_code=400, detail="Invalid mobile number")
    conn = db()
    try:
        rows = conn.execute(
            "SELECT mobile,name,fname,address,alt,circle,id FROM users WHERE mobile=?",
            (mobile,)
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="User not found")

    results = [dict(row) for row in rows]

    # Backward compatible:
    # old clients can still read top-level name/mobile/etc from the first record,
    # while updated clients can read every match from "results".
    payload = dict(results[0])
    payload["count"] = len(results)
    payload["results"] = results
    return payload

@app.get("/stats", dependencies=[Depends(verify_key)])
def stats():
    conn = db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()
    return {"users": count}


@app.get("/id/{record_id}", dependencies=[Depends(verify_key)])
def lookup_by_id(record_id: str):
    # Exact internal 12-digit ID only.
    if not record_id.isdigit() or len(record_id) != 12:
        raise HTTPException(
            status_code=400,
            detail="Exact 12-digit ID required"
        )

    conn = db()
    try:
        rows = conn.execute(
            "SELECT mobile,name,fname,address,alt,circle,id "
            "FROM users WHERE id=?",
            (record_id,)
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Record not found")

    results = [dict(row) for row in rows]

    payload = dict(results[0])
    payload["count"] = len(results)
    payload["results"] = results
    return payload
