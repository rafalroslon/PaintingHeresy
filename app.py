import sys
import os
import threading
import sqlite3
import base64
import io
import subprocess

from flask import Flask, jsonify, request, render_template, send_from_directory
from PIL import Image

# ═══════════════════════════════════════════════
#  WERSJA APLIKACJI
# ═══════════════════════════════════════════════
APP_VERSION    = "1.5.0"
UPDATE_URL     = "https://web-production-ca07e.up.railway.app/version"

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

@app.route('/api/download-update', methods=['POST'])
def download_update():
    """Pobiera nowy PaintingHeresy_app.exe w tle"""
    data         = request.get_json()
    download_url = data.get('url', '')
    new_version  = data.get('version', '')

    if not download_url:
        return jsonify({'error': 'No download URL'}), 400

    def do_download():
        try:
            temp_path = os.path.join(BASE_DIR, '_update_temp.exe')
            r = _requests_lib.get(download_url, stream=True, timeout=120,
                                  allow_redirects=True,
                                  headers={'User-Agent': f'PaintingHeresy/{APP_VERSION}'})
            total      = int(r.headers.get('content-length', 0))
            downloaded = 0

            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            # Zapisz nową wersję
            version_file = os.path.join(BASE_DIR, '_version.txt')
            with open(version_file, 'w') as f:
                f.write(new_version)

            app._update_ready    = True
            app._update_temp     = temp_path
            app._update_version  = new_version

        except Exception as e:
            app._update_error = str(e)

    app._update_ready = False
    app._update_error = None
    t = threading.Thread(target=do_download, daemon=True)
    t.start()
    return jsonify({'status': 'downloading'})

@app.route('/api/update-status', methods=['GET'])
def update_status():
    """Sprawdź status pobierania"""
    return jsonify({
        'ready': getattr(app, '_update_ready', False),
        'error': getattr(app, '_update_error', None),
    })

@app.route('/api/install-update', methods=['POST'])
def install_update():
    """Podmień plik i zrestartuj aplikację"""
    temp_path = getattr(app, '_update_temp', None)
    if not temp_path or not os.path.exists(temp_path):
        return jsonify({'error': 'No update file'}), 400

    app_exe  = os.path.join(BASE_DIR, 'PaintingHeresy.exe')
    bat_path = os.path.join(BASE_DIR, '_update.bat')

    bat_content = f"""@echo off
timeout /t 3 /nobreak >nul
taskkill /f /im PaintingHeresy.exe >nul 2>&1
timeout /t 3 /nobreak >nul
move /y "{temp_path}" "{app_exe}"
timeout /t 2 /nobreak >nul
start "" "{app_exe}"
del "%~f0"
"""
    with open(bat_path, 'w') as f:
        f.write(bat_content)

    subprocess.Popen(
        ['cmd', '/c', bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    # Zamknij aplikację — ignoruj błędy PyWebView
    def shutdown():
        import time as _t
        _t.sleep(1)
        try:
            import webview
            for w in webview.windows:
                w.destroy()
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            pass
    threading.Thread(target=shutdown, daemon=True).start()

    return jsonify({'status': 'installing'})

@app.route('/api/changelog', methods=['GET'])
def get_changelog():
    """Zawsze zwraca pełny changelog z serwera"""
    try:
        resp = _requests_lib.get(UPDATE_URL, timeout=8,
                                 headers={'User-Agent': f'PaintingHeresy/{APP_VERSION}'})
        data = resp.json()
        return jsonify({
            'current_version': APP_VERSION,
            'changelog': data.get('changelog', [])
        })
    except Exception as e:
        return jsonify({
            'current_version': APP_VERSION,
            'changelog': [],
            'error': str(e)
        })

@app.route('/api/news', methods=['GET'])
def get_news():
    return jsonify(fetch_news())

# ── KILL TEAM DATA ────────────────────────────────────────────

import json as _json
import time as _time

KT_FACTIONS_FILE = os.path.join(BASE_DIR, 'ktdata_factions.json')
KT_KT_DIR        = os.path.join(BASE_DIR, 'ktdata_killteams')
KT_MEM_CACHE     = {}  # pamięć podręczna na czas sesji

def _kt_headers():
    return {'User-Agent': 'PaintingHeresy/1.0', 'Accept': 'application/json'}

def _kt_save_factions(data):
    try:
        with open(KT_FACTIONS_FILE, 'w', encoding='utf-8') as f:
            _json.dump({'ts': _time.time(), 'data': data}, f)
    except Exception:
        pass

def _kt_load_factions():
    try:
        if os.path.exists(KT_FACTIONS_FILE):
            with open(KT_FACTIONS_FILE, 'r', encoding='utf-8') as f:
                return _json.load(f)
    except Exception:
        pass
    return None

def _kt_save_killteam(killteamid, data):
    try:
        if not os.path.exists(KT_KT_DIR):
            os.makedirs(KT_KT_DIR)
        path = os.path.join(KT_KT_DIR, f'{killteamid}.json')
        with open(path, 'w', encoding='utf-8') as f:
            _json.dump({'ts': _time.time(), 'data': data}, f)
    except Exception:
        pass

def _kt_load_killteam(killteamid):
    try:
        path = os.path.join(KT_KT_DIR, f'{killteamid}.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return _json.load(f)
    except Exception:
        pass
    return None

KT_NEW_TEAMS_NOTIFICATION = []  # lista nowych kill teamów do pokazania

def _kt_check_update_in_background(cached_data):
    """Sprawdź w tle czy API ma nowe kill teamy"""
    def _check():
        global KT_NEW_TEAMS_NOTIFICATION
        try:
            resp = _requests_lib.get(
                'https://ktdash.app/api/factions?loadkts=1',
                timeout=10, headers=_kt_headers()
            )
            new_data = resp.json()
            if not isinstance(new_data, list):
                return

            # Zbuduj set starych killteamId
            old_ids = set()
            for f in cached_data:
                for kt in f.get('killteams', []):
                    kid = kt.get('killteamId') or kt.get('killteamid') or ''
                    if kid:
                        old_ids.add(kid)

            # Znajdź nowe
            new_teams = []
            for f in new_data:
                fname = f.get('factionName') or f.get('factionname') or ''
                for kt in f.get('killteams', []):
                    kid  = kt.get('killteamId') or kt.get('killteamid') or ''
                    kname = kt.get('killteamName') or kt.get('killteamname') or ''
                    if kid and kid not in old_ids:
                        new_teams.append({
                            'killteamId':   kid,
                            'killteamName': kname,
                            'factionName':  fname,
                        })

            if new_teams:
                _kt_save_factions(new_data)
                KT_MEM_CACHE['factions'] = new_data
                KT_NEW_TEAMS_NOTIFICATION = new_teams

        except Exception:
            pass
    threading.Thread(target=_check, daemon=True).start()

@app.route('/api/kt/new-teams', methods=['GET'])
def kt_new_teams():
    """Zwraca listę nowo wykrytych kill teamów"""
    return jsonify(KT_NEW_TEAMS_NOTIFICATION)

@app.route('/api/kt/new-teams/dismiss', methods=['POST'])
def kt_dismiss_new_teams():
    """Wyczyść powiadomienie"""
    global KT_NEW_TEAMS_NOTIFICATION
    KT_NEW_TEAMS_NOTIFICATION = []
    return jsonify({'ok': True})


@app.route('/api/kt/factions', methods=['GET'])
def kt_factions():
    # 1. Sprawdź pamięć sesji
    if 'factions' in KT_MEM_CACHE:
        return jsonify(KT_MEM_CACHE['factions'])

    # 2. Sprawdź lokalny plik cache
    cached = _kt_load_factions()
    if cached and isinstance(cached.get('data'), list):
        data  = cached['data']
        KT_MEM_CACHE['factions'] = data
        # Sprawdź aktualizacje w tle (bez blokowania)
        _kt_check_update_in_background(data)
        return jsonify(data)

    # 3. Pierwsze uruchomienie — pobierz z API
    try:
        resp = _requests_lib.get(
            'https://ktdash.app/api/factions?loadkts=1',
            timeout=15, headers=_kt_headers()
        )
        data = resp.json()
        if isinstance(data, list):
            _kt_save_factions(data)
            KT_MEM_CACHE['factions'] = data
            return jsonify(data)
    except Exception as e:
        pass

    return jsonify({'error': 'Could not load factions and no local cache found'}), 503

@app.route('/api/kt/killteam/<factionid>/<killteamid>', methods=['GET'])
def kt_killteam(factionid, killteamid):
    cache_key = f'kt_{killteamid}'

    # 1. Pamięć sesji
    if cache_key in KT_MEM_CACHE:
        return jsonify(KT_MEM_CACHE[cache_key])

    # 2. Lokalny plik
    cached = _kt_load_killteam(killteamid)
    if cached and isinstance(cached.get('data'), dict):
        KT_MEM_CACHE[cache_key] = cached['data']
        return jsonify(cached['data'])

    # 3. Pobierz z API i zapisz
    try:
        resp = _requests_lib.get(
            f'https://ktdash.app/api/killteams/{killteamid}',
            timeout=10, headers=_kt_headers()
        )
        if resp.status_code == 200 and 'application/json' in resp.headers.get('Content-Type', ''):
            data = resp.json()
            _kt_save_killteam(killteamid, data)
            KT_MEM_CACHE[cache_key] = data
            return jsonify(data)
    except Exception:
        pass

    return jsonify({'error': 'Could not fetch kill team data'}), 404

@app.route('/api/window/quit', methods=['POST'])
def window_quit():
    """Całkowicie zamknij aplikację"""
    threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/window/minimize', methods=['POST'])
def window_minimize():
    try:
        import webview
        for w in webview.windows:
            w.minimize()
    except Exception:
        pass
    return jsonify({'ok': True})

@app.route('/api/window/hide', methods=['POST'])
def window_hide():
    """Chowaj do tray (zamiast zamykać)"""
    try:
        import webview
        for w in webview.windows:
            w.hide()
    except Exception:
        pass
    return jsonify({'ok': True})


def kt_cache_status():
    """Informacja o stanie cache"""
    has_factions = os.path.exists(KT_FACTIONS_FILE)
    kt_count     = len(os.listdir(KT_KT_DIR)) if os.path.exists(KT_KT_DIR) else 0
    cached       = _kt_load_factions()
    ts           = cached.get('ts', 0) if cached else 0
    return jsonify({
        'has_factions_cache': has_factions,
        'killteams_cached':   kt_count,
        'cache_age_hours':    round((_time.time() - ts) / 3600, 1) if ts else None,
        'in_memory':          list(KT_MEM_CACHE.keys()),
    })



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

DATACARDS_DIR = os.path.join(BASE_DIR, 'datacards')

@app.route('/api/datacard/<optype_id>', methods=['GET'])
def get_datacard(optype_id):
    """Sprawdź czy istnieje obraz data cardu dla operatora"""
    if not re.match(r'^[A-Za-z0-9_\-]+$', optype_id):
        return jsonify({'exists': False})
    path = os.path.join(DATACARDS_DIR, f'{optype_id}.jpg')
    return jsonify({'exists': os.path.exists(path)})

@app.route('/datacards/<optype_id>.jpg', methods=['GET'])
def serve_datacard(optype_id):
    if not re.match(r'^[A-Za-z0-9_\-]+$', optype_id):
        return 'Not found', 404
    if not os.path.exists(DATACARDS_DIR):
        return 'Not found', 404
    return send_from_directory(DATACARDS_DIR, f'{optype_id}.jpg')


def upload_pdf():
    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR)
    files = request.files.getlist('files')
    saved = []
    for f in files:
        if f.filename.lower().endswith('.pdf'):
            safe = os.path.basename(f.filename)
            f.save(os.path.join(PDF_DIR, safe))
            saved.append(safe)
    return jsonify({'ok': True, 'saved': saved})

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

def make_tray_icon():
    """Generuje ikonę dla system tray — złote oko na ciemnym tle"""
    from PIL import Image, ImageDraw
    size = 64
    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d    = ImageDraw.Draw(img)
    # Tło
    d.ellipse([2, 2, size-2, size-2], fill=(14, 14, 26, 255))
    # Oko
    d.ellipse([8, 8, size-8, size-8], outline=(201, 168, 76, 255), width=3)
    # Źrenica
    d.ellipse([24, 20, 40, 44], fill=(201, 168, 76, 255))
    return img

def main():
    # Wycisz ostrzeżenie PyWebView o folderach tymczasowych
    try:
        import webview.platforms.winforms as _wf
        _orig_destroy = getattr(_wf, '_destroy_window', None)
        if _orig_destroy:
            def _patched_destroy(*a, **kw):
                try:
                    _orig_destroy(*a, **kw)
                except Exception:
                    pass
            _wf._destroy_window = _patched_destroy
    except Exception:
        pass

    # Wycisz MessageBox z Windows przez monkey-patch ctypes
    try:
        import ctypes
        _orig_msgbox = ctypes.windll.user32.MessageBoxW
        def _silent_msgbox(*a, **kw):
            # Automatycznie kliknij OK (return 1)
            return 1
        ctypes.windll.user32.MessageBoxW = _silent_msgbox
    except Exception:
        pass

    # Sprawdź czy PaintsReq.db istnieje
    if not os.path.exists(CITADEL_DB_PATH):
        import webview
        webview.create_window(
            'Painting Heresy — Error',
            html=f'''<body style="background:#0e0e1a;color:#c9a84c;font-family:sans-serif;
                     display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
                     <div style="text-align:center;padding:40px">
                     <h2 style="color:#c9a84c">⚠ Missing file</h2>
                     <p style="color:#a0a0b0">PaintsReq.db not found!<br>
                     Make sure it is in the same folder as the application:<br>
                     <code style="color:#7a7a96">{BASE_DIR}</code></p>
                     </div></body>''',
            width=500, height=250
        )
        webview.start()
        sys.exit(1)

    # Uruchom Flask w wątku w tle
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    import time
    time.sleep(0.8)

    import webview
    import pystray

    # Utwórz okno — frameless (bez systemowego paska tytułu)
    window = webview.create_window(
        title     = 'Painting Heresy',
        url       = 'http://127.0.0.1:5000',
        width     = 1400,
        height    = 900,
        min_size  = (1000, 600),
        resizable = True,
        frameless = True,
    )

    # ── Tray ikona ──────────────────────────────
    tray_icon = [None]

    def show_window(icon=None, item=None):
        window.show()
        window.restore()

    def quit_app(icon=None, item=None):
        if tray_icon[0]:
            tray_icon[0].stop()
        os._exit(0)

    def on_closing():
        """Zamiast zamykać — chowaj do tray"""
        window.hide()
        return False  # Blokuj domyślne zamknięcie

    def setup_tray():
        menu = pystray.Menu(
            pystray.MenuItem('Show Painting Heresy', show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', quit_app),
        )
        icon_img = make_tray_icon()
        icon = pystray.Icon(
            'PaintingHeresy',
            icon_img,
            'Painting Heresy',
            menu
        )
        tray_icon[0] = icon
        icon.run()

    # Podłącz obsługę zamykania
    window.events.closing += on_closing

    # Uruchom tray w osobnym wątku
    tray_thread = threading.Thread(target=setup_tray, daemon=True)
    tray_thread.start()

    webview.start()

    # Wyczyść foldery tymczasowe PyWebView po zamknięciu
    try:
        import tempfile
        import shutil
        import glob
        temp_dir = tempfile.gettempdir()
        for folder in glob.glob(os.path.join(temp_dir, '_MEI*')):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass

if __name__ == '__main__':
    main()
