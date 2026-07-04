import os
import uuid
import json
import datetime
from flask import Flask, request, send_from_directory, render_template_string
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = '/app/images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file:
        filename = secure_filename(file.filename)
        # Evitar colisiones usando un UUID único manteniendo la extensión original
        ext = os.path.splitext(filename)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)
        
        # Recibir texto opcional y guardarlo en formato JSON
        texto = request.form.get('texto', '')
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        metadata = {
            'texto': texto,
            'timestamp': timestamp,
            'filename': unique_name
        }
        
        # Guardar metadata
        meta_name = f"{os.path.splitext(unique_name)[0]}.json"
        meta_path = os.path.join(app.config['UPLOAD_FOLDER'], meta_name)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        return unique_name, 200

@app.route('/images/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/fotos')
def list_photos():
    fotos = []
    # Escanear el directorio para encontrar archivos de imagen
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            name_without_ext = os.path.splitext(file)[0]
            meta_file = f"{name_without_ext}.json"
            meta_path = os.path.join(app.config['UPLOAD_FOLDER'], meta_file)
            
            # Leer metadata si existe, si no, crear defaults
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
                # Obtener la fecha de modificación del archivo como fallback
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file)
                mtime = os.path.getmtime(filepath)
                timestamp = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                texto = 'Sin descripción'
                
            fotos.append({
                'filename': file,
                'texto': texto,
                'timestamp': timestamp,
                # Guardamos epoch para ordenar
                'mtime': os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], file))
            })
            
    # Ordenar fotos por fecha de modificación (más recientes primero)
    fotos.sort(key=lambda x: x['mtime'], reverse=True)
    
    # HTML embebido para la galería
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
            
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                min-height: 100vh;
                padding: 2rem 1rem;
                background-image: radial-gradient(circle at 50% 0%, rgba(6, 182, 212, 0.08) 0%, transparent 50%);
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
            }

            header {
                text-align: center;
                margin-bottom: 3rem;
            }

            header h1 {
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #fff 0%, #a5f3fc 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
            }

            header p {
                color: var(--text-muted);
                font-size: 1.1rem;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: 2rem;
            }

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

            .card:hover .image-container img {
                transform: scale(1.05);
            }

            .content {
                padding: 1.5rem;
                display: flex;
                flex-direction: column;
                flex-grow: 1;
            }

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

            .description {
                font-size: 0.95rem;
                line-height: 1.5;
                color: var(--text-color);
            }

            /* Modal / Lightbox */
            .lightbox {
                display: none;
                position: fixed;
                z-index: 999;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(10, 11, 15, 0.95);
                backdrop-filter: blur(8px);
                justify-content: center;
                align-items: center;
                padding: 2rem;
                opacity: 0;
                transition: opacity 0.3s ease;
            }

            .lightbox.active {
                display: flex;
                opacity: 1;
            }

            .lightbox-content {
                max-width: 90%;
                max-height: 90vh;
                position: relative;
            }

            .lightbox-content img {
                max-width: 100%;
                max-height: 80vh;
                border-radius: 12px;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }

            .lightbox-close {
                position: absolute;
                top: -40px;
                right: 0;
                color: #fff;
                font-size: 2rem;
                cursor: pointer;
                background: none;
                border: none;
            }

            .lightbox-caption {
                color: var(--text-color);
                margin-top: 1rem;
                text-align: center;
                font-size: 1.1rem;
            }
        </style>
    </head>
    <body>
        <div class="container">
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

        <!-- Lightbox Modal -->
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

            function closeLightbox() {
                document.getElementById('lightbox').classList.remove('active');
            }

            // Cerrar con Escape
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeLightbox();
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, fotos=fotos)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
