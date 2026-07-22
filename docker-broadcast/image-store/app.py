import os
import uuid
import json
import datetime
import time
from functools import wraps
from flask import Flask, request, send_from_directory, render_template, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuración de sesión y directorios
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'stratocaster_secret_key_2026_change_me')
UPLOAD_FOLDER = '/app/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Credenciales de Administrador (leídas de variables de entorno o valores por defecto)
CONTROL_USER = os.environ.get('CONTROL_USER', 'admin')
CONTROL_PASS = os.environ.get('CONTROL_PASS', 'admin')

# Credenciales MQTT del Broker a inyectar en las vistas autenticadas
MQTT_USER = os.environ.get('TELEGRAF_MQTT_USER', 'admin')
MQTT_PASS = os.environ.get('TELEGRAF_MQTT_PASSWORD', 'AWLCxdfGxwohHF2qpScJLK9AbRAFxD')

# Estado global del lanzamiento (en memoria)
LAUNCH_STATE = {
    'estado': 'espera',        # 'espera', 'armando', 'cuenta_atras', 'lanzado', 'recuperacion'
    'tiempo_restante': 0,
    'timestamp_inicio': 0.0,
    'timestamp_mision': 0.0
}

def login_required(f):
    """Decorador para proteger rutas HTML exigiendo sesión activa de administrador."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login_view', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def api_auth_required(f):
    """Decorador para proteger endpoints de la API REST."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized', 'message': 'Se requiere iniciar sesión en la consola'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin:
        if 'localhost' in origin or '127.0.0.1' in origin or '192.168.' in origin or 'stratocaster.martivich.es' in origin:
            response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# ------------------------------------------------------------------------------
# AUTENTICACIÓN & LOGIN
# ------------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login_view():
    if request.method == 'POST':
        user = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if user == CONTROL_USER and password == CONTROL_PASS:
            session['logged_in'] = True
            session['user'] = user
            next_url = request.args.get('next') or url_for('control_panel')
            return redirect(next_url)
        else:
            return render_template('login.html', error='Usuario o contraseña incorrectos.')
            
    if session.get('logged_in'):
        return redirect(url_for('control_panel'))
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_view'))

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
@api_auth_required
def change_launch_status():
    global LAUNCH_STATE
    data = request.json or {}
    action = data.get('action')
    
    if action == 'armar':
        LAUNCH_STATE['estado'] = 'armando'
        LAUNCH_STATE['tiempo_restante'] = 0
        LAUNCH_STATE['timestamp_inicio'] = 0.0
        LAUNCH_STATE['timestamp_mision'] = 0.0
    elif action == 'ok':
        now = time.time()
        LAUNCH_STATE['estado'] = 'cuenta_atras'
        LAUNCH_STATE['timestamp_inicio'] = now
        LAUNCH_STATE['timestamp_mision'] = now
        LAUNCH_STATE['tiempo_restante'] = 10
    elif action == 'abortar' or action == 'reset':
        LAUNCH_STATE['estado'] = 'espera'
        LAUNCH_STATE['tiempo_restante'] = 0
        LAUNCH_STATE['timestamp_inicio'] = 0.0
        LAUNCH_STATE['timestamp_mision'] = 0.0
    elif action == 'finalizar':
        LAUNCH_STATE['estado'] = 'recuperacion'
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
        device_id = request.form.get('device_id', 'movil_sonda_1')
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        metadata = {
            'texto': texto,
            'device_id': device_id,
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

@app.route('/')
def index():
    return redirect(url_for('control_panel'))

@app.route('/fotos')
@login_required
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
    return render_template('fotos.html', fotos=fotos)

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
@login_required
def control_panel():
    return render_template('control.html', mqtt_user=MQTT_USER, mqtt_pass=MQTT_PASS)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
