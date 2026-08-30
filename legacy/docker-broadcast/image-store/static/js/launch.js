// Gestión de Acciones de Lanzamiento y Secuencias REST
function setTestMode(enabled) {
    const toggle = document.getElementById('test-mode-toggle');
    if (toggle) toggle.disabled = true;
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'set_test_mode', enabled })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        testModeEnabled = Boolean(data.test_mode);
        updateTestModeUI();
        validateChecklist();
        logMessage(testModeEnabled ? 'warn' : 'info', 'SISTEMA', testModeEnabled
            ? 'Modo pruebas activo: los checks pre-vuelo no bloquean el avance.'
            : 'Modo pruebas desactivado: se aplican los checks habituales.');
    }).catch(error => {
        if (toggle) toggle.checked = !enabled;
        logMessage('err', 'SISTEMA', 'No se pudo cambiar el modo pruebas: ' + error.message);
    }).finally(() => {
        if (toggle) toggle.disabled = false;
    });
}

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
        if (!streamActive && !testModeEnabled) {
            videoPreviewInProgress = false;
            updateChecklistUI('chk-video', 'ko', 'Sin señal de vídeo');
            logMessage('err', 'VÍDEO', 'No se recibió señal de vídeo durante la previsualización.');
            return;
        }
        videoPreviewReady = true;
        videoPreviewInProgress = false;
        if (confirm) confirm.disabled = false;
        logMessage(testModeEnabled && !streamActive ? 'warn' : 'ok', 'VÍDEO', testModeEnabled && !streamActive
            ? 'Sin señal de vídeo; confirmación permitida por modo pruebas.'
            : 'Previsualización completada. Confirma la imagen en OBS.');
    }, 5000);
}

function confirmVideo() {
    if (mission.state !== 'espera' || (!preflightPassed && !testModeEnabled) || !videoPreviewReady) return;
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
    logMessage('info', 'MISIÓN', 'Solicitando Fase 4 al móvil...');
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'finalizar' })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        mission.state = data.estado || 'recuperacion_solicitada';
        logMessage('warn', 'MISIÓN', 'Recuperación solicitada. Esperando confirmación del móvil.');
        validateChecklist();
    }).catch(error => {
        logMessage('err', 'MISIÓN', 'No se pudo finalizar la misión: ' + error.message);
        pollLaunchStatus();
    });
}

function forceRecovery() {
    if (!window.confirm('El móvil no ha confirmado la recuperación. ¿Quieres declararla igualmente como decisión del operador?')) return;
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'forzar_recuperacion' })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        mission.state = data.estado;
        logMessage('warn', 'MISIÓN', 'Recuperación forzada por el operador; el móvil no la ha confirmado.');
        validateChecklist();
    }).catch(error => logMessage('err', 'MISIÓN', 'No se pudo forzar la recuperación: ' + error.message));
}

function closeMission() {
    if (!window.confirm('¿Cerrar la misión actual? Esta acción no borra las fotos ni la telemetría almacenadas.')) return;
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cerrar_mision' })
    }).then(async response => {
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        mission.state = data.estado;
        logMessage('ok', 'MISIÓN', 'Misión cerrada. Ya puedes iniciar una nueva.');
        validateChecklist();
    }).catch(error => logMessage('err', 'MISIÓN', 'No se pudo cerrar la misión: ' + error.message));
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
    const btnForceRecovery = document.getElementById('btn-force-recovery');
    const btnCloseMission = document.getElementById('btn-close-mission');
    const btnNewMission = document.getElementById('btn-new-mission');
    
    if (!btnReady || !btnArm || !btnAbort) return;

    // Si la verificación completa tuvo éxito o todos los checks están OK:
    const isReady = testModeEnabled || (preflightPassed && videoConfirmed);
    if (isReady) {
        checklistPassed = true;
    }
    
    // Botón Abortar siempre activo durante misiones en curso
    if (mission.state === 'armando' || mission.state === 'armada' || mission.state === 'cuenta_atras' || mission.state === 'lanzamiento_solicitado' || mission.state === 'lanzado') {
        btnAbort.disabled = false;
    } else {
        btnAbort.disabled = true;
    }

    // La previsualización y confirmación solo son posibles antes de armar.
    if (btnPreview) btnPreview.disabled = !(mission.state === 'espera' && (preflightPassed || testModeEnabled) && !videoPreviewInProgress && !videoConfirmed);
    if (btnVideoConfirm) btnVideoConfirm.disabled = !(mission.state === 'espera' && (preflightPassed || testModeEnabled) && videoPreviewReady && !videoConfirmed);
    if (btnFinalize) btnFinalize.disabled = !(['lanzamiento_solicitado', 'lanzado'].includes(mission.state));
    if (btnForceRecovery) btnForceRecovery.disabled = mission.state !== 'recuperacion_solicitada';
    if (btnCloseMission) btnCloseMission.disabled = !(['recuperacion', 'recuperacion_forzada'].includes(mission.state));
    if (btnNewMission) {
        btnNewMission.hidden = false;
        btnNewMission.disabled = ['armando', 'armada', 'cuenta_atras', 'lanzamiento_solicitado', 'lanzado', 'recuperacion_solicitada', 'aborto_solicitado'].includes(mission.state);
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
            const previousMissionState = mission.state;
            mission.state = data.estado;
            if (data.mission_id) mission.id = data.mission_id;
            if (previousMissionState !== 'lanzado' && data.estado === 'lanzado') {
                logMessage('ok', 'MISIÓN', '¡Sonda lanzada con éxito! La misión está en vuelo.');
            }
            // Flask es la autoridad de presencia móvil. El navegador no
            // deduce la cobertura por sus propios mensajes MQTT.
            if (typeof data.mobile_online === 'boolean') {
                mobileOnline = data.mobile_online;
                lastSondaPing = (Number(data.mobile_last_seen) || 0) * 1000;
                updateLinkState('movil', mobileOnline);
                const mobilePayload = data.mobile_last_payload || {};
                if (mobileOnline && mobilePayload.status === 'status_received') {
                    checks.movil = true;
                    updateChecklistUI('chk-movil', 'ok', 'RESPUESTA RECIBIDA');
                }
                if (mobileOnline && mobilePayload.status === 'diagnostico') {
                    checks.movil = true;
                    checks.sensors = true;
                    checks.battery = Number(mobilePayload.level) >= 50;
                    updateChecklistUI('chk-movil', 'ok', 'CONFIRMADO');
                    updateChecklistUI('chk-sensors', 'ok', `${mobilePayload.temp ?? '--'}°C (OK)`);
                    updateChecklistUI('chk-battery', checks.battery ? 'ok' : 'ko', `${mobilePayload.level ?? '--'}%`);
                }
                const coverageState = mobileOnline ? 'online' : 'offline';
                if (lastCoverageState === 'offline' && coverageState === 'online') {
                    logMessage('ok', 'COMUNICACIÓN', 'Comunicación móvil recuperada.');
                    if (mission.state === 'lanzado' && typeof reloadVideoViewer === 'function') {
                        reloadVideoViewer();
                    }
                } else if (lastCoverageState === 'online' && coverageState === 'offline') {
                    logMessage('err', 'COMUNICACIÓN', 'Sin comunicación con el móvil. Se conserva la última posición válida.');
                }
                lastCoverageState = coverageState;
            }
            preflightPassed = Boolean(data.preflight_passed);
            videoConfirmed = Boolean(data.video_confirmed);
            testModeEnabled = Boolean(data.test_mode);
            updateTestModeUI();
            if (preflightPassed) {
                checks.movil = true;
                checks.lora_telemetria = true;
                checks.aprs_lora = true;
                checks.battery = true;
                checks.sensors = true;
                checks.gps = true;
                checks.camera_foto = true;
                updateChecklistUI('chk-movil', 'ok', 'CONFIRMADO');
                updateChecklistUI('chk-lora', 'ok', 'CONFIRMADO');
                updateChecklistUI('chk-aprs-lora', 'ok', 'CONFIRMADO');
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
            if (isSequenceRunning) {
                const step = testSteps[currentStepIndex];
                if (step && step.check()) handleStepSuccess();
            }
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

    if (estado === 'espera' || estado === 'armando' || estado === 'armada' || estado === 'aborto_solicitado') {
        p1.className = 'phase-card active';
        currentPhase = 1;
    } else if (estado === 'cuenta_atras') {
        p2.className = 'phase-card active';
        currentPhase = 2;
    } else if (estado === 'lanzamiento_solicitado' || estado === 'lanzado') {
        p3.className = 'phase-card active';
        currentPhase = 3;
    } else if (estado === 'recuperacion_solicitada' || estado === 'recuperacion' || estado === 'recuperacion_forzada' || estado === 'finalizada') {
        p4.className = 'phase-card active';
        currentPhase = 4;
    }
}

// Polling activo del estado del servidor
setInterval(pollLaunchStatus, 2000);
