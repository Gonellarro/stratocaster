// Gestión de Acciones de Lanzamiento y Secuencias REST
function readyLaunch() {
    logMessage('warn', 'MISIÓN', 'Enviando orden ARMAR. El móvil seguirá esperando el lanzamiento.');
    mission.state = 'armando';
    validateChecklist();
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'armar', mission_id: mission.id })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        validateChecklist();
    }).catch(error => {
        mission.state = 'espera';
        validateChecklist();
        logMessage('err', 'MISIÓN', 'No se pudo armar: ' + error.message);
    });
}

function startCountdown() {
    logMessage('warn', 'MISIÓN', 'Iniciando la cuenta atrás. El lanzamiento se enviará al llegar a cero.');
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'ok' })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        mission.state = 'cuenta_atras';
        validateChecklist();
    }).catch(error => logMessage('err', 'MISIÓN', 'No se pudo iniciar la cuenta atrás: ' + error.message));
}

function startVideoPreview() {
    sendCommand('test_video_on');
    switchCameraTab('video');
    updateChecklistUI('chk-video', 'testing', 'Esperando imagen en OBS...');
    streamActive = false;
    videoPreviewReady = false;
    videoPreviewInProgress = true;
    clearTimeout(videoPreviewTimer);
    const confirm = document.getElementById('btn-video-confirm');
    if (confirm) confirm.disabled = true;
    logMessage('info', 'VÍDEO', 'Previsualización solicitada. Se observará durante 5 segundos.');
    videoPreviewTimer = setTimeout(() => {
        if (!streamActive) {
            videoPreviewInProgress = false;
            updateChecklistUI('chk-video', 'ko', 'Sin señal de vídeo');
            logMessage('err', 'VÍDEO', 'No se recibió señal de vídeo durante la previsualización.');
            return;
        }
        videoPreviewReady = true;
        videoPreviewInProgress = false;
        if (confirm) confirm.disabled = false;
        logMessage('ok', 'VÍDEO', 'Previsualización completada. Confirma la imagen en OBS.');
    }, 5000);
}

function confirmVideo() {
    if (mission.state !== 'espera' || !preflightPassed || !videoPreviewReady) return;
    videoConfirmed = true;
    checks.camera_video = true;
    updateChecklistUI('chk-video', 'ok', 'Confirmado en OBS');
    const videoLink = document.getElementById('video-link-state');
    if (videoLink) { videoLink.textContent = 'OBS CONFIRMADO'; videoLink.className = 'link-badge connected'; }
    fetch('/control_lanzamiento', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'video_confirmed'})
    }).then(() => validateChecklist()).catch(() => logMessage('err', 'VÍDEO', 'No se pudo registrar la confirmación.'));
    logMessage('ok', 'VÍDEO', 'El operador confirma que la imagen es correcta en OBS.');
}

function abortLaunch() {
    logMessage('err', 'MISIÓN', '¡ALERTA! Secuencia de lanzamiento abortada por el operador.');
    mission.state = 'espera';
    videoPreviewReady = false;
    videoPreviewInProgress = false;
    clearTimeout(videoPreviewTimer);
    checklistPassed = false;
    
    // Reiniciar estados locales
    isTesting = false;
    checks.camera_foto = false;
    checks.camera_video = false;
    resetChecklistUI();
    updateChecklistUI('chk-foto', false, 'Abortado');
    updateChecklistUI('chk-video', false, 'Abortado');

    const btn = document.getElementById('btn-test-systems');
    if (btn) {
        btn.textContent = '🤖 PROBAR SISTEMAS';
        btn.className = 'btn btn-accent';
        btn.disabled = false;
    }

    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'abortar' })
    }).then(validateChecklist);
}

function triggerBuzzer() {
    logMessage('warn', 'RECUPERACIÓN', 'Solicitando alarma sonora en el móvil...');
    sendCommand('play_audio', {audio_id: 'recovery_alarm'});
}

function finalizeMission() {
    logMessage('info', 'MISIÓN', 'Finalizando misión y cerrando la recuperación.');
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'finalizar' })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        mission.state = data.estado || 'finalizada';
        logMessage('ok', 'MISIÓN', 'Misión finalizada. Reloj detenido.');
        validateChecklist();
    }).catch(error => {
        logMessage('err', 'MISIÓN', 'No se pudo finalizar la misión: ' + error.message);
        pollLaunchStatus();
    });
}

function startNewMission() {
    if (!window.confirm('¿Crear una nueva misión y reiniciar el estado actual?')) return;
    logMessage('info', 'SISTEMA', 'Creando una nueva sesión de misión...');
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        window.location.reload();
    }).catch(error => logMessage('err', 'MISIÓN', 'No se pudo crear la nueva misión: ' + error.message));
}

function validateChecklist() {
    const btnReady = document.getElementById('btn-ready');
    const btnArm = document.getElementById('btn-arm');
    const btnAbort = document.getElementById('btn-abort');
    const btnPreview = document.getElementById('btn-video-preview');
    const btnVideoConfirm = document.getElementById('btn-video-confirm');
    const btnFinalize = document.getElementById('btn-finalize-mission');
    const btnNewMission = document.getElementById('btn-new-mission');
    
    if (!btnReady || !btnArm || !btnAbort) return;

    // Si la verificación completa tuvo éxito o todos los checks están OK:
    const isReady = preflightPassed && videoConfirmed;
    if (isReady) {
        checklistPassed = true;
    }
    
    // Botón Abortar siempre activo durante misiones en curso
    if (mission.state === 'armando' || mission.state === 'armada' || mission.state === 'cuenta_atras' || mission.state === 'lanzado') {
        btnAbort.disabled = false;
    } else {
        btnAbort.disabled = true;
    }

    // La previsualización y confirmación solo son posibles antes de armar.
    if (btnPreview) btnPreview.disabled = !(mission.state === 'espera' && preflightPassed && !videoPreviewInProgress && !videoConfirmed);
    if (btnVideoConfirm) btnVideoConfirm.disabled = !(mission.state === 'espera' && preflightPassed && videoPreviewReady && !videoConfirmed);
    if (btnFinalize) btnFinalize.disabled = !(mission.state === 'lanzado' || mission.state === 'recuperacion');
    if (btnNewMission) {
        btnNewMission.hidden = false;
        btnNewMission.disabled = ['armando', 'armada', 'cuenta_atras', 'lanzado'].includes(mission.state);
    }

    if (mission.state === 'armada') {
        // El armado ya está confirmado: ahora se puede iniciar la cuenta atrás.
        btnArm.disabled = true;
        btnReady.disabled = false;
        return;
    }

    if (mission.state !== 'espera') {
        btnReady.disabled = true;
        btnArm.disabled = true;
        return;
    }

    // En espera: primero ARMAR y después iniciar la cuenta atrás.
    if (!isReady) {
        btnReady.disabled = true;
        btnArm.disabled = true;
    } else {
        btnReady.disabled = true;
        btnArm.disabled = false;
    }
}

function pollLaunchStatus() {
    fetch('/control_lanzamiento')
        .then(r => r.json())
        .then(data => {
            mission.state = data.estado;
            if (data.mission_id) mission.id = data.mission_id;
            // Flask es la autoridad de presencia móvil. El navegador no
            // deduce la cobertura por sus propios mensajes MQTT.
            if (typeof data.mobile_online === 'boolean') {
                mobileOnline = data.mobile_online;
                lastSondaPing = (Number(data.mobile_last_seen) || 0) * 1000;
                updateLinkState('movil', mobileOnline);
                const coverageState = mobileOnline ? 'online' : 'offline';
                if (lastCoverageState === 'offline' && coverageState === 'online') {
                    logMessage('ok', 'COMUNICACIÓN', 'Comunicación móvil recuperada.');
                } else if (lastCoverageState === 'online' && coverageState === 'offline') {
                    logMessage('err', 'COMUNICACIÓN', 'Sin comunicación con el móvil. Se conserva la última posición válida.');
                }
                lastCoverageState = coverageState;
            }
            preflightPassed = Boolean(data.preflight_passed);
            videoConfirmed = Boolean(data.video_confirmed);
            if (preflightPassed) {
                checks.movil = true;
                checks.battery = true;
                checks.sensors = true;
                checks.gps = true;
                checks.camera_foto = true;
                updateChecklistUI('chk-movil', 'ok', 'CONFIRMADO');
                updateChecklistUI('chk-battery', 'ok', 'CONFIRMADO');
                updateChecklistUI('chk-sensors', 'ok', 'CONFIRMADO');
                updateChecklistUI('chk-gps', 'ok', 'CONFIRMADO');
                updateChecklistUI('chk-foto', 'ok', 'CONFIRMADO');
            }
            if (videoConfirmed) {
                checks.camera_video = true;
                updateChecklistUI('chk-video', 'ok', 'CONFIRMADO EN OBS');
            }
            checklistPassed = preflightPassed;
            
            const stateCard = document.getElementById('mission-state-card');
            if (stateCard) {
                stateCard.textContent = data.estado.toUpperCase();
            }
            
            // Sincronizar Fases visuales
            updatePhaseIndicators(data.estado);
            updateGeneralStatusLarge();

            // Sincronizar Tiempo de Misión (arriba) con el servidor
            if (data.timestamp_mision && data.timestamp_mision > 0) {
                const elapsedMs = Date.now() - (data.timestamp_mision * 1000);
                const hours = Math.floor(elapsedMs / 3600000);
                const minutes = Math.floor((elapsedMs % 3600000) / 60000);
                const seconds = Math.floor((elapsedMs % 60000) / 1000);
                
                const pad = (n) => String(n).padStart(2, '0');
                const timeEl = document.getElementById('mission-time');
                if (timeEl) {
                    timeEl.textContent = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
                }
            } else {
                const timeEl = document.getElementById('mission-time');
                if (timeEl) {
                    timeEl.textContent = '00:00:00';
                }
            }

            // Sincronizar reloj central
            const clock = document.getElementById('countdown-clock');
            if (clock) {
            if (data.estado === 'cuenta_atras') {
                    clock.textContent = '00:00:' + String(data.tiempo_restante).padStart(2, '0');
                    clock.className = 'countdown-value active';
            } else {
                    clock.textContent = '00:00:10';
                    clock.className = 'countdown-value';
                }
            }
            
            // Actualizar botones de control según el nuevo estado
            validateChecklist();
        });
}

function updatePhaseIndicators(estado) {
    const p1 = document.getElementById('phase-1');
    const p2 = document.getElementById('phase-2');
    const p3 = document.getElementById('phase-3');
    const p4 = document.getElementById('phase-4');
    
    if (!p1 || !p2 || !p3 || !p4) return;
    
    // Reset
    p1.className = 'phase-card';
    p2.className = 'phase-card';
    p3.className = 'phase-card';
    p4.className = 'phase-card';

    if (estado === 'espera' || estado === 'armando' || estado === 'armada') {
        p1.className = 'phase-card active';
        currentPhase = 1;
    } else if (estado === 'cuenta_atras') {
        p2.className = 'phase-card active';
        currentPhase = 2;
    } else if (estado === 'lanzado') {
        p3.className = 'phase-card active';
        currentPhase = 3;
    } else if (estado === 'recuperacion' || estado === 'finalizada') {
        p4.className = 'phase-card active';
        currentPhase = 4;
    }
}

// Polling activo del estado del servidor
setInterval(pollLaunchStatus, 2000);
