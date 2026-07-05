import os
import uuid
import json
import datetime
import time
from flask import Flask, request, send_from_directory, render_template_string, jsonify

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
                        texto = data.get('texto', 'Sin descripción')
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

@app.route('/control')
def control_panel():
    html_template = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stratocaster - Consola de Lanzamiento</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #0b0c10;
                --card-bg: rgba(255, 255, 255, 0.02);
                --card-border: rgba(255, 255, 255, 0.07);
                --text-color: #e2e8f0;
                --text-muted: #64748b;
                --red-accent: #ef4444;
                --red-glow: rgba(239, 68, 68, 0.15);
                --green-accent: #10b981;
                --green-glow: rgba(16, 185, 129, 0.15);
                --yellow-accent: #f59e0b;
                --cyan-accent: #06b6d4;
                --cyan-glow: rgba(6, 182, 212, 0.2);
            }
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                min-height: 100vh;
                padding: 2rem;
                background-image: radial-gradient(circle at 50% 0%, rgba(6, 182, 212, 0.05) 0%, transparent 60%);
            }
            .container { max-width: 1200px; margin: 0 auto; }
            header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2.5rem;
                border-bottom: 1px solid var(--card-border);
                padding-bottom: 1.5rem;
            }
            header h1 {
                font-size: 2rem;
                font-weight: 700;
                background: linear-gradient(135deg, #fff 0%, #a5f3fc 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .sonda-link {
                background: rgba(255,255,255,0.04);
                border: 1px solid var(--card-border);
                padding: 0.5rem 1rem;
                border-radius: 8px;
                font-size: 0.85rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background-color: var(--text-muted);
                display: inline-block;
            }
            .status-dot.active {
                background-color: var(--green-accent);
                box-shadow: 0 0 10px var(--green-glow);
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0% { transform: scale(1); opacity: 1; }
                50% { transform: scale(1.2); opacity: 0.7; }
                100% { transform: scale(1); opacity: 1; }
            }
            
            /* Indicador del Estado de Lanzamiento */
            .state-banner {
                background: rgba(255, 255, 255, 0.01);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                padding: 2.5rem;
                text-align: center;
                margin-bottom: 2.5rem;
                position: relative;
                overflow: hidden;
            }
            .state-title {
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.15em;
                color: var(--text-muted);
                margin-bottom: 0.75rem;
            }
            .state-value {
                font-size: 3rem;
                font-weight: 700;
                letter-spacing: -0.02em;
            }
            .state-espera { color: var(--text-color); }
            .state-armando {
                color: var(--yellow-accent);
                animation: blink 1.5s infinite;
            }
            .state-countdown {
                color: var(--red-accent);
                font-size: 4rem;
                text-shadow: 0 0 20px rgba(239, 68, 68, 0.4);
                animation: scalePulse 1s infinite alternate;
            }
            .state-lanzado {
                color: var(--green-accent);
                text-shadow: 0 0 20px rgba(16, 185, 129, 0.3);
            }
            @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
            @keyframes scalePulse { 0% { transform: scale(1); } 100% { transform: scale(1.03); } }

            /* Grid Layout */
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 2.5rem;
                margin-bottom: 2.5rem;
            }
            @media (max-width: 768px) {
                .grid { grid-template-columns: 1fr; }
            }

            .panel {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                padding: 1.5rem;
            }
            .panel h2 {
                font-size: 1.25rem;
                font-weight: 600;
                margin-bottom: 1.5rem;
                border-bottom: 1px solid var(--card-border);
                padding-bottom: 0.75rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            /* Checklist */
            .checklist-item {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.75rem 0;
                border-bottom: 1px solid rgba(255,255,255,0.02);
            }
            .checklist-checkbox {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 1px solid var(--card-border);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.75rem;
                color: transparent;
                transition: all 0.2s;
            }
            .checklist-item.checked .checklist-checkbox {
                background-color: var(--green-accent);
                border-color: var(--green-accent);
                color: #fff;
                box-shadow: 0 0 8px var(--green-glow);
            }
            .checklist-label {
                font-size: 0.95rem;
                flex-grow: 1;
            }
            .checklist-val {
                font-size: 0.9rem;
                color: var(--text-muted);
                font-family: monospace;
            }

            /* Diagnostic Grid */
            .diag-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1rem;
            }
            .diag-card {
                background: rgba(255,255,255,0.01);
                border: 1px solid var(--card-border);
                border-radius: 10px;
                padding: 1rem;
                text-align: center;
            }
            .diag-label {
                font-size: 0.75rem;
                color: var(--text-muted);
                text-transform: uppercase;
                margin-bottom: 0.5rem;
            }
            .diag-value {
                font-size: 1.3rem;
                font-weight: 600;
                font-family: monospace;
            }

            /* Buttons & Actions */
            .actions-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1rem;
            }
            .btn {
                font-family: 'Outfit', sans-serif;
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--card-border);
                color: var(--text-color);
                padding: 0.85rem 1rem;
                border-radius: 10px;
                font-size: 0.9rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
            }
            .btn:hover:not(:disabled) {
                background: rgba(255,255,255,0.08);
                border-color: var(--text-color);
            }
            .btn:active:not(:disabled) {
                transform: scale(0.98);
            }
            .btn:disabled {
                opacity: 0.3;
                cursor: not-allowed;
            }
            .btn-accent {
                background: var(--cyan-accent);
                color: #000;
                border: none;
            }
            .btn-accent:hover:not(:disabled) {
                background: #22d3ee;
                box-shadow: 0 0 15px var(--cyan-glow);
            }
            .btn-red {
                background: var(--red-accent);
                color: #fff;
                border: none;
                font-size: 1.1rem;
                padding: 1.25rem 2rem;
                border-radius: 12px;
                width: 100%;
                box-shadow: 0 0 20px rgba(239, 68, 68, 0.2);
            }
            .btn-red:hover:not(:disabled) {
                background: #f87171;
                box-shadow: 0 0 25px rgba(239, 68, 68, 0.4);
            }
            .btn-outline-red {
                border-color: var(--red-accent);
                color: var(--red-accent);
            }
            .btn-outline-red:hover {
                background: rgba(239, 68, 68, 0.05);
            }

            .bottom-bar {
                text-align: center;
                margin-top: 1.5rem;
            }
            .bottom-link {
                color: var(--cyan-accent);
                text-decoration: none;
                font-size: 0.95rem;
                font-weight: 600;
            }
            .bottom-link:hover { text-decoration: underline; }
        </style>
        <!-- Importar MQTT.js desde CDN -->
        <script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>STRATOCASTER • LAUNCH CONTROL</h1>
                <div class="sonda-link">
                    <span id="sonda-dot" class="status-dot"></span>
                    <span id="sonda-status-text">Sonda Desconectada</span>
                </div>
            </header>

            <!-- Banner de Estado principal -->
            <div class="state-banner">
                <div class="state-title">Estado de la Misión</div>
                <div id="state-display" class="state-value state-espera">EN ESPERA</div>
            </div>

            <div class="grid">
                <!-- PANEL IZQUIERDO: Diagnósticos y Estado -->
                <div class="panel">
                    <h2>Diagnósticos en Tiempo Real</h2>
                    <div class="diag-grid" style="margin-bottom: 1.5rem;">
                        <div class="diag-card">
                            <div class="diag-label">Batería Móvil</div>
                            <div id="diag-bat" class="diag-value">--</div>
                        </div>
                        <div class="diag-card">
                            <div class="diag-label">Temp. Móvil</div>
                            <div id="diag-temp" class="diag-value">--</div>
                        </div>
                        <div class="diag-card">
                            <div class="diag-label">Altitud GPS</div>
                            <div id="diag-alt" class="diag-value">--</div>
                        </div>
                        <div class="diag-card">
                            <div class="diag-label">Precisión GPS</div>
                            <div id="diag-acc" class="diag-value">--</div>
                        </div>
                    </div>

                    <div class="diag-grid">
                        <div class="diag-card" style="grid-column: span 2;">
                            <div class="diag-label">Coordenadas de la Rampa</div>
                            <div id="diag-coords" class="diag-value" style="font-size: 1.1rem; padding: 0.2rem;">--</div>
                        </div>
                    </div>
                </div>

                <!-- PANEL DERECHO: Checklist y Comandos -->
                <div class="panel" style="display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <h2>Checklist de Sistemas</h2>
                        
                        <div id="check-gps" class="checklist-item">
                            <div class="checklist-checkbox">✓</div>
                            <div class="checklist-label">Señal GPS de la Sonda</div>
                            <div id="val-check-gps" class="checklist-val">Sin Señal</div>
                        </div>
                        
                        <div id="check-bat" class="checklist-item">
                            <div class="checklist-checkbox">✓</div>
                            <div class="checklist-label">Carga de Batería (>50%)</div>
                            <div id="val-check-bat" class="checklist-val">--</div>
                        </div>
                        
                        <div id="check-audio" class="checklist-item">
                            <div class="checklist-checkbox">✓</div>
                            <div class="checklist-label">Prueba de Altavoz (TTS)</div>
                            <div id="val-check-audio" class="checklist-val">Pendiente</div>
                        </div>
                        
                        <div id="check-video" class="checklist-item">
                            <div class="checklist-checkbox">✓</div>
                            <div class="checklist-label">Prueba de Vídeo en Vivo</div>
                            <div id="val-check-video" class="checklist-val">Pendiente</div>
                        </div>
                    </div>

                    <div class="actions-grid" style="margin-top: 1.5rem;">
                        <button class="btn" onclick="sendCommand('get_status')">🔍 Consultar Sensores</button>
                        <button class="btn" onclick="sendCommand('test_audio')">🔊 Probar Audio (TTS)</button>
                        <button class="btn" onclick="sendCommand('test_video_on')">📹 Test Vídeo [ON]</button>
                        <button class="btn" onclick="sendCommand('test_video_off')">🔌 Test Vídeo [OFF]</button>
                    </div>
                </div>
            </div>

            <!-- Firing Command & Abort -->
            <div class="panel" style="text-align: center; padding: 2rem;">
                <div style="max-width: 600px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.5rem;">
                    <button id="arm-btn" class="btn-red" onclick="armLaunch()" disabled>🔒 ARMAR SONDA & INICIAR CUENTA ATRÁS</button>
                    <button class="btn btn-outline-red" onclick="abortLaunch()">🚨 ABORTAR Y REINICIAR SISTEMAS</button>
                </div>
            </div>

            <div class="bottom-bar">
                <a href="/fotos" class="bottom-link">Ver Galería de Fotos →</a>
            </div>
        </div>

        <script>
            let client = null;
            let lastMessageTime = 0;
            let checks = {
                gps: false,
                battery: false,
                audio: false,
                video: false
            };

            // Detectar automáticamente la IP del servidor de la URL para conectar a MQTT
            const serverIP = window.location.hostname;
            const mqttUrl = 'ws://' + serverIP + ':9001';

            console.log('Conectando a MQTT en:', mqttUrl);
            client = mqtt.connect(mqttUrl, {
                username: 'admin',
                password: 'AWLCxdfGxwohHF2qpScJLK9AbRAFxD'
            });

            client.on('connect', () => {
                console.log('Conectado al Broker MQTT');
                client.subscribe('sonda/status');
                client.subscribe('sonda/camera');
                
                // Pedir estado inicial
                sendCommand('get_status');
            });

            client.on('message', (topic, message) => {
                const payload = JSON.parse(message.toString());
                console.log('Mensaje recibido en:', topic, payload);
                
                // Marcar sonda como activa (Heartbeat/Keepalive)
                lastMessageTime = Date.now();
                updateSondaConnection(true);

                if (topic === 'sonda/status') {
                    handleSondaStatus(payload);
                }
            });

            // Monitor de conexión de la sonda (si no habla en 15s, se marca offline)
            setInterval(() => {
                if (Date.now() - lastMessageTime > 15000) {
                    updateSondaConnection(false);
                }
            }, 5000);

            function updateSondaConnection(active) {
                const dot = document.getElementById('sonda-dot');
                const text = document.getElementById('sonda-status-text');
                if (active) {
                    dot.classList.add('active');
                    text.textContent = 'Sonda Conectada (Activa)';
                } else {
                    dot.classList.remove('active');
                    text.textContent = 'Sonda Desconectada (Inactiva)';
                    document.getElementById('arm-btn').disabled = true;
                }
            }

            function sendCommand(cmdName) {
                if (!client) return;
                const payload = JSON.stringify({ cmd: cmdName });
                client.publish('sonda/comando', payload);
                console.log('Comando enviado:', cmdName);
                
                if (cmdName === 'test_video_on') {
                    document.getElementById('check-video').classList.add('checked');
                    document.getElementById('val-check-video').textContent = 'Stream Activo';
                    checks.video = true;
                    validateChecklist();
                } else if (cmdName === 'test_video_off') {
                    document.getElementById('check-video').classList.remove('checked');
                    document.getElementById('val-check-video').textContent = 'Stream Parado';
                    checks.video = false;
                    validateChecklist();
                }
            }

            function handleSondaStatus(data) {
                // 1. Carga de sensores
                if (data.level !== undefined) {
                    document.getElementById('diag-bat').textContent = data.level + '%';
                    document.getElementById('diag-temp').textContent = data.temp + '°C';
                    
                    // Validar batería en el checklist
                    const batCheck = document.getElementById('check-bat');
                    const batVal = document.getElementById('val-check-bat');
                    if (data.level >= 50) {
                        batCheck.classList.add('checked');
                        batVal.textContent = data.level + '% (Apto)';
                        checks.battery = true;
                    } else {
                        batCheck.classList.remove('checked');
                        batVal.textContent = data.level + '% (Bajo!)';
                        checks.battery = false;
                    }
                }
                
                if (data.lat !== undefined && data.lat !== null && data.lat !== 'null') {
                    document.getElementById('diag-coords').textContent = parseFloat(data.lat).toFixed(5) + ', ' + parseFloat(data.lng).toFixed(5);
                    document.getElementById('diag-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
                    document.getElementById('diag-acc').textContent = data.accuracy ? data.accuracy + ' m' : '--';

                    // Validar GPS en el checklist
                    const gpsCheck = document.getElementById('check-gps');
                    const gpsVal = document.getElementById('val-check-gps');
                    gpsCheck.classList.add('checked');
                    gpsVal.textContent = 'Enlace Fijo (OK)';
                    checks.gps = true;
                }

                if (data.status === 'audio_ok') {
                    document.getElementById('check-audio').classList.add('checked');
                    document.getElementById('val-check-audio').textContent = 'Confirmado';
                    checks.audio = true;
                }
                
                if (data.status === 'armed') {
                    updateStatusDisplay('armando');
                }

                validateChecklist();
            }

            function validateChecklist() {
                const armBtn = document.getElementById('arm-btn');
                const isSondaActive = Date.now() - lastMessageTime < 15000;
                
                // Habilitar botón de lanzamiento solo si todos los tests pasan y la sonda responde
                if (checks.gps && checks.battery && checks.audio && checks.video && isSondaActive) {
                    armBtn.disabled = false;
                } else {
                    armBtn.disabled = true;
                }
            }

            // Llamadas REST a la API de Flask para sincronizar el estado global
            function updateStatusDisplay(state, timeRemaining = 10) {
                const display = document.getElementById('state-display');
                display.className = 'state-value'; // reset
                
                if (state === 'espera') {
                    display.textContent = 'EN ESPERA';
                    display.classList.add('state-espera');
                } else if (state === 'armando') {
                    display.textContent = 'SONDA ARMADA';
                    display.classList.add('state-armando');
                } else if (state === 'cuenta_atras') {
                    display.textContent = 'T-MINUS ' + timeRemaining + 's';
                    display.classList.add('state-countdown');
                } else if (state === 'lanzado') {
                    display.textContent = '¡DESPEGUE!';
                    display.classList.add('state-lanzado');
                }
            }

            function pollStatus() {
                fetch('/control_lanzamiento')
                    .then(r => r.json())
                    .then(data => {
                        updateStatusDisplay(data.estado, data.tiempo_restante);
                        
                        // Si está en cuenta atrás o lanzado, deshabilitar interacciones
                        if (data.estado === 'cuenta_atras' || data.estado === 'lanzado') {
                            document.getElementById('arm-btn').disabled = true;
                        }
                    });
            }
            setInterval(pollStatus, 1000);

            function armLaunch() {
                // 1. Enviar comando "arm" al móvil por MQTT
                sendCommand('arm');
                
                // 2. Avisar al servidor REST para ponerlo en modo armando
                fetch('/control_lanzamiento', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'armar' })
                });
            }

            function abortLaunch() {
                // 1. Mandar parada a la sonda
                sendCommand('test_video_off');
                
                // 2. Restablecer checklist local
                checks.audio = false;
                document.getElementById('check-audio').classList.remove('checked');
                document.getElementById('val-check-audio').textContent = 'Pendiente';
                
                // 3. Resetear API
                fetch('/control_lanzamiento', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'abortar' })
                });
                
                validateChecklist();
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
