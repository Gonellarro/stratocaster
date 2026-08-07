import os
import uuid
import json
import datetime
import time
import tempfile
import threading
from functools import wraps
from flask import Flask, request, send_from_directory, render_template, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import paho.mqtt.publish as mqtt_publish
    import paho.mqtt.client as mqtt_client_lib
except ImportError:  # El contenedor lo instala; permite importar la app en tests mínimos.
    mqtt_publish = None
    mqtt_client_lib = None

app = Flask(__name__)

# Configuración de sesión y directorios
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'stratocaster_secret_key_2026_change_me')
UPLOAD_FOLDER = '/app/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Credenciales de Administrador (leídas de variables de entorno o valores por defecto)
CONTROL_USER = os.environ.get('CONTROL_USER', '')
CONTROL_PASS = os.environ.get('CONTROL_PASS', '')

# Credenciales MQTT del Broker a inyectar en las vistas autenticadas
MQTT_HOST = os.environ.get('MQTT_HOST', '')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
MQTT_USER = os.environ.get('MQTT_COMMAND_USER', os.environ.get('TELEGRAF_MQTT_USER', ''))
MQTT_PASS = os.environ.get('MQTT_COMMAND_PASSWORD', os.environ.get('TELEGRAF_MQTT_PASSWORD', ''))
MQTT_VIEW_USER = os.environ.get('MQTT_VIEW_USER', os.environ.get('TELEGRAF_MQTT_USER', ''))
MQTT_VIEW_PASS = os.environ.get('MQTT_VIEW_PASSWORD', os.environ.get('TELEGRAF_MQTT_PASSWORD', ''))
DEVICE_ID = os.environ.get('SONDA_DEVICE_ID', 'movil_sonda_1')
VDO_NINJA_VIEW_URL = os.environ.get('VDO_NINJA_VIEW_URL', 'https://vdo.ninja/?view=sonda_stratocaster')

# Estado global del lanzamiento (en memoria)
LAUNCH_STATE = {
    'estado': 'espera',        # espera, armando, armada, cuenta_atras, lanzado, recuperacion, finalizada
    'tiempo_restante': 0,
    'timestamp_inicio': 0.0,
    'timestamp_mision': 0.0
}

def login_required(f):
    """Decorador para proteger rutas HTML exigiendo sesión activa de administrador."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login_view', next=request.path))
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
    allowed_origins = {
        'https://stratocaster.martivich.es',
        'https://staging-stratocaster.martivich.es',
        'http://localhost:5000',
        'http://127.0.0.1:5000',
    }
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
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

STATE_FILE = os.environ.get('LAUNCH_STATE_FILE', '/data/launch_state.json')
COUNTDOWN_SECONDS = 10

DEFAULT_STATE = {
    'mission_id': '',
    'estado': 'espera',
    'tiempo_restante': 0,
    'timestamp_inicio': 0.0,
    'timestamp_mision': 0.0,
    'preflight_passed': False,
    'video_confirmed': False,
    'last_command_id': '',
    'last_event': 'Sistema en espera',
}

def load_launch_state():
    default_state = dict(DEFAULT_STATE)
    if not os.path.exists(STATE_FILE):
        return default_state
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default_state

def save_launch_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix='launch-', suffix='.json', dir=os.path.dirname(STATE_FILE))
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        app.logger.error(f"Error saving launch state: {e}")

def handle_mqtt_status(message):
    """Actualiza la misión desde eventos del móvil, sin depender del navegador."""
    topic = message.topic
    expected_topic = f'sonda/mobile/{DEVICE_ID}/status'
    if topic != expected_topic:
        return
    try:
        payload = json.loads(message.payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        app.logger.warning('Estado MQTT no válido recibido en %s', topic)
        return
    if payload.get('status') != 'landed':
        return

    state = load_launch_state()
    if state.get('estado') not in ('lanzado', 'recuperacion'):
        app.logger.info('Aterrizaje recibido fuera de una misión lanzada; se ignora')
        return
    if state.get('estado') == 'recuperacion':
        return
    state['estado'] = 'recuperacion'
    state['tiempo_restante'] = 0
    state['last_event'] = 'Aterrizaje detectado; baliza de recuperación activa'
    save_launch_state(state)
    app.logger.info('Misión %s pasa a RECUPERACIÓN por evento MQTT landed', state.get('mission_id'))

def start_mqtt_listener():
    """Arranca un receptor MQTT persistente en segundo plano (un worker Gunicorn)."""
    if mqtt_client_lib is None or not MQTT_HOST:
        app.logger.warning('Receptor MQTT interno desactivado: falta paho-mqtt o MQTT_HOST')
        return

    def run():
        while True:
            try:
                try:
                    client = mqtt_client_lib.Client(
                        mqtt_client_lib.CallbackAPIVersion.VERSION2,
                        client_id=f'control-{DEVICE_ID}',
                    )
                except AttributeError:
                    client = mqtt_client_lib.Client(client_id=f'control-{DEVICE_ID}')
                if MQTT_VIEW_USER:
                    client.username_pw_set(MQTT_VIEW_USER, MQTT_VIEW_PASS)

                def on_connect(mqtt_client, userdata, flags, *args):
                    mqtt_client.subscribe(f'sonda/mobile/{DEVICE_ID}/status', qos=1)
                    app.logger.info('Receptor MQTT interno conectado y suscrito al estado móvil')

                def on_message(mqtt_client, userdata, message):
                    handle_mqtt_status(message)

                client.on_connect = on_connect
                client.on_message = on_message
                client.reconnect_delay_set(min_delay=2, max_delay=30)
                client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
                client.loop_forever()
            except Exception as exc:
                app.logger.warning('Receptor MQTT interno desconectado: %s', exc)
                time.sleep(5)

    threading.Thread(target=run, name='mqtt-status-listener', daemon=True).start()

def publish_command(command, command_id, extra=None):
    """Publica una orden de misión; el móvil debe devolver un acuse con el ID."""
    if mqtt_publish is None:
        app.logger.error('paho-mqtt no está instalado; no se puede publicar la orden')
        return False
    try:
        payload_data = {'cmd': command, 'command_id': command_id, 'expires_at': time.time() + 30}
        if extra:
            payload_data.update(extra)
        payload = json.dumps(payload_data)
        mqtt_publish.single(
            f'sonda/mobile/{DEVICE_ID}/command', payload=payload,
            hostname=MQTT_HOST, port=MQTT_PORT,
            auth={'username': MQTT_USER, 'password': MQTT_PASS} if MQTT_USER else None,
            qos=1, retain=False, keepalive=10,
        )
        app.logger.info('Orden MQTT publicada: cmd=%s device=%s host=%s:%s',
                        command, DEVICE_ID, MQTT_HOST, MQTT_PORT)
        return True
    except Exception as exc:
        app.logger.error('Error publicando comando %s: %s', command, exc)
        return False

def normalize_photo_orientation(filepath):
    """Corrige EXIF y fuerza las capturas de la sonda a formato horizontal."""
    try:
        with Image.open(filepath) as source:
            image_format = source.format or 'JPEG'
            image = ImageOps.exif_transpose(source)
            if image.height > image.width:
                image = image.rotate(-90, expand=True)
            if image_format == 'JPEG' and image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            image.save(filepath, format=image_format)
    except (UnidentifiedImageError, OSError) as exc:
        app.logger.warning('No se pudo normalizar la orientación de %s: %s', filepath, exc)

def update_countdown_state():
    """Calcula dinámicamente el tiempo restante de la cuenta atrás."""
    state = load_launch_state()
    if state.get('estado') == 'cuenta_atras':
        elapsed = time.time() - state.get('timestamp_inicio', 0.0)
        remaining = COUNTDOWN_SECONDS - int(elapsed)
        if remaining <= 0:
            state['estado'] = 'lanzado'
            state['tiempo_restante'] = 0
            command_id = uuid.uuid4().hex
            state['last_command_id'] = command_id
            state['last_event'] = 'Cuenta atrás completada; orden de lanzamiento enviada'
            save_launch_state(state)
            publish_command('launch', command_id)
        else:
            if state.get('tiempo_restante') != remaining:
                state['tiempo_restante'] = remaining
                save_launch_state(state)
    return state

@app.route('/control_lanzamiento', methods=['GET'])
def get_launch_status():
    state = update_countdown_state()
    return jsonify(state)

@app.route('/control_lanzamiento', methods=['POST'])
@api_auth_required
def change_launch_status():
    state = load_launch_state()
    data = request.json or {}
    action = data.get('action')

    def reject(message):
        return jsonify({'error': message, 'state': state}), 409

    if action == 'preflight_ok':
        if state.get('estado') != 'espera':
            return reject('No se puede aprobar el pre-vuelo durante una misión activa')
        state['preflight_passed'] = True
        state['video_confirmed'] = bool(data.get('video_confirmed', state.get('video_confirmed')))
        state['estado'] = 'espera'
        state['last_event'] = 'Pruebas pre-vuelo aprobadas'
    elif action == 'preflight_reset':
        if state.get('estado') != 'espera':
            return reject('No se puede invalidar el pre-vuelo durante una misión activa')
        state['preflight_passed'] = False
        state['video_confirmed'] = False
        state['last_event'] = 'Pruebas pre-vuelo caducadas; repetir autotest'
    elif action == 'video_confirmed':
        if state.get('estado') != 'espera' or not state.get('preflight_passed'):
            return reject('Las pruebas pre-vuelo deben estar aprobadas antes del vídeo')
        state['video_confirmed'] = True
        state['last_event'] = 'Vídeo confirmado visualmente por el operador'
    elif action == 'armar':
        if state.get('estado') != 'espera' or not state.get('preflight_passed') or not state.get('video_confirmed'):
            return reject('Faltan pruebas pre-vuelo o confirmación visual del vídeo')
        state['estado'] = 'armando'
        state['tiempo_restante'] = 0
        state['timestamp_inicio'] = 0.0
        state['timestamp_mision'] = 0.0
        state['mission_id'] = data.get('mission_id') or f"MISIÓN_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        command_id = uuid.uuid4().hex
        state['last_command_id'] = command_id
        state['last_event'] = 'Orden ARMAR enviada; esperando acuse del móvil'
        if not publish_command('arm', command_id):
            return reject('No se pudo enviar la orden ARMAR')
    elif action == 'armada':
        if state.get('estado') != 'armando':
            return reject('El móvil no puede confirmar ARMADA en la fase actual')
        state['estado'] = 'armada'
        state['last_event'] = 'Móvil armado y esperando lanzamiento'
    elif action == 'ok':
        if state.get('estado') != 'armada':
            return reject('El móvil debe confirmar ARMADA antes de la cuenta atrás')
        now = time.time()
        state['estado'] = 'cuenta_atras'
        state['timestamp_inicio'] = now
        state['timestamp_mision'] = now
        state['tiempo_restante'] = COUNTDOWN_SECONDS
        state['last_event'] = 'Cuenta atrás iniciada'
    elif action == 'recuperacion':
        if state.get('estado') not in ('lanzado', 'recuperacion'):
            return reject('La recuperación solo puede iniciarse tras el lanzamiento')
        state['estado'] = 'recuperacion'
        state['tiempo_restante'] = 0
        state['last_event'] = 'Aterrizaje detectado; baliza de recuperación activa'
    elif action == 'abortar':
        command_id = uuid.uuid4().hex
        publish_command('abort', command_id)
        state['estado'] = 'espera'
        state['tiempo_restante'] = 0
        state['timestamp_inicio'] = 0.0
        state['timestamp_mision'] = 0.0
        state['preflight_passed'] = False
        state['video_confirmed'] = False
        state['last_command_id'] = command_id
        state['last_event'] = 'Misión abortada; sistema en espera'
    elif action == 'reset':
        state = dict(DEFAULT_STATE)
        state['mission_id'] = f"MISIÓN_{datetime.datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
        state['last_event'] = 'Nueva misión creada; sistema en espera'
    elif action == 'finalizar':
        if state.get('estado') not in ('lanzado', 'recuperacion'):
            return reject('Solo se puede finalizar una misión lanzada o en recuperación')
        state['estado'] = 'finalizada'
        state['tiempo_restante'] = 0
        state['timestamp_inicio'] = 0.0
        state['timestamp_mision'] = 0.0
        state['preflight_passed'] = False
        state['video_confirmed'] = False
        state['last_event'] = 'Misión finalizada'
    else:
        return reject('Acción desconocida')

    save_launch_state(state)
    return jsonify(state)

@app.route('/control_lanzamiento/ack', methods=['POST'])
@api_auth_required
def sonda_command_ack():
    """Registra acuses del dispositivo sin iniciar transiciones implícitas."""
    state = load_launch_state()
    data = request.json or {}
    if data.get('device_id', DEVICE_ID) != DEVICE_ID:
        return jsonify({'error': 'device_id no autorizado'}), 403
    state['last_event'] = f"Acuse móvil: {data.get('status', 'desconocido')}"
    save_launch_state(state)
    return jsonify({'status': 'ok', 'state': state})

@app.route('/device_command', methods=['POST'])
@api_auth_required
def device_command():
    """Puerta autenticada para comandos de diagnóstico y recuperación."""
    data = request.json or {}
    device_id = data.get('device_id', DEVICE_ID)
    command = data.get('cmd', '')
    allowed = {
        'get_status', 'init_gps', 'test_video_on',
        'test_video_off', 'test_photo', 'play_audio', 'stop_audio',
    }
    if device_id != DEVICE_ID or command not in allowed:
        return jsonify({'error': 'Comando o dispositivo no permitido'}), 403
    command_id = data.get('command_id') or uuid.uuid4().hex
    extra = {}
    if command == 'play_audio':
        audio_id = data.get('audio_id')
        if audio_id != 'recovery_alarm':
            return jsonify({'error': 'Audio no permitido'}), 403
        extra['audio_id'] = audio_id
    if not publish_command(command, command_id, extra):
        return jsonify({'error': 'No se pudo publicar el comando'}), 503
    return jsonify({'status': 'sent', 'command_id': command_id})

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
        normalize_photo_orientation(filepath)
        
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
    return render_template('control.html', mqtt_user=MQTT_VIEW_USER, mqtt_pass=MQTT_VIEW_PASS,
                           device_id=DEVICE_ID, vdo_view_url=VDO_NINJA_VIEW_URL)

start_mqtt_listener()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
