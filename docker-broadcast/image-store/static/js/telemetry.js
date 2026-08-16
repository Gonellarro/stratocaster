// Procesadores de Recepción de Datos y Telemetría
function handleSondaDiagnostics(data) {
    // Un diagnóstico completo confirma la disponibilidad del móvil y alimenta
    // también los checks de batería y sensor térmico sin repetir get_status.
    if (isSequenceRunning) {
        checks.movil = true;
        updateChecklistUI('chk-movil', 'ok', 'Respuesta recibida');
        logMessage('ok', 'MÓVIL', 'Diagnóstico recibido correctamente.');
    }
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
            batBar.style.backgroundColor = 'var(--red)';
        } else if (data.level < 75) {
            batBar.style.backgroundColor = 'var(--amber)';
        } else {
            batBar.style.backgroundColor = 'var(--green)';
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
    if (isSequenceRunning) checks.movil = true;

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
    if (isSequenceRunning && lastLoraPing >= loraTestStartedAt) {
        checks.lora_telemetria = true;
    }
    updateLinkState('lora', true);

    if (data.rssi !== undefined && data.rssi !== null) {
        const signalEl = document.getElementById('sys-lora-signal');
        if (signalEl) signalEl.textContent = data.rssi + ' dBm';
    }

    // 2. Actualizar referencias LoRa. El check GPS requiere el acuse
    // explícito del móvil tras init_gps; LoRa no lo puede aprobar.
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

    // 5. Pintar el marcador rojo de LoRa en el mapa
    updateMapCoordinates('lora', data.lat, data.lng);

}

function aprsValueIsPresent(value) {
    return value !== undefined && value !== null && value !== 'null' && value !== '' && Number.isFinite(Number(value));
}

function aprsDataIsFresh(now = Date.now()) {
    return aprsLoraData.positionUpdatedAt > 0 &&
        aprsLoraData.temperatureUpdatedAt > 0 &&
        aprsLoraData.pressureUpdatedAt > 0 &&
        (now - aprsLoraData.positionUpdatedAt) <= APRS_DATA_MAX_AGE_MS &&
        (now - aprsLoraData.temperatureUpdatedAt) <= APRS_DATA_MAX_AGE_MS &&
        (now - aprsLoraData.pressureUpdatedAt) <= APRS_DATA_MAX_AGE_MS;
}

function aprsChecklistLabel() {
    const temp = aprsValueIsPresent(aprsLoraData.temperature) ? `${Number(aprsLoraData.temperature).toFixed(1)}°C` : '-- °C';
    const pressure = aprsValueIsPresent(aprsLoraData.pressure) ? `${Number(aprsLoraData.pressure).toFixed(1)} hPa` : '-- hPa';
    return `Posición · ${temp} · ${pressure}`;
}

// EA2FMQ-8 publica por APRS la posición y los sensores en tramas distintas.
// Conservamos el último valor fresco de cada grupo para que el control pueda
// comprobar el conjunto, sin confundirlo con la telemetría de la sonda.
function handleAprsLoraTelemetry(data) {
    const now = Date.now();
    aprsLoraData.lastSeen = now;

    if (aprsValueIsPresent(data.lat) && aprsValueIsPresent(data.lng)) {
        aprsLoraData.lat = Number(data.lat);
        aprsLoraData.lng = Number(data.lng);
        aprsLoraData.positionUpdatedAt = now;
    }
    if (aprsValueIsPresent(data.temperature_c)) {
        aprsLoraData.temperature = Number(data.temperature_c);
        aprsLoraData.temperatureUpdatedAt = now;
    }
    if (aprsValueIsPresent(data.pressure_hpa)) {
        aprsLoraData.pressure = Number(data.pressure_hpa);
        aprsLoraData.pressureUpdatedAt = now;
    }

    const position = document.getElementById('td-aprs-position');
    const temperature = document.getElementById('td-aprs-temperature');
    const pressure = document.getElementById('td-aprs-pressure');
    if (position && aprsValueIsPresent(aprsLoraData.lat) && aprsValueIsPresent(aprsLoraData.lng)) {
        position.textContent = `${aprsLoraData.lat.toFixed(5)}, ${aprsLoraData.lng.toFixed(5)}`;
    }
    if (temperature && aprsValueIsPresent(aprsLoraData.temperature)) {
        temperature.textContent = `${aprsLoraData.temperature.toFixed(1)} °C`;
    }
    if (pressure && aprsValueIsPresent(aprsLoraData.pressure)) {
        pressure.textContent = `${aprsLoraData.pressure.toFixed(1)} hPa`;
    }

    const receivedDuringTest = aprsLoraData.lastSeen >= aprsLoraTestStartedAt;
    if (isSequenceRunning && receivedDuringTest && aprsDataIsFresh(now)) {
        checks.aprs_lora = true;
        updateChecklistUI('chk-aprs-lora', 'ok', aprsChecklistLabel());
        logMessage('ok', 'LORA APRS', 'Posición, temperatura y presión recibidas de EA2FMQ-8.');
    }
}

function handleCameraEvent(data) {
    // Refrescar feed de foto
    const img = document.getElementById('photo-feed');
    if (img) {
        img.src = '/images/last?t=' + Date.now(); // forzar refresco
    }
    const streamFrame = document.getElementById('video-stream');
    if (streamFrame && !streamFrame.getAttribute('src')) {
        streamFrame.src = (window.CONFIG && window.CONFIG.vdoViewUrl) || 'https://vdo.ninja/?view=sonda_stratocaster';
    }
    switchCameraTab('foto');
    
    const photoTimeEl = document.getElementById('photo-time');
    if (photoTimeEl) {
        photoTimeEl.textContent = 'Última foto (' + new Date().toLocaleTimeString() + '): ' + (data.texto || 'Captura de verificación de cámara (OK)');
    }
    logMessage('ok', 'CÁMARA', 'Nueva foto recibida: "' + (data.texto || 'Captura de verificación de cámara (OK)') + '"');
    
    if (data.lat !== undefined && data.lat !== null && data.lat !== 'null' && data.lat !== 0) {
        updateMapCoordinates('movil', data.lat, data.lng);
    }
    
    if (isSequenceRunning) {
        checks.camera_foto = true;
        updateChecklistUI('chk-foto', true, 'Foto confirmada');
    }
}

function handleSondaEvent(data) {
    if (data.status === 'status_received') {
        if (isSequenceRunning) {
            // status_received solo es un acuse de recepción de la orden. El
            // móvil queda confirmado con el diagnóstico completo.
        }
        logMessage('ok', 'MÓVIL', 'El móvil ha recibido la orden de diagnóstico.');
    } else if (data.status === 'gps_initializing') {
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
    } else if (data.status === 'recovery_alarm_started') {
        logMessage('ok', 'BALIZA', 'Alarma de recuperación activada en el móvil.');
    } else if (data.status === 'recovery_alarm_missing_audio' || data.status === 'audio_rejected_missing_file' || data.status === 'audio_playback_failed') {
        logMessage('err', 'BALIZA', 'No se pudo activar la alarma MP3 de recuperación.');
    } else if (data.status === 'landed') {
        if (!landingTransitionRequested) {
            landingTransitionRequested = true;
            logMessage('warn', 'ATERRIZAJE', 'Aterrizaje detectado por la sonda. Activando recuperación.');
        }
        // Flask es la autoridad del estado. El navegador solo refresca su
        // representación mediante el polling periódico.
        pollLaunchStatus();
    } else if (data.status === 'video_streaming_on') {
        streamActive = true;
        videoPreviewReady = false;
        const videoLink = document.getElementById('video-link-state');
        if (videoLink) { videoLink.textContent = 'RECIBIENDO'; videoLink.className = 'link-badge connected'; }
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
        videoPreviewReady = false;
        videoPreviewInProgress = false;
        clearTimeout(videoPreviewTimer);
        const videoLink = document.getElementById('video-link-state');
        if (videoLink) { videoLink.textContent = 'SIN SEÑAL'; videoLink.className = 'link-badge disconnected'; }
        const streamBtn = document.getElementById('btn-stream-switch');
        if (streamBtn) {
            streamBtn.textContent = '📹 INICIAR VÍDEO';
            streamBtn.className = 'btn btn-quick btn-accent';
        }
        switchCameraTab('foto');
        logMessage('info', 'VÍDEO', 'Transmisión de vídeo en directo detenida.');
    } else if (data.status === 'camera_testing') {
        logMessage('info', 'CÁMARA', 'Móvil procesando la captura de verificación...');
    } else if (data.status === 'camera_error' || data.status === 'camera_capture_failed') {
        if (isSequenceRunning) {
            checks.camera_foto = false;
            updateChecklistUI('chk-foto', 'ko', 'Fallo de cámara');
        }
        logMessage('err', 'CÁMARA', 'Error al disparar la cámara o procesar con llama.cpp.');
    } else if (data.status === 'armed') {
        if (mission.state !== 'armando') return;
        fetch('/control_lanzamiento', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'armada'})
        }).then(() => {
            mission.state = 'armada';
            validateChecklist();
        }).catch(() => logMessage('err', 'MISIÓN', 'El servidor no aceptó el acuse ARMADA.'));
        logMessage('ok', 'MISIÓN', '¡Sonda Armada! Bloqueando cambios terrestres.');
    }
}
