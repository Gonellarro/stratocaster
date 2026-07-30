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

    // Actualizar datos de telemetría en tiempo real
    if (data.alt !== null && data.alt !== 'null') {
        document.getElementById('mini-alt').textContent = parseFloat(data.alt).toFixed(1) + ' m';
    }

    // Actualizar Coordenadas en Mapa
    updateMapCoordinates('movil', data.lat, data.lng);

    // Registrar comunicación activa con el móvil
    checks.movil = true;

    // Solo cambiar el estado gráfico del checklist si la secuencia de prueba (autotest) está ejecutándose activamente
    if (isSequenceRunning) {
        updateChecklistUI('chk-movil', 'ok', 'CONFIRMADO');

        checks.sensors = true;
        updateChecklistUI('chk-sensors', 'ok', data.temp + '°C (OK)');

        if (data.level >= 50) {
            checks.battery = true;
            updateChecklistUI('chk-battery', 'ok', data.level + '% (Apto)');
        } else {
            checks.battery = false;
            updateChecklistUI('chk-battery', 'ko', data.level + '% (Baja)');
        }

        // Validación de GPS
        if (data.lat !== undefined && data.lat !== null && data.lat !== 'null' && data.lat !== 0) {
            checks.gps = true;
            const hasAcc = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null");
            const accText = hasAcc ? ' (' + data.accuracy + 'm)' : '';
            updateChecklistUI('chk-gps', 'ok', 'Fijo' + accText);
        }

        validateChecklist();
    }
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
}

function handleLoraTelemetry(data) {
    // 1. Actualizar estado de enlace y checklist de LoRa
    checks.lora_telemetria = true;
    updateLinkState('lora', true);
    updateChecklistUI('chk-lora', 'ok', 'Enlace OK (868MHz)');

    if (data.rssi !== undefined && data.rssi !== null) {
        const signalEl = document.getElementById('sys-lora-signal');
        if (signalEl) signalEl.textContent = data.rssi + ' dBm';
    }

    // 2. Si recibimos coordenadas GPS válidas por LoRa, marcar también el GPS como disponible
    if (data.lat !== null && data.lat !== undefined && data.lat !== 'null' && data.lat !== 0) {
        checks.gps = true;
        const gpsVal = document.getElementById('chk-gps-val');
        if (gpsVal && (gpsVal.textContent === 'Sin Enlace' || gpsVal.textContent === 'Sin Verificar')) {
            updateChecklistUI('chk-gps', 'ok', 'Fijo LoRa');
        }
    }

    // 3. Actualizar referencias LoRa
    if (document.getElementById('td-l-sats')) document.getElementById('td-l-sats').textContent = 'Fijo';
    if (document.getElementById('td-l-alt')) document.getElementById('td-l-alt').textContent = data.altitude !== null && data.altitude !== undefined ? parseFloat(data.altitude).toFixed(1) + ' m' : '--';
    if (document.getElementById('td-l-lat')) document.getElementById('td-l-lat').textContent = data.lat !== null && data.lat !== undefined ? parseFloat(data.lat).toFixed(5) : '--';
    if (document.getElementById('td-l-lng')) document.getElementById('td-l-lng').textContent = data.lng !== null && data.lng !== undefined ? parseFloat(data.lng).toFixed(5) : '--';
    if (document.getElementById('td-l-spd')) document.getElementById('td-l-spd').textContent = data.speed !== undefined && data.speed !== null ? parseFloat(data.speed).toFixed(1) + ' km/h' : '--';
    if (document.getElementById('td-l-crs')) document.getElementById('td-l-crs').textContent = data.course !== undefined && data.course !== null ? data.course + '°' : '--';
    
    // 4. Volcar SIEMPRE los datos reales de radio LoRa (868MHz) a las tarjetas de Telemetría en Tiempo Real
    if (data.lat !== null && data.lat !== undefined && data.lat !== 'null') {
        document.getElementById('td-m-lat').textContent = parseFloat(data.lat).toFixed(5);
    }
    if (data.lng !== null && data.lng !== undefined && data.lng !== 'null') {
        document.getElementById('td-m-lng').textContent = parseFloat(data.lng).toFixed(5);
    }
    if (data.altitude !== null && data.altitude !== undefined && data.altitude !== 'null') {
        document.getElementById('mini-alt').textContent = parseFloat(data.altitude).toFixed(1) + ' m';
    }
    if (data.speed !== undefined && data.speed !== null && data.speed !== 'null') {
        document.getElementById('mini-spd').textContent = parseFloat(data.speed).toFixed(1) + ' km/h';
    }
    if (data.course !== undefined && data.course !== null && data.course !== 'null') {
        const courseNum = parseFloat(data.course);
        document.getElementById('mini-crs').textContent = getWindDirection(courseNum) + ' (' + courseNum.toFixed(1) + '°)';
    }

    // 5. Pintar ruta y marcador rojo de LoRa en el mapa
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
    
    if (isSequenceRunning) {
        checks.camera_foto = true;
        updateChecklistUI('chk-foto', true, 'Foto & IA Confirmada');
    }
}

function handleSondaEvent(data) {
    if (data.status === 'gps_initializing') {
        if (isSequenceRunning) updateChecklistUI('chk-gps', 'testing', 'Buscando satélites...');
        logMessage('warn', 'GPS', 'Iniciando búsqueda activa de satélites GPS...');
    } else if (data.status === 'gps_ok') {
        // Siempre actualizar datos de telemetría en la UI
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
        // Solo marcar el checklist si el autotest está corriendo
        if (isSequenceRunning) {
            checks.gps = true;
            const accText = (data.accuracy !== undefined && data.accuracy !== null && data.accuracy !== "null" && data.accuracy !== 0) ? ' (' + parseFloat(data.accuracy).toFixed(1) + 'm)' : '';
            updateChecklistUI('chk-gps', 'ok', 'Fijo' + accText);
        }
        logMessage('ok', 'GPS', 'Señal de GPS fijada (Precisión: ' + (data.accuracy || '--') + 'm).');
    } else if (data.status === 'gps_failed') {
        if (isSequenceRunning) {
            checks.gps = false;
            updateChecklistUI('chk-gps', 'ko', 'Fallo Fijación');
        }
        logMessage('err', 'GPS', 'Fallo al fijar señal GPS.');
    } else if (data.status === 'audio_ok') {
        if (isSequenceRunning) {
            checks.audio = true;
            updateChecklistUI('chk-audio', 'ok', 'Confirmado');
        }
        logMessage('ok', 'AUDIO', 'Prueba de altavoz confirmada en el móvil.');
    } else if (data.status === 'video_streaming_on') {
        streamActive = true;
        if (isSequenceRunning) {
            checks.camera_video = true;
            updateChecklistUI('chk-video', 'ok', 'Transmitiendo');
        }
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
        if (isSequenceRunning) {
            checks.camera_foto = false;
            updateChecklistUI('chk-foto', 'ko', 'Fallo de cámara');
        }
        logMessage('err', 'CÁMARA', 'Error al disparar la cámara o procesar con llama.cpp.');
    } else if (data.status === 'armed') {
        logMessage('ok', 'MISIÓN', '¡Sonda Armada! Bloqueando cambios terrestres.');
    }
}

function handleMeshtasticEvent(data, nodeIdFromTopic = null) {
    const nodeId = nodeIdFromTopic || data.node_id;
    if (nodeId && data.rssi) {
        const rssiVal = data.rssi + ' dBm';
        if (nodeId === 1) {
            document.getElementById('mesh-node-1').textContent = rssiVal;
        } else if (nodeId === 2) {
            document.getElementById('mesh-node-2').textContent = rssiVal;
        } else if (nodeId === 3) {
            document.getElementById('mesh-node-3').textContent = rssiVal;
        }
        logMessage('info', 'MESHTASTIC', 'Paquete recibido de Nodo ' + nodeId + ' (RSSI: ' + data.rssi + 'dBm)');
    }
}
