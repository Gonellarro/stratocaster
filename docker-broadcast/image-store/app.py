import os
import uuid
import json
import datetime
import time
from flask import Flask, request, send_from_directory, render_template_string, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = '/app/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Estado global del lanzamiento (en memoria)
LAUNCH_STATE = {
    'estado': 'espera',        # 'espera', 'armando', 'cuenta_atras', 'lanzado'
    'tiempo_restante': 0,
    'timestamp_inicio': 0.0
}

# ------------------------------------------------------------------------------
# ENDPOINTS DE CONTROL DE LANZAMIENTO (API REST)
# ------------------------------------------------------------------------------

def update_countdown_state():
    """Calcula dinámicamente el tiempo restante de la cuenta atrás."""
    global LAUNCH_STATE
    if LAUNCH_STATE['estado'] == 'cuenta_atras':
        elapsed = time.time() - LAUNCH_STATE['timestamp_inicio']
        remaining = 10 - int(elapsed)
        if remaining <= 0:
            LAUNCH_STATE['estado'] = 'lanzado'
            LAUNCH_STATE['tiempo_restante'] = 0
        else:
            LAUNCH_STATE['tiempo_restante'] = remaining

@app.route('/control_lanzamiento', methods=['GET'])
def get_launch_status():
    update_countdown_state()
    return jsonify(LAUNCH_STATE)

@app.route('/control_lanzamiento', methods=['POST'])
def change_launch_status():
    global LAUNCH_STATE
    data = request.json or {}
    action = data.get('action')
    
    if action == 'armar':
        LAUNCH_STATE['estado'] = 'armando'
        LAUNCH_STATE['tiempo_restante'] = 0
        LAUNCH_STATE['timestamp_inicio'] = 0.0
    elif action == 'ok':
        # La sonda responde con su estado OK. Arrancamos la cuenta atrás real.
        LAUNCH_STATE['estado'] = 'cuenta_atras'
        LAUNCH_STATE['timestamp_inicio'] = time.time()
        LAUNCH_STATE['tiempo_restante'] = 10
    elif action == 'abortar' or action == 'reset':
        LAUNCH_STATE['estado'] = 'espera'
        LAUNCH_STATE['tiempo_restante'] = 0
        LAUNCH_STATE['timestamp_inicio'] = 0.0
        
    return jsonify(LAUNCH_STATE)

@app.route('/control_lanzamiento/ok', methods=['POST'])
def sonda_confirm_ok():
    """Endpoint directo para que el móvil de la sonda confirme que está listo para el lanzamiento."""
    global LAUNCH_STATE
    LAUNCH_STATE['estado'] = 'cuenta_atras'
    LAUNCH_STATE['timestamp_inicio'] = time.time()
    LAUNCH_STATE['tiempo_restante'] = 10
    return jsonify({'status': 'ok', 'message': 'Countdown started'})

# ------------------------------------------------------------------------------
# ENDPOINTS DE ARCHIVOS (IMÁGENES & UPLOADS)
# ------------------------------------------------------------------------------

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file:
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)
        
        texto = request.form.get('texto', '')
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        metadata = {
            'texto': texto,
            'timestamp': timestamp,
            'filename': unique_name
        }
        
        meta_name = f"{os.path.splitext(unique_name)[0]}.json"
        meta_path = os.path.join(app.config['UPLOAD_FOLDER'], meta_name)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        return unique_name, 200

@app.route('/images/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ------------------------------------------------------------------------------
# VISTAS WEB (INTERFACES HTML)
# ------------------------------------------------------------------------------

@app.route('/fotos')
def list_photos():
    fotos = []
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            name_without_ext = os.path.splitext(file)[0]
            meta_file = f"{name_without_ext}.json"
            meta_path = os.path.join(app.config['UPLOAD_FOLDER'], meta_file)
            
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        texto = data.get('texto', 'Sin descripción').strip()
                        # Sanitizar saltos de línea y comillas para evitar romper el JavaScript inline de la galería
                        texto = texto.replace('\n', ' ').replace('\r', ' ').replace("'", "&#39;").replace('"', '&quot;')
                        timestamp = data.get('timestamp', 'Fecha desconocida')
                except Exception:
                    texto = 'Error al leer descripción'
                    timestamp = 'Error al leer fecha'
            else:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file)
                mtime = os.path.getmtime(filepath)
                timestamp = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                texto = 'Sin descripción'
                
            fotos.append({
                'filename': file,
                'texto': texto,
                'timestamp': timestamp,
                'mtime': os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], file))
            })
            
    fotos.sort(key=lambda x: x['mtime'], reverse=True)
    
    html_template = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Galería de Capturas de Sonda</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #0d0e12;
                --card-bg: rgba(255, 255, 255, 0.03);
                --card-border: rgba(255, 255, 255, 0.08);
                --text-color: #e2e8f0;
                --text-muted: #94a3b8;
                --accent-color: #06b6d4;
                --accent-glow: rgba(6, 182, 212, 0.15);
            }
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                min-height: 100vh;
                padding: 2rem 1rem;
                background-image: radial-gradient(circle at 50% 0%, rgba(6, 182, 212, 0.08) 0%, transparent 50%);
            }
            .container { max-width: 1200px; margin: 0 auto; }
            header { text-align: center; margin-bottom: 3rem; }
            header h1 {
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #fff 0%, #a5f3fc 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
            }
            header p { color: var(--text-muted); font-size: 1.1rem; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 2rem; }
            .card {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                backdrop-filter: blur(12px);
                transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.3s, box-shadow 0.3s;
            }
            .card:hover {
                transform: translateY(-5px);
                border-color: var(--accent-color);
                box-shadow: 0 10px 30px var(--accent-glow);
            }
            .image-container {
                width: 100%;
                height: 240px;
                overflow: hidden;
                background-color: #1a1c23;
                position: relative;
                cursor: pointer;
            }
            .image-container img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                transition: transform 0.5s ease;
            }
            .card:hover .image-container img { transform: scale(1.05); }
            .content { padding: 1.5rem; display: flex; flex-direction: column; flex-grow: 1; }
            .time-badge {
                align-self: flex-start;
                font-size: 0.75rem;
                font-weight: 600;
                color: var(--accent-color);
                background: rgba(6, 182, 212, 0.1);
                padding: 0.25rem 0.75rem;
                border-radius: 99px;
                margin-bottom: 0.75rem;
            }
            .description { font-size: 0.95rem; line-height: 1.5; color: var(--text-color); }
            .lightbox {
                display: none;
                position: fixed;
                z-index: 999;
                top: 0; left: 0; width: 100%; height: 100%;
                background-color: rgba(10, 11, 15, 0.95);
                backdrop-filter: blur(8px);
                justify-content: center;
                align-items: center;
                padding: 2rem;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            .lightbox.active { display: flex; opacity: 1; }
            .lightbox-content { max-width: 90%; max-height: 90vh; position: relative; }
            .lightbox-content img {
                max-width: 100%; max-height: 80vh; border-radius: 12px;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .lightbox-close {
                position: absolute; top: -40px; right: 0; color: #fff;
                font-size: 2rem; cursor: pointer; background: none; border: none;
            }
            .lightbox-caption { color: var(--text-color); margin-top: 1rem; text-align: center; font-size: 1.1rem; }
            .back-btn {
                display: inline-block;
                margin-bottom: 2rem;
                color: var(--accent-color);
                text-decoration: none;
                font-weight: 600;
                transition: color 0.2s;
            }
            .back-btn:hover { color: #22d3ee; }
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/control" class="back-btn">← Volver al Panel de Control</a>
            <header>
                <h1>Galería de Capturas de la Sonda</h1>
                <p>Historial de imágenes procesadas e inferencia local de la IA en tiempo real</p>
            </header>

            {% if fotos %}
            <div class="grid">
                {% for foto in fotos %}
                <div class="card">
                    <div class="image-container" onclick="openLightbox('/images/{{ foto.filename }}', '{{ foto.texto }}')">
                        <img src="/images/{{ foto.filename }}" alt="Captura de Sonda">
                    </div>
                    <div class="content">
                        <span class="time-badge">{{ foto.timestamp }}</span>
                        <p class="description">{{ foto.texto }}</p>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div style="text-align: center; padding: 4rem; color: var(--text-muted);">
                <p>Aún no se han recibido imágenes. Las capturas aparecerán aquí a medida que se suban.</p>
            </div>
            {% endif %}
        </div>

        <div id="lightbox" class="lightbox" onclick="closeLightbox()">
            <div class="lightbox-content" onclick="event.stopPropagation()">
                <button class="lightbox-close" onclick="closeLightbox()">&times;</button>
                <img id="lightbox-img" src="" alt="Ampliada">
                <p id="lightbox-txt" class="lightbox-caption"></p>
            </div>
        </div>

        <script>
            function openLightbox(src, text) {
                const lightbox = document.getElementById('lightbox');
                const img = document.getElementById('lightbox-img');
                const txt = document.getElementById('lightbox-txt');
                img.src = src;
                txt.textContent = text;
                lightbox.classList.add('active');
            }
            function closeLightbox() { document.getElementById('lightbox').classList.remove('active'); }
            document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLightbox(); });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, fotos=fotos)

@app.route('/images/last')
def last_image():
    try:
        files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        if not files:
            return send_from_directory('static', 'no-image.png') if os.path.exists('static/no-image.png') else ('No images uploaded yet', 404)
        files.sort(key=lambda x: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], x)), reverse=True)
        return send_from_directory(app.config['UPLOAD_FOLDER'], files[0])
    except Exception as e:
        return str(e), 500

@app.route('/control')
def control_panel():
    html_template = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sonda Meteorológica - Consola de Control</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <!-- MQTT y Leaflet -->
        <script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            :root {
                --bg-color: #0b0c10;
                --sidebar-bg: #0d0f14;
                --card-bg: rgba(255, 255, 255, 0.02);
                --card-border: rgba(255, 255, 255, 0.07);
                --text-color: #e2e8f0;
                --text-muted: #64748b;
                --red-accent: #ef4444;
                --red-glow: rgba(239, 68, 68, 0.15);
                --green-accent: #10b981;
                --green-glow: rgba(16, 185, 129, 0.15);
                --yellow-accent: #f59e0b;
                --yellow-glow: rgba(245, 158, 11, 0.15);
                --cyan-accent: #06b6d4;
                --cyan-glow: rgba(6, 182, 212, 0.2);
            }
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                min-height: 100vh;
                display: flex;
            }

            /* Lateral Sidebar */
            .sidebar {
                width: 280px;
                background-color: var(--sidebar-bg);
                border-right: 1px solid var(--card-border);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                padding: 1.5rem;
                position: fixed;
                height: 100vh;
                left: 0; top: 0;
            }
            .sidebar-logo {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 2rem;
            }
            .sidebar-logo-icon {
                width: 32px;
                height: 32px;
                background: linear-gradient(135deg, var(--cyan-accent), #0284c7);
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                color: #000;
            }
            .sidebar-title h2 { font-size: 1.1rem; font-weight: 700; letter-spacing: 0.05em; }
            .sidebar-title p { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }
            
            .menu-list { list-style: none; display: flex; flex-direction: column; gap: 0.5rem; }
            .menu-item a {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.75rem 1rem;
                color: var(--text-color);
                text-decoration: none;
                font-size: 0.95rem;
                border-radius: 8px;
                transition: background 0.2s;
            }
            .menu-item.active a, .menu-item a:hover {
                background: rgba(255,255,255,0.03);
                color: var(--cyan-accent);
                font-weight: 600;
            }
            .active-mission-card {
                background: rgba(255,255,255,0.01);
                border: 1px solid var(--card-border);
                border-radius: 12px;
                padding: 1rem;
                margin-top: auto;
            }
            .active-mission-title { font-size: 0.7rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.25rem; }
            .active-mission-id { font-size: 0.9rem; font-weight: 700; color: var(--cyan-accent); }
            .active-mission-detail { font-size: 0.8rem; margin-top: 0.5rem; color: var(--text-color); }
            .btn-new-mission {
                width: 100%;
                background: rgba(6, 182, 212, 0.1);
                border: 1px dashed var(--cyan-accent);
                color: var(--cyan-accent);
                padding: 0.5rem;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
                margin-top: 0.75rem;
                cursor: pointer;
                transition: background 0.2s;
            }
            .btn-new-mission:hover { background: rgba(6, 182, 212, 0.2); }

            /* Main Workspace Area */
            .main-content {
                margin-left: 280px;
                flex-grow: 1;
                padding: 2rem;
                overflow-y: auto;
                max-width: calc(100% - 280px);
            }

            /* Phase Progress Selector */
            .phase-bar {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 1rem;
                margin-bottom: 2rem;
            }
            .phase-card {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 12px;
                padding: 1rem;
                display: flex;
                align-items: center;
                gap: 0.75rem;
                position: relative;
                transition: all 0.3s;
                opacity: 0.5;
            }
            .phase-card.active {
                opacity: 1;
                border-color: var(--cyan-accent);
                box-shadow: 0 0 15px rgba(6, 182, 212, 0.1);
                background: rgba(6, 182, 212, 0.02);
            }
            .phase-icon {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                background: rgba(255,255,255,0.03);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.1rem;
            }
            .phase-card.active .phase-icon {
                background: var(--cyan-accent);
                color: #000;
                box-shadow: 0 0 10px var(--cyan-glow);
            }
            .phase-num { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; }
            .phase-title { font-size: 0.9rem; font-weight: 700; }
            .phase-subtitle { font-size: 0.75rem; color: var(--text-muted); }

            /* Dashboard Top Cards Grid */
            .top-cards-grid {
                display: grid;
                grid-template-columns: 340px 1.2fr 1fr 1.1fr;
                gap: 1.5rem;
                margin-bottom: 2rem;
            }
            @media (max-width: 1200px) {
                .top-cards-grid { grid-template-columns: 1fr 1fr; }
            }
            @media (max-width: 768px) {
                .top-cards-grid { grid-template-columns: 1fr; }
            }

            .panel {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                padding: 1.5rem;
                backdrop-filter: blur(12px);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            .panel-title {
                font-size: 0.85rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-muted);
                margin-bottom: 1rem;
                border-bottom: 1px solid var(--card-border);
                padding-bottom: 0.5rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            /* Checklist pre-flight */
            .checklist-list { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }
            .checklist-item {
                display: flex;
                align-items: center;
                gap: 0.6rem;
                padding: 0.4rem 0;
                font-size: 0.85rem;
                transition: all 0.3s ease;
            }
            .checklist-item.testing {
                border: 1px solid var(--cyan-accent) !important;
                background: rgba(6, 182, 212, 0.08) !important;
                box-shadow: 0 0 10px var(--cyan-glow);
                border-radius: 8px;
                padding-left: 0.4rem;
                padding-right: 0.4rem;
            }
            .checklist-item.testing .checklist-status {
                border-color: var(--cyan-accent);
                background: rgba(6, 182, 212, 0.08);
                color: transparent;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .checklist-item.testing .checklist-status::after {
                content: "...";
                color: var(--cyan-accent);
                font-family: monospace;
                font-size: 1.1rem;
                font-weight: bold;
                letter-spacing: -1.5px;
                animation: dotsPulse 1.2s infinite steps(4);
                line-height: 1;
                margin-top: -6px;
                margin-left: -1px;
            }
            @keyframes dotsPulse {
                0% { content: ""; }
                33% { content: "."; }
                66% { content: ".."; }
                100% { content: "..."; }
            }
            .checklist-status {
                width: 16px; height: 16px;
                border-radius: 4px;
                border: 1px solid var(--card-border);
                display: flex; align-items: center; justify-content: center;
                font-size: 0.7rem; color: transparent;
                transition: all 0.2s;
            }
            .checklist-item.ok .checklist-status {
                background-color: var(--green-accent);
                border-color: var(--green-accent);
                color: #fff;
                box-shadow: 0 0 6px var(--green-glow);
            }
            .checklist-item.warn .checklist-status {
                background-color: var(--yellow-accent);
                border-color: var(--yellow-accent);
                color: #fff;
                box-shadow: 0 0 6px var(--yellow-glow);
            }
            .checklist-item.ko .checklist-status {
                background-color: var(--red-accent);
                border-color: var(--red-accent);
                color: #fff;
                box-shadow: 0 0 6px var(--red-glow);
            }
            .checklist-item.ko .checklist-status::after { content: "✗"; color: #fff; }
            .checklist-item.ok .checklist-status::after { content: "✓"; color: #fff; }
            .checklist-item.warn .checklist-status::after { content: "⚠"; color: #000; font-weight: bold; }
            .checklist-label { flex-grow: 1; }
            .checklist-val { font-family: monospace; color: var(--text-muted); font-size: 0.8rem; }
            
            .btn {
                font-family: 'Outfit', sans-serif;
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--card-border);
                color: var(--text-color);
                padding: 0.75rem 1rem;
                border-radius: 8px;
                font-size: 0.85rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex; align-items: center; justify-content: center; gap: 0.5rem;
            }
            .btn:hover:not(:disabled) { background: rgba(255,255,255,0.08); border-color: var(--text-color); }
            .btn:active:not(:disabled) { transform: scale(0.98); }
            .btn:disabled { opacity: 0.3; cursor: not-allowed; }
            .btn-accent { background: var(--cyan-accent); color: #000; border: none; }
            .btn-accent:hover:not(:disabled) { background: #22d3ee; box-shadow: 0 0 10px var(--cyan-glow); }
            .btn-red { background: var(--red-accent); color: #fff; border: none; font-size: 1rem; font-weight: 700; width: 100%; box-shadow: 0 0 15px rgba(239, 68, 68, 0.2); }
            .btn-red:hover:not(:disabled) { background: #f87171; box-shadow: 0 0 20px rgba(239, 68, 68, 0.4); }

            /* Countdown Display */
            .countdown-area { text-align: center; display: flex; flex-direction: column; justify-content: center; flex-grow: 1; min-height: 100px; }
            .countdown-value { font-size: 3rem; font-weight: 700; font-family: monospace; color: var(--cyan-accent); text-shadow: 0 0 15px rgba(6, 182, 212, 0.3); }
            .countdown-value.active { color: var(--red-accent); text-shadow: 0 0 20px rgba(239, 68, 68, 0.4); animation: scalePulse 1s infinite alternate; }

            /* General Status */
            .status-large { font-size: 3rem; font-weight: 700; text-align: center; margin-bottom: 0.5rem; }
            .status-ok { color: var(--green-accent); text-shadow: 0 0 15px rgba(16, 185, 129, 0.3); }
            .status-warn { color: var(--yellow-accent); text-shadow: 0 0 15px rgba(245, 158, 11, 0.3); }
            .status-alarm { color: var(--red-accent); text-shadow: 0 0 15px rgba(239, 68, 68, 0.3); }
            .status-subtext { font-size: 0.8rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 0.3rem; margin-top: auto; }
            .status-subtext div { display: flex; justify-content: space-between; }

            /* Link Indicators */
            .links-list { display: flex; flex-direction: column; gap: 0.75rem; flex-grow: 1; justify-content: center; }
            .link-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; }
            .link-badge { padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); color: var(--text-muted); }
            .link-badge.connected { color: var(--green-accent); background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.2); }
            .link-badge.disconnected { color: var(--red-accent); background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.2); }

            /* In-Flight Row Layout */
            .flight-grid {
                display: grid;
                grid-template-columns: 2.1fr 1fr 1.6fr;
                gap: 1.5rem;
                margin-bottom: 2rem;
            }
            @media (max-width: 1200px) {
                .flight-grid { grid-template-columns: 1fr; }
            }

            /* Telemetry Compare Table */
            .telem-table-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 1rem; }
            .telem-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: left; }
            .telem-table th { color: var(--text-muted); font-weight: 600; padding: 0.5rem 0.3rem; border-bottom: 1px solid var(--card-border); }
            .telem-table td { padding: 0.45rem 0.3rem; border-bottom: 1px solid rgba(255,255,255,0.02); }
            .telem-table tr:last-child td { border-bottom: none; }
            .telem-icon { color: var(--cyan-accent); font-weight: bold; width: 20px; }

            /* Telemetry 6 mini-cards block */
            .telemetry-mini-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-top: 0.5rem; }
            .telem-mini-card { background: rgba(255,255,255,0.01); border: 1px solid var(--card-border); border-radius: 8px; padding: 0.6rem; text-align: center; }
            .telem-mini-label { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.2rem; }
            .telem-mini-value { font-size: 0.95rem; font-weight: 700; font-family: monospace; color: var(--text-color); }

            /* Camera & Media Card */
            .camera-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
            .camera-tabs { display: flex; gap: 0.3rem; background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); padding: 0.2rem; border-radius: 6px; }
            .camera-tab { background: none; border: none; color: var(--text-muted); font-family: inherit; font-size: 0.75rem; font-weight: 600; padding: 0.3rem 0.75rem; border-radius: 4px; cursor: pointer; transition: all 0.2s; }
            .camera-tab.active { background: var(--cyan-accent); color: #000; }
            .camera-viewer { width: 100%; height: 210px; border-radius: 8px; overflow: hidden; background: #050608; border: 1px solid var(--card-border); position: relative; }
            .camera-viewer iframe { width: 100%; height: 100%; border: none; display: none; }
            .camera-viewer img { width: 100%; height: 100%; object-fit: contain; display: block; }
            .camera-viewer.video-mode iframe { display: block; }
            .camera-viewer.video-mode img { display: none; }
            .camera-timestamp { font-size: 0.7rem; color: var(--text-muted); text-align: right; margin-top: 0.4rem; }
            .camera-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.75rem; }

            /* Map panel */
            .map-outer { position: relative; width: 100%; height: 285px; border-radius: 12px; overflow: hidden; border: 1px solid var(--card-border); }
            #map-container { width: 100%; height: 100%; background-color: #0d0f14; }
            .map-legend { position: absolute; bottom: 10px; left: 10px; background: rgba(11, 12, 16, 0.9); border: 1px solid var(--card-border); padding: 0.4rem 0.6rem; border-radius: 6px; font-size: 0.65rem; z-index: 1000; pointer-events: none; display: flex; flex-direction: column; gap: 0.2rem; }
            .map-legend-item { display: flex; align-items: center; gap: 0.4rem; }
            .legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

            /* Bottom Row Layout (Meshtastic, Logs, Actions) */
            .bottom-grid {
                display: grid;
                grid-template-columns: 1fr 2fr 1fr;
                gap: 1.5rem;
                margin-top: 0.5rem;
            }
            @media (max-width: 1024px) {
                .bottom-grid { grid-template-columns: 1fr; }
            }

            /* Meshtastic list */
            .mesh-list { display: flex; flex-direction: column; gap: 0.5rem; flex-grow: 1; justify-content: center; }
            .mesh-node { display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; padding: 0.35rem 0; border-bottom: 1px solid rgba(255,255,255,0.02); }
            .mesh-rssi { font-weight: bold; font-family: monospace; }
            .mesh-rssi.good { color: var(--green-accent); }
            .mesh-rssi.mid { color: var(--yellow-accent); }
            .mesh-rssi.bad { color: var(--red-accent); }

            /* Event log console */
            .log-console {
                background: #050608;
                border: 1px solid var(--card-border);
                border-radius: 8px;
                padding: 0.75rem;
                font-family: monospace;
                font-size: 0.75rem;
                color: #38bdf8;
                height: 140px;
                overflow-y: auto;
                flex-grow: 1;
                box-shadow: inset 0 0 10px rgba(0,0,0,0.8);
            }
            .log-line { margin-bottom: 0.3rem; line-height: 1.3; }
            .log-line .time { color: var(--text-muted); }
            .log-line .tag { color: var(--cyan-accent); font-weight: bold; }
            .log-line .tag.warn { color: var(--yellow-accent); }
            .log-line .tag.err { color: var(--red-accent); }
            .log-line .tag.ok { color: var(--green-accent); }

            /* Quick actions panel */
            .quick-actions-list { display: flex; flex-direction: column; gap: 0.6rem; flex-grow: 1; justify-content: center; }
            .btn-quick { width: 100%; font-size: 0.8rem; padding: 0.6rem 0.85rem; border-radius: 6px; }
            
            /* Scrollbar styling */
            ::-webkit-scrollbar { width: 6px; height: 6px; }
            ::-webkit-scrollbar-track { background: transparent; }
            ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 99px; }
            ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
        </style>
    </head>
    <body>
        <!-- 1. Left Sidebar -->
        <div class="sidebar">
            <div>
                <div class="sidebar-logo">
                    <div class="sidebar-logo-icon">🎈</div>
                    <div class="sidebar-title">
                        <h2>Sonda Meteorológica</h2>
                        <p>Dashboard de Control</p>
                    </div>
                </div>
                <ul class="menu-list">
                    <li class="menu-item active"><a href="#">📊 Dashboard</a></li>
                    <li class="menu-item"><a href="/fotos">🖼️ Galería Fotos</a></li>
                </ul>
            </div>
            
            <div class="active-mission-card">
                <div class="active-mission-title">Misión Activa</div>
                <div id="mission-id-card" class="active-mission-id">--</div>
                <div class="active-mission-detail">
                    <div>Inicio: <span id="mission-start-card">--</span></div>
                    <div>Estado: <span id="mission-state-card">En espera</span></div>
                </div>
                <button class="btn-new-mission" onclick="startNewMission()">🆕 NUEVA MISIÓN</button>
            </div>
        </div>

        <!-- 2. Main Workspace -->
        <div class="main-content">
            <!-- Header con Barra de Fases y Estado General -->
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1.5rem; margin-bottom: 2rem;">
                <div class="phase-bar" style="flex-grow: 1; margin-bottom: 0;">
                    <div id="phase-1" class="phase-card active">
                        <div class="phase-icon">📋</div>
                        <div>
                            <div class="phase-num">Fase 1</div>
                            <div class="phase-title">PRE-DESPEGUE</div>
                            <div class="phase-subtitle">Check de sistemas</div>
                        </div>
                    </div>
                    <div id="phase-2" class="phase-card">
                        <div class="phase-icon">🚀</div>
                        <div>
                            <div class="phase-num">Fase 2</div>
                            <div class="phase-title">DESPEGUE</div>
                            <div class="phase-subtitle">Cuenta atrás</div>
                        </div>
                    </div>
                    <div id="phase-3" class="phase-card">
                        <div class="phase-icon">⛅</div>
                        <div>
                            <div class="phase-num">Fase 3</div>
                            <div class="phase-title">EN VUELO</div>
                            <div class="phase-subtitle">Telemetría e IA</div>
                        </div>
                    </div>
                    <div id="phase-4" class="phase-card">
                        <div class="phase-icon">🪂</div>
                        <div>
                            <div class="phase-num">Fase 4</div>
                            <div class="phase-title">ATERRIZAJE</div>
                            <div class="phase-subtitle">Rescate / GPS</div>
                        </div>
                    </div>
                </div>

                <div class="panel" style="width: 250px; padding: 1rem; text-align: center; display: flex; flex-direction: row; align-items: center; gap: 1rem; height: 75px;">
                    <div style="flex-grow: 1; text-align: left;">
                        <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; font-weight: bold;">Tiempo de Misión</div>
                        <div id="mission-time" style="font-size: 1.4rem; font-weight: 700; font-family: monospace;">00:00:00</div>
                    </div>
                    <div style="border-left: 1px solid var(--card-border); height: 100%; padding-left: 1rem; text-align: right;">
                        <div style="font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; font-weight: bold;">Satélites</div>
                        <div id="header-gps-sats" style="font-size: 1.4rem; font-weight: 700; color: var(--cyan-accent);">0</div>
                    </div>
                </div>
            </div>

            <!-- Pre-Flight Panel Row -->
            <div class="top-cards-grid">
                <!-- Card 1: Checklist de sistemas -->
                <div class="panel">
                    <div class="panel-title">Check de sistemas</div>
                    <div class="checklist-list">
                        <div id="chk-movil" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">Móvil (Android)</div>
                            <div id="chk-movil-val" class="checklist-val">--</div>
                        </div>
                        <div id="chk-lora" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">ESP32 LoRa (Telemetría)</div>
                            <div id="chk-lora-val" class="checklist-val">--</div>
                        </div>
                        <div id="chk-meshtastic" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">ESP32 LoRa (Meshtastic)</div>
                            <div id="chk-meshtastic-val" class="checklist-val">Moc</div>
                        </div>
                        <div id="chk-foto" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">Cámara (Foto e IA)</div>
                            <div id="chk-foto-val" class="checklist-val">Pendiente</div>
                        </div>
                        <div id="chk-video" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">Cámara (Vídeo directo)</div>
                            <div id="chk-video-val" class="checklist-val">Pendiente</div>
                        </div>
                        <div id="chk-battery" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">Batería Móvil (>50%)</div>
                            <div id="chk-battery-val" class="checklist-val">--</div>
                        </div>
                        <div id="chk-sensors" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">Sensores Térmicos</div>
                            <div id="chk-sensors-val" class="checklist-val">--</div>
                        </div>
                        <div id="chk-gps" class="checklist-item">
                            <div class="checklist-status"></div>
                            <div class="checklist-label">GPS Fijo (Precisión <= 10m)</div>
                            <div id="chk-gps-val" class="checklist-val">Sin Enlace</div>
                        </div>
                    </div>
                    <button id="btn-test-systems" class="btn btn-accent" style="width: 100%; margin-top: auto;" onclick="runSelfTest()">🤖 PROBAR SISTEMAS</button>
                </div>

                <!-- Card 2: Cuenta atrás -->
                <div class="panel">
                    <div class="panel-title">Listo para el despegue</div>
                    <div class="countdown-area">
                        <div id="countdown-clock" class="countdown-value">00:00:10</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.5rem; text-transform: uppercase;">Cuenta atrás de ignición</div>
                    </div>
                    <button id="btn-arm" class="btn btn-accent btn-red" style="width: 100%;" onclick="armLaunch()" disabled>🚀 INICIAR CUENTA ATRÁS</button>
                </div>

                <!-- Card 3: Estado General -->
                <div class="panel">
                    <div class="panel-title">Estado General</div>
                    <div>
                        <div id="sys-status-large" class="status-large status-ok">OK</div>
                    </div>
                    <div class="status-subtext">
                        <div><span>Señal LoRa:</span> <span id="sys-lora-signal">-- dBm</span></div>
                        <div><span>Satélites GPS:</span> <span id="sys-gps-sats">--</span></div>
                        <div><span>Último Ping:</span> <span id="sys-last-ping">--</span></div>
                    </div>
                </div>

                <!-- Card 4: Enlaces -->
                <div class="panel">
                    <div class="panel-title">Enlaces</div>
                    <div class="links-list">
                        <div class="link-row">
                            <span>Sonda Móvil (4G)</span>
                            <span id="link-movil" class="link-badge disconnected">Desconectado</span>
                        </div>
                        <div class="link-row">
                            <span>ESP32 LoRa (Telemetría)</span>
                            <span id="link-lora" class="link-badge disconnected">Desconectado</span>
                        </div>
                        <div class="link-row">
                            <span>ESP32 LoRa (Meshtastic)</span>
                            <span id="link-meshtastic" class="link-badge disconnected">Desconectado</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Row 2: In-Flight Real-Time Display (Telemetry Table, Camera Feed, Map) -->
            <div class="flight-grid">
                <!-- Card 1: Telemetría en tiempo real comparativa y mini-cards -->
                <div class="panel" style="justify-content: flex-start; gap: 1rem;">
                    <div class="panel-title">Telemetría en tiempo real</div>
                    <div class="telem-table-container">
                        <table class="telem-table">
                            <thead>
                                <tr>
                                    <th>Sensor</th>
                                    <th>📱 Sonda (Móvil)</th>
                                    <th>📻 Sonda (LoRa)</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><span class="telem-icon">🛰️</span> Satélites</td>
                                    <td id="td-m-sats">--</td>
                                    <td id="td-l-sats">--</td>
                                </tr>
                                <tr>
                                    <td><span class="telem-icon">⛰️</span> Altitud</td>
                                    <td id="td-m-alt">--</td>
                                    <td id="td-l-alt">--</td>
                                </tr>
                                <tr>
                                    <td><span class="telem-icon">📍</span> Latitud</td>
                                    <td id="td-m-lat">--</td>
                                    <td id="td-l-lat">--</td>
                                </tr>
                                <tr>
                                    <td><span class="telem-icon">📍</span> Longitud</td>
                                    <td id="td-m-lng">--</td>
                                    <td id="td-l-lng">--</td>
                                </tr>
                                <tr>
                                    <td><span class="telem-icon">⚡</span> Velocidad</td>
                                    <td id="td-m-spd">--</td>
                                    <td id="td-l-spd">--</td>
                                </tr>
                                <tr>
                                    <td><span class="telem-icon">🧭</span> Rumbo</td>
                                    <td id="td-m-crs">--</td>
                                    <td id="td-l-crs">--</td>
                                </tr>
                                <tr>
                                    <td><span class="telem-icon">🔋</span> Batería / Temp.</td>
                                    <td id="td-m-bat">--</td>
                                    <td id="td-l-bat">--</td>
                                </tr>
                            </tbody>
                        </table>

                        <div class="telemetry-mini-grid">
                            <div class="telem-mini-card">
                                <div class="telem-mini-label">Altitud (Mejor)</div>
                                <div id="mini-alt" class="telem-mini-value">-- m</div>
                            </div>
                            <div class="telem-mini-card">
                                <div class="telem-mini-label">Velocidad</div>
                                <div id="mini-spd" class="telem-mini-value">-- km/h</div>
                            </div>
                            <div class="telem-mini-card">
                                <div class="telem-mini-label">Rumbo</div>
                                <div id="mini-crs" class="telem-mini-value">--</div>
                            </div>
                            <div class="telem-mini-card">
                                <div class="telem-mini-label">Temperatura</div>
                                <div id="mini-temp" class="telem-mini-value">-- °C</div>
                            </div>
                            <div class="telem-mini-card">
                                <div class="telem-mini-label">Batería</div>
                                <div id="mini-bat" class="telem-mini-value">--%</div>
                            </div>
                            <div class="telem-mini-card">
                                <div class="telem-mini-label">GPS Prec.</div>
                                <div id="mini-gps" class="telem-mini-value">--</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Card 2: Cámara y Vídeo -->
                <div class="panel">
                    <div class="camera-header">
                        <span class="panel-title" style="margin-bottom: 0; border: none; padding: 0;">CÁMARA DE VUELO</span>
                        <div class="camera-tabs">
                            <button id="tab-foto" class="camera-tab active" onclick="switchCameraTab('foto')">FOTO</button>
                            <button id="tab-video" class="camera-tab" onclick="switchCameraTab('video')">VÍDEO</button>
                        </div>
                    </div>
                    <div id="camera-frame" class="camera-viewer">
                        <!-- El stream HLS de MediaMTX o fallback de VDO.ninja -->
                        <iframe id="video-stream" src="" allow="autoplay; camera; microphone"></iframe>
                        <!-- Última foto capturada por la IA -->
                        <img id="photo-feed" src="/images/last" alt="Alimentación de Cámara" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 fill=%22%231a1c23%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%2364748b%22 font-family=%22Outfit%22 font-size=%2210%22>Esperando captura...</text></svg>';">
                    </div>
                    <div id="photo-time" class="camera-timestamp">Último evento de cámara: --</div>
                    <div class="camera-actions">
                        <button class="btn btn-quick" onclick="sendCommand('test_photo')">📸 TOMAR FOTO</button>
                        <button id="btn-stream-switch" class="btn btn-quick btn-accent" onclick="toggleStreamCmd()">📹 INICIAR VÍDEO</button>
                    </div>
                </div>

                <!-- Card 3: Mapa interactivo -->
                <div class="panel" style="justify-content: flex-start; gap: 0.5rem;">
                    <div class="panel-title" style="margin-bottom: 0.5rem;">Posición en Mapa</div>
                    <div class="map-outer">
                        <div id="map-container"></div>
                        <div class="map-legend">
                            <div class="map-legend-item"><span class="legend-dot" style="background: #06b6d4;"></span> Sonda Móvil (4G)</div>
                            <div class="map-legend-item"><span class="legend-dot" style="background: #ef4444;"></span> Sonda LoRa (Radio)</div>
                            <div class="map-legend-item"><span class="legend-dot" style="background: #f59e0b;"></span> Meshtastic</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Bottom Row: Meshtastic, Event Log, Quick Actions -->
            <div class="bottom-grid">
                <!-- Card Meshtastic nodes -->
                <div class="panel">
                    <div class="panel-title">Meshtastic (LoRa)</div>
                    <div class="mesh-list">
                        <div class="mesh-node">
                            <span>Sonda (Nodo Principal)</span>
                            <span id="mesh-node-1" class="mesh-rssi good">-80 dBm</span>
                        </div>
                        <div class="mesh-node">
                            <span>Nodo Seguimiento 2</span>
                            <span id="mesh-node-2" class="mesh-rssi mid">-92 dBm</span>
                        </div>
                        <div class="mesh-node">
                            <span>Nodo Base 3</span>
                            <span id="mesh-node-3" class="mesh-rssi bad">-98 dBm</span>
                        </div>
                    </div>
                    <button class="btn btn-quick" style="margin-top: 0.5rem;" onclick="logMessage('info', 'Meshtastic', 'Abriendo detalles de red mallada...')">VER RED COMPLETA</button>
                </div>

                <!-- Card Registro de eventos -->
                <div class="panel" style="flex-grow: 1;">
                    <div class="panel-title">Registro de Eventos</div>
                    <div id="log-display" class="log-console">
                        <div class="log-line"><span class="time">16:58:10</span> <span class="tag ok">[SISTEMA]</span> Servidor Flask arrancado correctamente en puerto 5000.</div>
                        <div class="log-line"><span class="time">16:58:11</span> <span class="tag ok">[MQTT]</span> Escuchando topics: sonda/status, sonda/camera, gps/data, sonda/meshtastic.</div>
                    </div>
                </div>

                <!-- Card Acciones rápidas -->
                <div class="panel">
                    <div class="panel-title">Acciones rápidas</div>
                    <div class="quick-actions-list">
                        <button class="btn btn-quick btn-outline-red" style="border-color: var(--yellow-accent); color: var(--yellow-accent);" onclick="triggerBuzzer()">🔊 ACTIVAR BALIZA SONORA</button>
                        <button class="btn btn-quick btn-outline-red" onclick="abortLaunch()">🚨 ABORTAR LANZAMIENTO</button>
                        <button class="btn btn-quick" onclick="finalizeMission()">🪂 FINALIZAR MISIÓN</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Dashboard JavaScript Client Logic -->
        <script>
            let client = null;
            let lastSondaPing = 0;
            let lastLoraPing = 0;
            let lastMeshPing = 0;
            let streamActive = false;
            let isTesting = false;
            let currentPhase = 1;
            
            // Checklist local status variables
            let checks = {
                movil: false,
                lora_telemetria: false,
                lora_meshtastic: true, // Meshtastic mock / por ahora siempre true
                camera_foto: false,
                camera_video: false,
                battery: false,
                sensors: false,
                gps: false,
                audio: false
            };

            // Secuenciador de pruebas pre-vuelo
            let currentStepIndex = -1;
            let currentRetry = 0;
            let stepTimeoutTimer = null;
            let isSequenceRunning = false;

            // Estructura de Misión
            let mission = {
                id: 'MISIÓN_' + new Date().toISOString().slice(0,10).replace(/-/g, '_') + '_001',
                start: '--',
                state: 'espera',
                startTimestamp: 0
            };

            document.getElementById('mission-id-card').textContent = mission.id;

            // 1. Inicialización del Mapa Leaflet
            let map = L.map('map-container').setView([41.12345, 1.98765], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19
            }).addTo(map);

            // Capa Satélite
            let satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
                attribution: 'Tiles &copy; Esri'
            });

            let baseLayers = {
                "Mapa": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
                "Satélite": satelliteLayer
            };
            L.control.layers(baseLayers).addTo(map);

            // Marcadores neón y rutas
            let markers = {
                movil: L.circleMarker([41.12345, 1.98765], { color: '#06b6d4', fillColor: '#06b6d4', fillOpacity: 0.8, radius: 8 }).addTo(map),
                lora: L.circleMarker([41.12345, 1.98765], { color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.8, radius: 8 }).addTo(map),
                mesh: L.circleMarker([41.12345, 1.98765], { color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.8, radius: 8 }).addTo(map)
            };

            let paths = {
                movil: L.polyline([], { color: '#06b6d4', weight: 3 }).addTo(map),
                lora: L.polyline([], { color: '#ef4444', weight: 3, dashArray: '5, 5' }).addTo(map),
                mesh: L.polyline([], { color: '#f59e0b', weight: 3, dashArray: '2, 5' }).addTo(map)
            };

            // 2. Conexión MQTT
            const serverIP = window.location.hostname;
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const mqttUrl = `${protocol}//${serverIP}:9001`;

            logMessage('info', 'MQTT', 'Conectando a ' + mqttUrl + '...');
            client = mqtt.connect(mqttUrl, {
                username: 'admin',
                password: 'AWLCxdfGxwohHF2qpScJLK9AbRAFxD'
            });

            client.on('connect', () => {
                logMessage('ok', 'MQTT', 'Conectado al Broker MQTT.');
                client.subscribe('sonda/status');
                client.subscribe('sonda/camera');
                client.subscribe('gps/data');
                client.subscribe('sonda/meshtastic');
                
                // Cargar primer estado
                sendCommand('get_status');
            });

            client.on('message', (topic, message) => {
                const payload = JSON.parse(message.toString());
                
                if (topic === 'sonda/status') {
                    lastSondaPing = Date.now();
                    checks.movil = true;
                    updateLinkState('movil', true);
                    
                    if (payload.status === 'diagnostico') {
                        handleSondaDiagnostics(payload);
                    } else {
                        handleSondaEvent(payload);
                    }
                } 
                else if (topic === 'gps/data') {
                    // Diferenciar entre paquete del Móvil (tiene accuracy) y LoRa (tiene speed/course sin accuracy)
                    if (payload.accuracy !== undefined) {
                        lastSondaPing = Date.now();
                        checks.movil = true;
                        updateLinkState('movil', true);
                        handleMobileTelemetry(payload);
                    } else {
                        lastLoraPing = Date.now();
                        checks.lora_telemetria = true;
                        updateLinkState('lora', true);
                        handleLoraTelemetry(payload);
                    }
                }
                else if (topic === 'sonda/camera') {
                    lastSondaPing = Date.now();
                    updateLinkState('movil', true);
                    handleCameraEvent(payload);
                }
                else if (topic === 'sonda/meshtastic') {
                    lastMeshPing = Date.now();
                    checks.lora_meshtastic = true;
                    updateLinkState('meshtastic', true);
                    handleMeshtasticEvent(payload);
                }
                // Si la secuencia de pruebas está activa, comprobar éxito inmediatamente
                if (isSequenceRunning) {
                    const step = testSteps[currentStepIndex];
                    if (step && step.check()) {
                        handleStepSuccess();
                    }
                }
            });

            // 3. Vigilante de Enlaces (Heartbeat)
            setInterval(() => {
                const now = Date.now();
                
                // Móvil
                if (now - lastSondaPing > 15000) {
                    if (checks.movil) {
                        checks.movil = false;
                        updateLinkState('movil', false);
                        logMessage('err', 'CONEXIÓN', 'Pérdida de cobertura de la Sonda Móvil.');
                    }
                }
                
                // LoRa Telemetría
                if (now - lastLoraPing > 15000) {
                    if (checks.lora_telemetria) {
                        checks.lora_telemetria = false;
                        updateLinkState('lora', false);
                        logMessage('err', 'CONEXIÓN', 'Receptor LoRa de Telemetría fuera de línea.');
                    }
                }

                // Meshtastic
                if (now - lastMeshPing > 20000) {
                    // No dar alarma fuerte aún para Meshtastic (se simula por ahora)
                }

                updateGeneralStatusLarge();
                validateChecklist();
            }, 4000);

            // 4. Manejadores de Recepción de Datos
            function handleSondaDiagnostics(data) {
                // Actualizar tabla comparativa
                document.getElementById('td-m-sats').textContent = data.accuracy ? 'Sí (Prec: ' + data.accuracy + 'm)' : 'Sí';
                document.getElementById('td-m-alt').textContent = data.alt !== null ? parseFloat(data.alt).toFixed(1) + ' m' : '--';
                document.getElementById('td-m-lat').textContent = data.lat !== null ? parseFloat(data.lat).toFixed(5) : '--';
                document.getElementById('td-m-lng').textContent = data.lng !== null ? parseFloat(data.lng).toFixed(5) : '--';
                document.getElementById('td-m-spd').textContent = '--';
                document.getElementById('td-m-crs').textContent = '--';
                document.getElementById('td-m-bat').textContent = data.level + '% / ' + data.temp + '°C';

                // Mini-cards
                document.getElementById('mini-bat').textContent = data.level + '%';
                document.getElementById('mini-temp').textContent = data.temp + '°C';
                document.getElementById('mini-gps').textContent = data.accuracy ? 'Acc: ' + data.accuracy + 'm' : 'Fijo';

                if (data.alt !== null && data.alt !== 'null') {
                    document.getElementById('mini-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
                }

                // Actualizar Mapa
                if (data.lat !== null && data.lat !== 'null' && data.lat !== 0) {
                    let latlng = [parseFloat(data.lat), parseFloat(data.lng)];
                    markers.movil.setLatLng(latlng);
                    paths.movil.addLatLng(latlng);
                }

                // Actualizar Checklist
                checks.sensors = true;
                updateChecklistUI('chk-sensors', true, data.temp + '°C (OK)');
                
                if (data.level >= 50) {
                    checks.battery = true;
                    updateChecklistUI('chk-battery', true, data.level + '% (Apto)');
                } else {
                    checks.battery = false;
                    updateChecklistUI('chk-battery', false, data.level + '% (Batería Baja!)');
                }

                if (data.accuracy && data.accuracy <= 10) {
                    checks.gps = true;
                    updateChecklistUI('chk-gps', true, 'Fijo (' + data.accuracy + 'm)');
                } else {
                    checks.gps = false;
                    updateChecklistUI('chk-gps', false, data.accuracy ? 'Acc: ' + data.accuracy + 'm (Insuficiente)' : 'Sin Enlace');
                }

                validateChecklist();
            }

            function handleMobileTelemetry(data) {
                document.getElementById('td-m-alt').textContent = data.altitude !== null ? parseFloat(data.altitude).toFixed(1) + ' m' : '--';
                document.getElementById('td-m-lat').textContent = data.lat !== null ? parseFloat(data.lat).toFixed(5) : '--';
                document.getElementById('td-m-lng').textContent = data.lng !== null ? parseFloat(data.lng).toFixed(5) : '--';

                if (data.altitude !== null) {
                    document.getElementById('mini-alt').textContent = parseFloat(data.altitude).toFixed(1) + ' m';
                }
                
                // Mapa
                if (data.lat !== null && data.lat !== 0) {
                    let latlng = [parseFloat(data.lat), parseFloat(data.lng)];
                    markers.movil.setLatLng(latlng);
                    paths.movil.addLatLng(latlng);
                }
                
                if (data.accuracy && data.accuracy <= 10) {
                    checks.gps = true;
                    updateChecklistUI('chk-gps', true, 'Fijo (' + data.accuracy + 'm)');
                }
                validateChecklist();
            }

            function handleLoraTelemetry(data) {
                // Actualizar tabla comparativa
                document.getElementById('td-l-sats').textContent = 'Fijo';
                document.getElementById('td-l-alt').textContent = data.altitude !== null ? parseFloat(data.altitude).toFixed(1) + ' m' : '--';
                document.getElementById('td-l-lat').textContent = data.lat !== null ? parseFloat(data.lat).toFixed(5) : '--';
                document.getElementById('td-l-lng').textContent = data.lng !== null ? parseFloat(data.lng).toFixed(5) : '--';
                document.getElementById('td-l-spd').textContent = data.speed !== undefined ? parseFloat(data.speed).toFixed(1) + ' km/h' : '--';
                document.getElementById('td-l-crs').textContent = data.course !== undefined ? data.course + '°' : '--';
                
                // Si la sonda perdió cobertura, rellenar mini-cards usando datos del LoRa
                if (!checks.movil) {
                    if (data.altitude !== null) document.getElementById('mini-alt').textContent = parseFloat(data.altitude).toFixed(1) + ' m';
                    if (data.speed !== undefined) document.getElementById('mini-spd').textContent = parseFloat(data.speed).toFixed(1) + ' km/h';
                    if (data.course !== undefined) document.getElementById('mini-crs').textContent = getWindDirection(data.course) + ' (' + data.course + '°)';
                }

                // Pintar en el mapa
                if (data.lat !== null && data.lat !== 0) {
                    let latlng = [parseFloat(data.lat), parseFloat(data.lng)];
                    markers.lora.setLatLng(latlng);
                    paths.lora.addLatLng(latlng);
                }
            }

            function handleCameraEvent(data) {
                // Actualizar foto
                const img = document.getElementById('photo-feed');
                img.src = '/images/last?t=' + Date.now(); // forzar refresco
                
                document.getElementById('photo-time').textContent = 'Última foto IA (' + new Date().toLocaleTimeString() + '): ' + data.texto;
                logMessage('ok', 'CÁMARA', 'Nueva foto procesada por IA: "' + data.texto + '"');
                
                checks.camera_foto = true;
                updateChecklistUI('chk-foto', true, 'Foto & IA Confirmada');
                validateChecklist();
            }

            function handleSondaEvent(data) {
                if (data.status === 'gps_initializing') {
                    updateChecklistUI('chk-gps', 'testing', 'Buscando satélites...');
                    logMessage('warn', 'GPS', 'Iniciando búsqueda activa de satélites GPS...');
                } else if (data.status === 'gps_ok') {
                    if (data.lat !== undefined && data.lat !== null) {
                        handleMobileTelemetry(data);
                    }
                    if (data.accuracy && data.accuracy <= 15) {
                        checks.gps = true;
                        updateChecklistUI('chk-gps', 'ok', 'Fijo (' + parseFloat(data.accuracy).toFixed(1) + 'm)');
                    } else {
                        checks.gps = true; // Aceptamos como recibido, pero en advertencia
                        updateChecklistUI('chk-gps', 'warn', 'Fijo (' + parseFloat(data.accuracy || 0).toFixed(1) + 'm)');
                    }
                    logMessage('ok', 'GPS', 'Señal de GPS fijada (Precisión: ' + (data.accuracy || '--') + 'm).');
                } else if (data.status === 'gps_failed') {
                    checks.gps = false;
                    updateChecklistUI('chk-gps', 'ko', 'Fallo Fijación');
                    logMessage('err', 'GPS', 'Fallo al fijar señal GPS.');
                } else if (data.status === 'audio_ok') {
                    checks.audio = true;
                    updateChecklistUI('chk-audio', 'ok', 'Confirmado');
                    logMessage('ok', 'AUDIO', 'Prueba de altavoz confirmada en el móvil.');
                } else if (data.status === 'video_streaming_on') {
                    streamActive = true;
                    checks.camera_video = true;
                    updateChecklistUI('chk-video', 'ok', 'Transmitiendo');
                    document.getElementById('btn-stream-switch').textContent = '🔌 DETENER VÍDEO';
                    document.getElementById('btn-stream-switch').className = 'btn btn-quick btn-outline-red';
                    switchCameraTab('video');
                    logMessage('ok', 'VÍDEO', 'Transmisión de vídeo en directo iniciada.');
                } else if (data.status === 'video_streaming_off') {
                    streamActive = false;
                    document.getElementById('btn-stream-switch').textContent = '📹 INICIAR VÍDEO';
                    document.getElementById('btn-stream-switch').className = 'btn btn-quick btn-accent';
                    switchCameraTab('foto');
                    logMessage('info', 'VÍDEO', 'Transmisión de vídeo en directo detenida.');
                } else if (data.status === 'camera_testing') {
                    logMessage('info', 'CÁMARA', 'Móvil procesando test de foto local con la IA...');
                } else if (data.status === 'camera_error' || data.status === 'camera_capture_failed') {
                    checks.camera_foto = false;
                    updateChecklistUI('chk-foto', 'ko', 'Fallo de cámara');
                    logMessage('err', 'CÁMARA', 'Error al disparar la cámara o procesar con llama.cpp.');
                } else if (data.status === 'armed') {
                    logMessage('ok', 'MISIÓN', '¡Sonda Armada! Bloqueando cambios terrestres.');
                }
                validateChecklist();
            }

            function handleMeshtasticEvent(data) {
                // Actualizar marcas en pantalla de nodos
                if (data.node_id && data.rssi) {
                    const rssiVal = data.rssi + ' dBm';
                    if (data.node_id === 1) {
                        document.getElementById('mesh-node-1').textContent = rssiVal;
                    } else if (data.node_id === 2) {
                        document.getElementById('mesh-node-2').textContent = rssiVal;
                    }
                    logMessage('info', 'MESHTASTIC', 'Paquete recibido de Nodo ' + data.node_id + ' (RSSI: ' + data.rssi + 'dBm)');
                }
            }

            // Definición de Pasos del Secuenciador Pre-Vuelo
            const testSteps = [
                {
                    id: 'chk-movil',
                    name: 'Móvil (Android)',
                    run: () => { sendCommand('get_status'); },
                    check: () => checks.movil,
                    timeout: 4000,
                    retries: 3
                },
                {
                    id: 'chk-lora',
                    name: 'ESP32 LoRa (Telemetría)',
                    run: () => { /* Pasivo */ },
                    check: () => checks.lora_telemetria,
                    timeout: 3000,
                    retries: 1
                },
                {
                    id: 'chk-meshtastic',
                    name: 'ESP32 LoRa (Meshtastic)',
                    run: () => { /* Pasivo/Mock */ },
                    check: () => checks.lora_meshtastic,
                    timeout: 2000,
                    retries: 1
                },
                {
                    id: 'chk-gps',
                    name: 'GPS Sonda',
                    run: () => { sendCommand('init_gps'); },
                    check: () => checks.gps,
                    timeout: 15000, // 15 segundos para dar tiempo al receptor físico GPS o su fallback de red
                    retries: 1
                },
                {
                    id: 'chk-battery',
                    name: 'Batería Móvil',
                    run: () => { sendCommand('get_status'); },
                    check: () => checks.battery,
                    timeout: 3000,
                    retries: 1
                },
                {
                    id: 'chk-sensors',
                    name: 'Sensores Sonda',
                    run: () => { sendCommand('get_status'); },
                    check: () => checks.sensors,
                    timeout: 3000,
                    retries: 1
                },
                {
                    id: 'chk-audio',
                    name: 'Altavoz (TTS)',
                    run: () => { sendCommand('test_audio'); },
                    check: () => checks.audio,
                    timeout: 5000,
                    retries: 2
                },
                {
                    id: 'chk-foto',
                    name: 'Cámara (Foto e IA)',
                    run: () => { sendCommand('test_photo'); },
                    check: () => checks.camera_foto,
                    timeout: 20000, // La inferencia local y upload toma tiempo
                    retries: 1 // No queremos reintentar inferencias pesadas
                },
                {
                    id: 'chk-video',
                    name: 'Cámara (Vídeo)',
                    run: () => { sendCommand('test_video_on'); },
                    check: () => checks.camera_video,
                    timeout: 6000,
                    retries: 2
                }
            ];

            // 5. Orquestador de Autotest Secuencial
            function runSelfTest() {
                if (isSequenceRunning) return;
                isSequenceRunning = true;
                
                // Resetear estados locales
                checks.movil = false;
                checks.lora_telemetria = false;
                checks.camera_foto = false;
                checks.camera_video = false;
                checks.battery = false;
                checks.sensors = false;
                checks.gps = false;
                checks.audio = false;

                resetChecklistUI();
                
                currentStepIndex = 0;
                currentRetry = 0;
                
                const btn = document.getElementById('btn-test-systems');
                btn.textContent = '🤖 EJECUTANDO AUTO-TEST...';
                btn.className = 'btn btn-quick btn-outline-red';
                btn.style.color = 'var(--yellow-accent)';
                btn.style.borderColor = 'var(--yellow-accent)';
                btn.disabled = true;

                logMessage('info', 'TEST', 'Iniciando secuencia de comprobación de sistemas paso a paso...');
                executeCurrentStep();
            }

            function executeCurrentStep() {
                if (currentStepIndex >= testSteps.length) {
                    isSequenceRunning = false;
                    const btn = document.getElementById('btn-test-systems');
                    btn.textContent = '🤖 SISTEMAS COMPROBADOS';
                    btn.className = 'btn btn-accent';
                    btn.style.color = '#000';
                    btn.style.borderColor = 'none';
                    btn.disabled = false;
                    logMessage('ok', 'TEST', 'Secuencia de auto-test completada.');
                    validateChecklist();
                    return;
                }
                
                const step = testSteps[currentStepIndex];
                updateChecklistUI(step.id, 'testing', 'Probando...');
                
                // Si la caché ya es válida, pasamos al siguiente
                if (step.check()) {
                    logMessage('ok', 'TEST', `${step.name} verificado por caché.`);
                    handleStepSuccess();
                    return;
                }
                
                logMessage('info', 'TEST', `Comprobando ${step.name}... (Intento ${currentRetry + 1}/${step.retries})`);
                step.run();
                
                clearTimeout(stepTimeoutTimer);
                stepTimeoutTimer = setTimeout(() => {
                    handleStepTimeout();
                }, step.timeout);
            }

            function handleStepSuccess() {
                clearTimeout(stepTimeoutTimer);
                const step = testSteps[currentStepIndex];
                
                // Para la batería, mostramos su estado warn/ok real
                if (step.id === 'chk-battery') {
                    const batText = document.getElementById('td-m-bat').textContent;
                    const batLvl = parseInt(batText) || 100;
                    if (batLvl >= 75) {
                        updateChecklistUI(step.id, 'ok', batText);
                    } else if (batLvl >= 50) {
                        updateChecklistUI(step.id, 'warn', batText);
                    } else {
                        updateChecklistUI(step.id, 'ko', batText + ' (Baja)');
                    }
                } else if (step.id === 'chk-gps') {
                    // Mantener texto de precisión si está
                    const accText = document.getElementById('chk-gps-val').textContent;
                    if (accText && accText.includes('m')) {
                        const match = accText.match(/\d+(\.\d+)?/);
                        const accVal = match ? parseFloat(match[0]) : 99;
                        updateChecklistUI(step.id, accVal <= 15 ? 'ok' : 'warn', accText);
                    } else {
                        updateChecklistUI(step.id, 'ok', 'CONFIRMADO');
                    }
                } else {
                    updateChecklistUI(step.id, 'ok', 'CONFIRMADO');
                }
                
                logMessage('ok', 'TEST', `${step.name} confirmado.`);
                
                if (step.id === 'chk-video') {
                    // Detener el vídeo 4 segundos después de validarlo
                    setTimeout(() => {
                        sendCommand('test_video_off');
                    }, 4000);
                }
                
                // Esperar 0.5s y avanzar
                setTimeout(() => {
                    currentStepIndex++;
                    currentRetry = 0;
                    executeCurrentStep();
                }, 500);
            }

            function handleStepTimeout() {
                const step = testSteps[currentStepIndex];
                if (step.check()) {
                    handleStepSuccess();
                    return;
                }
                
                currentRetry++;
                const maxRetries = step.retries || 3;
                if (currentRetry < maxRetries) {
                    logMessage('warn', 'TEST', `${step.name} sin respuesta. Reintentando (${currentRetry + 1}/${maxRetries})...`);
                    const item = document.getElementById(step.id);
                    if (item) item.classList.remove('testing');
                    setTimeout(() => {
                        executeCurrentStep();
                    }, 300);
                } else {
                    logMessage('err', 'TEST', `${step.name} falló tras ${maxRetries} intentos.`);
                    updateChecklistUI(step.id, 'ko', 'ERROR (KO)');
                    
                    setTimeout(() => {
                        currentStepIndex++;
                        currentRetry = 0;
                        executeCurrentStep();
                    }, 500);
                }
            }

            function resetChecklistUI() {
                const ids = ['chk-movil', 'chk-lora', 'chk-meshtastic', 'chk-foto', 'chk-video', 'chk-battery', 'chk-sensors', 'chk-gps', 'chk-audio'];
                ids.forEach(id => {
                    const item = document.getElementById(id);
                    if (item) item.className = 'checklist-item';
                    const val = document.getElementById(id + '-val');
                    if (val) val.textContent = 'Pendiente';
                });
            }

            // 6. Funciones de Interfaz de Usuario (UI)
            function updateChecklistUI(id, state, labelText) {
                const item = document.getElementById(id);
                const val = document.getElementById(id + '-val');
                if (!item) return;
                
                item.classList.remove('ok', 'ko', 'warn', 'testing');
                
                if (state === 'ok' || state === true) {
                    item.classList.add('ok');
                } else if (state === 'warn') {
                    item.classList.add('warn');
                } else if (state === 'testing') {
                    item.classList.add('testing');
                } else {
                    item.classList.add('ko');
                }
                
                if (val) val.textContent = labelText;
            }

            function updateLinkState(linkId, connected) {
                const badge = document.getElementById('link-' + linkId);
                const chk = document.getElementById('chk-' + linkId);
                const chkVal = document.getElementById('chk-' + linkId + '-val');
                
                if (connected) {
                    badge.textContent = 'Conectado';
                    badge.className = 'link-badge connected';
                    if (chk) {
                        chk.className = 'checklist-item ok';
                        chkVal.textContent = 'Conexión Estable';
                    }
                    if (linkId === 'movil') {
                        document.getElementById('sys-last-ping').textContent = new Date().toLocaleTimeString();
                    }
                } else {
                    badge.textContent = 'Desconectado';
                    badge.className = 'link-badge disconnected';
                    if (chk) {
                        chk.className = 'checklist-item ko';
                        chkVal.textContent = 'Sin Señal';
                    }
                }
            }

            function updateGeneralStatusLarge() {
                const large = document.getElementById('sys-status-large');
                
                let disconnectedCount = 0;
                if (!checks.movil) disconnectedCount++;
                if (!checks.lora_telemetria) disconnectedCount++;
                
                if (disconnectedCount === 0) {
                    large.textContent = 'OK';
                    large.className = 'status-large status-ok';
                } else if (disconnectedCount === 1) {
                    large.textContent = 'WARN';
                    large.className = 'status-large status-warn';
                } else {
                    large.textContent = 'ALERTA';
                    large.className = 'status-large status-alarm';
                }
            }

            function validateChecklist() {
                const btn = document.getElementById('btn-arm');
                
                // Checklist de despegue requiere obligatoriamente:
                // Móvil conectado, LoRa conectado, Foto Ok, Video OK, Batería OK, Sensores OK, GPS OK
                const isReady = checks.movil && checks.lora_telemetria && checks.camera_foto && checks.camera_video && checks.battery && checks.sensors && checks.gps;
                
                if (isReady && mission.state === 'espera') {
                    btn.disabled = false;
                } else {
                    btn.disabled = true;
                }
            }

            function switchCameraTab(tabName) {
                const tabFoto = document.getElementById('tab-foto');
                const tabVideo = document.getElementById('tab-video');
                const viewer = document.getElementById('camera-frame');
                const streamFrame = document.getElementById('video-stream');
                
                if (tabName === 'foto') {
                    tabFoto.className = 'camera-tab active';
                    tabVideo.className = 'camera-tab';
                    viewer.className = 'camera-viewer';
                    streamFrame.src = ""; // limpiar para no consumir datos
                } else {
                    tabFoto.className = 'camera-tab';
                    tabVideo.className = 'camera-tab active';
                    viewer.className = 'camera-viewer video-mode';
                    
                    // Asignar el stream HLS o WebRTC local
                    streamFrame.src = "https://vdo.ninja/?view=sonda_stream&clean";
                }
            }

            function toggleStreamCmd() {
                if (streamActive) {
                    sendCommand('test_video_off');
                } else {
                    sendCommand('test_video_on');
                }
            }

            function logMessage(level, tag, text) {
                const display = document.getElementById('log-display');
                const line = document.createElement('div');
                line.className = 'log-line';
                
                const timeSpan = document.createElement('span');
                timeSpan.className = 'time';
                timeSpan.textContent = new Date().toLocaleTimeString() + ' ';
                
                const tagSpan = document.createElement('span');
                tagSpan.className = 'tag ' + level;
                tagSpan.textContent = '[' + tag.toUpperCase() + '] ';
                
                const textSpan = document.createElement('span');
                textSpan.textContent = text;
                
                line.appendChild(timeSpan);
                line.appendChild(tagSpan);
                line.appendChild(textSpan);
                
                display.appendChild(line);
                display.scrollTop = display.scrollHeight; // Auto-scroll
            }

            // 7. Acciones de Envío
            function sendCommand(cmdName) {
                if (!client || !client.connected) return;
                const payload = JSON.stringify({ cmd: cmdName });
                client.publish('sonda/comando', payload);
                console.log('MQTT Publish sonda/comando:', cmdName);
            }

            function armLaunch() {
                logMessage('warn', 'MISIÓN', 'Armando la sonda e iniciando cuenta atrás para el despegue...');
                
                // Enviar arm al móvil
                sendCommand('arm');

                // Avisar a Flask para ponerlo en cuenta atrás
                fetch('/control_lanzamiento', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'armar' })
                });
            }

            function abortLaunch() {
                logMessage('err', 'MISIÓN', '¡ALERTA! Secuencia de lanzamiento abortada por el operador.');
                
                // Detener vídeo en móvil
                sendCommand('test_video_off');

                // Reiniciar estados locales
                isTesting = false;
                checks.camera_foto = false;
                checks.camera_video = false;
                updateChecklistUI('chk-foto', false, 'Abortado');
                updateChecklistUI('chk-video', false, 'Abortado');

                const btn = document.getElementById('btn-test-systems');
                btn.textContent = '🤖 PROBAR SISTEMAS';
                btn.className = 'btn btn-accent';
                btn.disabled = false;

                fetch('/control_lanzamiento', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'abortar' })
                });
            }

            function triggerBuzzer() {
                logMessage('warn', 'LORA', 'Enviando pulso de radio para activar la baliza sonora en el ESP32...');
                sendCommand('sirena_on');
            }

            function finalizeMission() {
                logMessage('info', 'MISIÓN', 'Finalizando misión. Sonda en fase de aterrizaje y recuperación.');
                fetch('/control_lanzamiento', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'finalizar' })
                });
            }

            function startNewMission() {
                const pass = prompt("Introduce la contraseña de misión:");
                if (pass === 'admin') {
                    logMessage('ok', 'SISTEMA', 'Iniciando una nueva sesión de misión.');
                    fetch('/control_lanzamiento', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'reset' })
                    }).then(() => {
                        window.location.reload();
                    });
                } else {
                    alert("Contraseña incorrecta.");
                }
            }

            // 8. Sincronización del Estado del Lanzamiento REST
            function pollLaunchStatus() {
                fetch('/control_lanzamiento')
                    .then(r => r.json())
                    .then(data => {
                        mission.state = data.estado;
                        document.getElementById('mission-state-card').textContent = data.estado.toUpperCase();
                        
                        // Sincronizar Fases visuales
                        updatePhaseIndicators(data.estado);

                        // Sincronizar reloj central
                        const clock = document.getElementById('countdown-clock');
                        if (data.estado === 'cuenta_atras') {
                            clock.textContent = '00:00:' + String(data.tiempo_restante).padStart(2, '0');
                            clock.className = 'countdown-value active';
                            document.getElementById('btn-arm').disabled = true;
                        } else {
                            clock.textContent = '00:00:10';
                            clock.className = 'countdown-value';
                        }
                    });
            }

            function updatePhaseIndicators(estado) {
                const p1 = document.getElementById('phase-1');
                const p2 = document.getElementById('phase-2');
                const p3 = document.getElementById('phase-3');
                const p4 = document.getElementById('phase-4');
                
                // Reset
                p1.className = 'phase-card';
                p2.className = 'phase-card';
                p3.className = 'phase-card';
                p4.className = 'phase-card';

                if (estado === 'espera' || estado === 'armando') {
                    p1.className = 'phase-card active';
                    currentPhase = 1;
                } else if (estado === 'cuenta_atras') {
                    p2.className = 'phase-card active';
                    currentPhase = 2;
                } else if (estado === 'lanzado') {
                    p3.className = 'phase-card active';
                    currentPhase = 3;
                } else if (estado === 'recuperacion') {
                    p4.className = 'phase-card active';
                    currentPhase = 4;
                }
            }

            // Cronómetro ascendente tras el despegue
            let missionSeconds = 0;
            setInterval(() => {
                if (mission.state === 'lanzado') {
                    missionSeconds++;
                    const hrs = String(Math.floor(missionSeconds / 3600)).padStart(2, '0');
                    const mins = String(Math.floor((missionSeconds % 3600) / 60)).padStart(2, '0');
                    const secs = String(missionSeconds % 60).padStart(2, '0');
                    document.getElementById('mission-time').textContent = `${hrs}:${mins}:${secs}`;
                } else if (mission.state === 'espera') {
                    missionSeconds = 0;
                    document.getElementById('mission-time').textContent = '00:00:00';
                }
            }, 1000);

            setInterval(pollLaunchStatus, 1000);

            // Helpers geográficos
            function getWindDirection(deg) {
                const sectors = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
                const index = Math.round(deg / 22.5) % 16;
                return sectors[index];
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
