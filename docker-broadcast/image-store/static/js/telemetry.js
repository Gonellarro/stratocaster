// Procesadores de Recepción de Datos y Telemetría
function handleSondaDiagnostics(data) {
    // Actualizar tabla comparativa
    document.getElementById('td-m-sats').textContent = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null") ? 'Sí (Prec: ' + data.accuracy + 'm)' : 'Sí (Sin Prec.)';
    document.getElementById('td-m-alt').textContent = data.alt !== null ? parseFloat(data.alt).toFixed(1) + ' m' : '--';
    document.getElementById('td-m-lat').textContent = data.lat !== null ? parseFloat(data.lat).toFixed(5) : '--';
    document.getElementById('td-m-lng').textContent = data.lng !== null ? parseFloat(data.lng).toFixed(5) : '--';
    document.getElementById('td-m-spd').textContent = '--';
    document.getElementById('td-m-crs').textContent = '--';
    document.getElementById('td-m-bat').textContent = data.level + '% / ' + data.temp + '°C';

    // Mini-cards
    document.getElementById('mini-bat').textContent = data.level + '%';
    const batBar = document.getElementById('mini-bat-bar');
    if (batBar) {
        batBar.style.width = data.level + '%';
        if (data.level < 50) {
            batBar.style.backgroundColor = 'var(--red-accent)';
        } else if (data.level < 75) {
            batBar.style.backgroundColor = 'var(--yellow-accent)';
        } else {
            batBar.style.backgroundColor = 'var(--green-accent)';
        }
    }
    document.getElementById('mini-temp').textContent = data.temp + '°C';
    document.getElementById('mini-gps').textContent = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null") ? 'Acc: ' + data.accuracy + 'm' : 'Fijo (Sin Prec.)';

    if (data.alt !== null && data.alt !== 'null') {
        document.getElementById('mini-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
    }

    // Actualizar Coordenadas en Mapa
    updateMapCoordinates('movil', data.lat, data.lng);

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

    // Validación de GPS
    const hasAcc = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null");
    if (data.lat !== undefined && data.lat !== null && data.lat !== 'null' && data.lat !== 0) {
        checks.gps = true;
        const accText = hasAcc ? ' (' + data.accuracy + 'm)' : '';
        updateChecklistUI('chk-gps', 'ok', 'Fijo' + accText);
    } else if (!checks.gps) {
        updateChecklistUI('chk-gps', 'ko', 'Sin Enlace');
    }

    validateChecklist();
}

function handleMobileTelemetry(data) {
    // Telemetría GPS móvil recibida
    document.getElementById('td-m-alt').textContent = data.altitude !== null ? parseFloat(data.altitude).toFixed(1) + ' m' : '--';
    document.getElementById('td-m-lat').textContent = data.lat !== null ? parseFloat(data.lat).toFixed(5) : '--';
    document.getElementById('td-m-lng').textContent = data.lng !== null ? parseFloat(data.lng).toFixed(5) : '--';

    if (data.altitude !== null) {
        document.getElementById('mini-alt').textContent = parseFloat(data.altitude).toFixed(1) + ' m';
    }
    
    // Mapa
    updateMapCoordinates('movil', data.lat, data.lng);
    
    // Validación de GPS
    const hasAcc = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null");
    if (data.lat !== undefined && data.lat !== null && data.lat !== 'null' && data.lat !== 0) {
        checks.gps = true;
        const accText = hasAcc ? ' (' + data.accuracy + 'm)' : '';
        updateChecklistUI('chk-gps', true, 'Fijo' + accText);
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
    
    // Si la sonda perdió cobertura móvil o aún no hay posición fija por 4G, alimentar visores principales con LoRa
    const currentLat = document.getElementById('td-m-lat').textContent;
    if (!checks.movil || currentLat === '--' || currentLat === '') {
        if (data.lat !== null && data.lat !== undefined) document.getElementById('td-m-lat').textContent = parseFloat(data.lat).toFixed(5);
        if (data.lng !== null && data.lng !== undefined) document.getElementById('td-m-lng').textContent = parseFloat(data.lng).toFixed(5);
        if (data.altitude !== null && data.altitude !== undefined) document.getElementById('mini-alt').textContent = parseFloat(data.altitude).toFixed(1) + ' m';
        if (data.speed !== undefined && data.speed !== null) document.getElementById('mini-spd').textContent = parseFloat(data.speed).toFixed(1) + ' km/h';
        if (data.course !== undefined && data.course !== null) document.getElementById('mini-crs').textContent = getWindDirection(data.course) + ' (' + data.course + '°)';
    }

    // Pintar ruta y marcador rojo de LoRa en el mapa
    updateMapCoordinates('lora', data.lat, data.lng);
}

function handleCameraEvent(data) {
    // Refrescar feed de foto
    const img = document.getElementById('photo-feed');
    if (img) {
        img.src = '/images/last?t=' + Date.now(); // forzar refresco
    }
    
    const photoTimeEl = document.getElementById('photo-time');
    if (photoTimeEl) {
        photoTimeEl.textContent = 'Última foto IA (' + new Date().toLocaleTimeString() + '): ' + data.texto;
    }
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
        if (data.lat !== undefined && data.lat !== null && data.lat !== 'null') {
            document.getElementById('td-m-lat').textContent = parseFloat(data.lat).toFixed(5);
            document.getElementById('td-m-lng').textContent = parseFloat(data.lng).toFixed(5);
            if (data.alt !== undefined && data.alt !== null && data.alt !== 'null') {
                document.getElementById('td-m-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
                document.getElementById('mini-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
            }
            document.getElementById('mini-gps').textContent = 'Acc: ' + (data.accuracy || '--') + 'm';
            updateMapCoordinates('movil', data.lat, data.lng);
        }
        checks.gps = true;
        const accText = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null" && data.accuracy !== 0) ? ' (' + parseFloat(data.accuracy).toFixed(1) + 'm)' : '';
        updateChecklistUI('chk-gps', 'ok', 'Fijo' + accText);
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
        const streamBtn = document.getElementById('btn-stream-switch');
        if (streamBtn) {
            streamBtn.textContent = '🔌 DETENER VÍDEO';
            streamBtn.className = 'btn btn-quick btn-outline-red';
        }
        switchCameraTab('video');
        logMessage('ok', 'VÍDEO', 'Transmisión de vídeo en directo iniciada.');
    } else if (data.status === 'video_streaming_off') {
        streamActive = false;
        const streamBtn = document.getElementById('btn-stream-switch');
        if (streamBtn) {
            streamBtn.textContent = '📹 INICIAR VÍDEO';
            streamBtn.className = 'btn btn-quick btn-accent';
        }
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
