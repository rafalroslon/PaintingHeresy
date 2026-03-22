import sys
import os
import threading
import sqlite3
import base64
import io

from flask import Flask, jsonify, request, render_template, send_from_directory
from PIL import Image

# ═══════════════════════════════════════════════
#  WERSJA APLIKACJI
# ═══════════════════════════════════════════════
APP_VERSION    = "1.0.0"
UPDATE_URL     = "https://YOUR-APP.railway.app/version"  # ← zmień po deploymencie

# ═══════════════════════════════════════════════
#  ŚCIEŻKI — działają zarówno w dev jak i w .exe
# ═══════════════════════════════════════════════

def get_base_dir():
    """Katalog gdzie leżą bazy danych (obok .exe lub obok app.py)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_dir():
    """Katalog z zasobami (templates itp.) — wewnątrz .exe lub obok app.py"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR     = get_base_dir()
RESOURCE_DIR = get_resource_dir()

DB_PATH         = os.path.join(BASE_DIR, 'mycollection.db')
CITADEL_DB_PATH = os.path.join(BASE_DIR, 'PaintsReq.db')

CATEGORIES = ["Base", "Layer", "Shade", "Dry", "Contrast", "Technical", "Primer"]

# ═══════════════════════════════════════════════
#  FLASK APP
# ═══════════════════════════════════════════════

app = Flask(
    __name__,
    template_folder=os.path.join(RESOURCE_DIR, 'templates'),
    static_folder=os.path.join(RESOURCE_DIR, 'static')
)

# ── DB helpers ──────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS paints
                 (id INTEGER PRIMARY KEY, name TEXT, category TEXT, image BLOB)''')
    conn.commit()
    return conn

def get_citadel_db():
    conn = sqlite3.connect(CITADEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def blob_to_base64(blob):
    if not blob:
        return None
    try:
        img = Image.open(io.BytesIO(blob)).convert("RGB")
        img.thumbnail((400, 400), Image.Resampling.LANCZOS)
        bio = io.BytesIO()
        img.save(bio, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(bio.getvalue()).decode()
    except Exception:
        return None

# ── Routes ───────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', categories=CATEGORIES)

@app.route('/api/paints', methods=['GET'])
def get_paints():
    category = request.args.get('category', 'All')
    search   = request.args.get('search', '').strip()
    conn = get_db()
    c    = conn.cursor()
    query  = "SELECT id, name, category, image FROM paints WHERE 1=1"
    params = []
    if category != 'All':
        query += " AND category = ?"
        params.append(category)
    if search:
        query += " AND LOWER(name) LIKE LOWER(?)"
        params.append(f"%{search}%")
    query += " ORDER BY name"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append({
            'id':       row['id'],
            'name':     row['name'],
            'category': row['category'],
            'image':    blob_to_base64(row['image'])
        })
    return jsonify(result)

@app.route('/api/paints', methods=['POST'])
def add_paint():
    data     = request.get_json()
    name     = data.get('name', '').strip()
    category = data.get('category', '').strip()
    source   = data.get('source', 'manual')
    if not name or not category:
        return jsonify({'error': 'Name and category required'}), 400

    blob = None
    if source == 'citadel':
        try:
            cdb = get_citadel_db()
            cc  = cdb.cursor()
            cc.execute("SELECT image FROM paints WHERE name=? AND category=?", (name, category))
            row = cc.fetchone()
            cdb.close()
            if row and row['image']:
                blob = row['image']
        except Exception:
            pass
    else:
        img_data = data.get('image')
        if img_data and img_data.startswith('data:image'):
            try:
                _, encoded = img_data.split(',', 1)
                blob = base64.b64decode(encoded)
            except Exception:
                blob = None
        if not blob:
            try:
                cdb = get_citadel_db()
                cc  = cdb.cursor()
                cc.execute("SELECT image FROM paints WHERE name=? AND category=?", (name, category))
                row = cc.fetchone()
                cdb.close()
                if row and row['image']:
                    blob = row['image']
            except Exception:
                pass

    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT id FROM paints WHERE name=? AND category=?", (name, category))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Paint already in collection'}), 409
    c.execute("INSERT INTO paints (name, category, image) VALUES (?, ?, ?)", (name, category, blob))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'name': name, 'category': category}), 201

@app.route('/api/paints/<int:paint_id>', methods=['DELETE'])
def delete_paint(paint_id):
    conn = get_db()
    c    = conn.cursor()
    c.execute("DELETE FROM paints WHERE id=?", (paint_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': paint_id})

# ── NEWS CACHE ───────────────────────────────────────────────
import time
import urllib.request
import json as _json
import requests as _requests_lib

_news_cache      = {'items': [], 'fetched_at': 0}
_NEWS_TTL        = 3600  # 1 godzina
_NEWS_FEED_URL   = 'https://warcomfeed.link/feed.json'

def fetch_news():
    global _news_cache
    now = time.time()
    if now - _news_cache['fetched_at'] < _NEWS_TTL and _news_cache['items']:
        return _news_cache['items']
    try:
        resp   = _requests_lib.get(_NEWS_FEED_URL, timeout=10,
                                   headers={'User-Agent': 'PaintingHeresy/1.0'})
        data   = resp.json()
        items  = data.get('items', [])[:20]
        result = []
        for item in items:
            result.append({
                'title': item.get('title', ''),
                'url':   item.get('url', ''),
                'date':  item.get('date_published', '')[:10] if item.get('date_published') else '',
            })
        _news_cache = {'items': result, 'fetched_at': now}
        return result
    except Exception as e:
        app.logger.warning(f'News fetch error: {e}')
        return _news_cache['items']

@app.route('/api/check-new-paints', methods=['GET'])
def check_new_paints():
    try:
        query = '{ paints(brand: "Citadel") { name type } }'
        req = urllib.request.Request(
            "https://warpaint.fergcb.uk/graphql",
            data=_json.dumps({"query": query}).encode(),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'PaintingHeresy/1.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data   = _json.loads(resp.read().decode())
            paints = data.get("data", {}).get("paints", [])

        # Pobierz co jest w citadel.db
        cdb = get_citadel_db()
        cc  = cdb.cursor()
        cc.execute("SELECT name FROM paints")
        existing = {row[0].lower() for row in cc.fetchall()}
        cdb.close()

        # Znajdź nowe
        new_paints = []
        for p in paints:
            if p.get('name', '').lower() not in existing:
                new_paints.append({
                    'name':     p.get('name', ''),
                    'category': p.get('type', '').capitalize()
                })

        return jsonify({
            'new_count': len(new_paints),
            'new_paints': new_paints[:50]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'new_count': 0, 'new_paints': []}), 200

@app.route('/api/check-update', methods=['GET'])
def check_update():
    try:
        resp = _requests_lib.get(UPDATE_URL, timeout=8,
                                 headers={'User-Agent': 'PaintingHeresy/' + APP_VERSION})
        data = resp.json()

        remote_version = data.get('version', '0.0.0')
        has_update     = _version_gt(remote_version, APP_VERSION)

        return jsonify({
            'current_version': APP_VERSION,
            'latest_version':  remote_version,
            'has_update':      has_update,
            'download_url':    data.get('download_url', ''),
            'mandatory':       data.get('mandatory', False),
            'changelog':       data.get('changelog', []),
            'release_date':    data.get('release_date', ''),
        })
    except Exception as e:
        return jsonify({
            'current_version': APP_VERSION,
            'has_update': False,
            'error': str(e)
        })

def _version_gt(v1, v2):
    """Zwraca True jeśli v1 > v2 (np. '1.2.0' > '1.0.0')"""
    try:
        a = [int(x) for x in v1.split('.')]
        b = [int(x) for x in v2.split('.')]
        return a > b
    except Exception:
        return False

@app.route('/api/current-version', methods=['GET'])
def current_version():
    return jsonify({'version': APP_VERSION})

@app.route('/api/news', methods=['GET'])
def get_news():
    return jsonify(fetch_news())

# ── PDF LIBRARY ──────────────────────────────────────────────

PDF_DIR = os.path.join(BASE_DIR, 'pdfs')

@app.route('/api/pdfs', methods=['GET'])
def get_pdfs():
    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR)
    files = []
    for f in sorted(os.listdir(PDF_DIR)):
        if f.lower().endswith('.pdf'):
            path = os.path.join(PDF_DIR, f)
            size = os.path.getsize(path)
            files.append({
                'filename': f,
                'title':    os.path.splitext(f)[0].replace('_', ' ').replace('-', ' '),
                'size_kb':  round(size / 1024),
            })
    return jsonify(files)

@app.route('/pdfs/<path:filename>', methods=['GET'])
def serve_pdf(filename):
    if not os.path.exists(PDF_DIR):
        return 'Not found', 404
    return send_from_directory(PDF_DIR, filename)

@app.route('/api/citadel', methods=['GET'])
def get_citadel():
    search = request.args.get('search', '').strip()
    try:
        cdb = get_citadel_db()
        cc  = cdb.cursor()
        if search:
            cc.execute(
                "SELECT name, category, image FROM paints WHERE LOWER(name) LIKE LOWER(?) ORDER BY name",
                (f"%{search}%",))
        else:
            cc.execute("SELECT name, category, image FROM paints ORDER BY name")
        rows = cc.fetchall()
        cdb.close()
        result = []
        for row in rows:
            result.append({
                'name':     row['name'],
                'category': row['category'],
                'image':    blob_to_base64(row['image'])
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT category, COUNT(*) as cnt FROM paints GROUP BY category ORDER BY cnt DESC")
    rows  = c.fetchall()
    c.execute("SELECT COUNT(*) as total FROM paints")
    total = c.fetchone()['total']
    conn.close()
    return jsonify({
        'total': total,
        'by_category': [{'category': r['category'], 'count': r['cnt']} for r in rows]
    })

# ═══════════════════════════════════════════════
#  URUCHOMIENIE
# ═══════════════════════════════════════════════

def run_flask():
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

def main():
    # Sprawdź czy citadel.db istnieje
    if not os.path.exists(CITADEL_DB_PATH):
        import tkinter.messagebox as mb
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        mb.showerror(
            "Brak pliku",
            f"Nie znaleziono citadel.db!\n\nUpewnij się że plik citadel.db\n"
            f"jest w tym samym folderze co aplikacja:\n{BASE_DIR}"
        )
        root.destroy()
        sys.exit(1)

    # Uruchom Flask w wątku w tle
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    # Poczekaj chwilę aż Flask się uruchomi
    import time
    time.sleep(0.8)

    # Otwórz okno PyWebView
    import webview
    webview.create_window(
        title     = 'Painting Heresy',
        url       = 'http://127.0.0.1:5000',
        width     = 1400,
        height    = 900,
        min_size  = (1000, 600),
        resizable = True,
    )
    webview.start()

if __name__ == '__main__':
    main()
