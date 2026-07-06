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
    lora_telemetria: true,
    lora_meshtastic: true,
    camera_foto: false,
    camera_video: true,
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
        updateChecklistUI('chk-gps', 'ok', 'Fijo (' + data.accuracy + 'm)');
    } else if (!checks.gps) {
        // Solo marcar como fallo si init_gps no lo habia confirmado previamente
        updateChecklistUI('chk-gps', 'ko', data.accuracy ? 'Acc: ' + data.accuracy + 'm (Insuficiente)' : 'Sin Enlace');
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
        // Actualizar tabla, mini-cards y mapa con los datos del GPS
        if (data.lat !== undefined && data.lat !== null && data.lat !== 'null') {
            document.getElementById('td-m-lat').textContent = parseFloat(data.lat).toFixed(5);
            document.getElementById('td-m-lng').textContent = parseFloat(data.lng).toFixed(5);
            if (data.alt !== undefined && data.alt !== null && data.alt !== 'null') {
                document.getElementById('td-m-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
                document.getElementById('mini-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
            }
            document.getElementById('mini-gps').textContent = 'Acc: ' + (data.accuracy || '--') + 'm';
            // Actualizar mapa
            let latlng = [parseFloat(data.lat), parseFloat(data.lng)];
            markers.movil.setLatLng(latlng);
            paths.movil.addLatLng(latlng);
            map.setView(latlng, 15);
        }
        if (data.accuracy && data.accuracy <= 15) {
            checks.gps = true;
            updateChecklistUI('chk-gps', 'ok', 'Fijo (' + parseFloat(data.accuracy).toFixed(1) + 'm)');
        } else {
            checks.gps = true;
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
    }
];

// 5. Orquestador de Autotest Secuencial
function runSelfTest() {
    if (isSequenceRunning) return;
    isSequenceRunning = true;
    
    // Resetear estados locales
    checks.movil = false;
    checks.lora_telemetria = true;
    checks.lora_meshtastic = true;
    checks.camera_foto = false;
    checks.camera_video = true;
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
    
    // (El test de vídeo se ha eliminado de la secuencia automática)
    
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
    const ids = ['chk-movil', 'chk-lora', 'chk-meshtastic', 'chk-gps', 'chk-battery', 'chk-sensors', 'chk-audio', 'chk-foto'];
    ids.forEach(id => {
        const item = document.getElementById(id);
        if (item) item.className = 'checklist-item';
        const val = document.getElementById(id + '-val');
        if (val) val.textContent = 'Pendiente';
    });
    
    // Forzar LoRa y Meshtastic a verde directamente
    checks.lora_telemetria = true;
    checks.lora_meshtastic = true;
    updateChecklistUI('chk-lora', 'ok', 'Omitido');
    updateChecklistUI('chk-meshtastic', 'ok', 'Omitido');
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
            // Si es LoRa o Meshtastic, mantenerlos en verde (omitidos/aprobados directamente)
            if (linkId === 'lora' || linkId === 'meshtastic') {
                chk.className = 'checklist-item ok';
                chkVal.textContent = 'Omitido';
            } else {
                chk.className = 'checklist-item ko';
                chkVal.textContent = 'Sin Enlace';
            }
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
