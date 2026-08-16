// Solo las comprobaciones del MÓVIL son secuenciales: cada orden depende
// de la respuesta anterior. Las dos radios se comprueban en paralelo.
const testSteps = [
    {
        id: 'chk-movil',
        name: 'Móvil (Android)',
        run: () => { sendCommand('get_status'); },
        check: () => checks.movil,
        // El acuse status_received solo confirma que llegó la orden. El paso
        // termina cuando llega el diagnóstico completo (batería, sensor y GPS).
        timeout: 30000,
        retries: 1,
        critical: true
    },
    {
        id: 'chk-battery',
        name: 'Batería Móvil',
        run: () => {},
        check: () => checks.battery,
        timeout: 30000,
        retries: 1
    },
    {
        id: 'chk-sensors',
        name: 'Sensores Sonda',
        run: () => {},
        check: () => checks.sensors,
        timeout: 30000,
        retries: 1
    },
    {
        id: 'chk-gps',
        name: 'GPS Sonda',
        run: () => { sendCommand('init_gps'); },
        check: () => checks.gps,
        // El móvil puede requerir hasta 45 s para adquirir un fix GNSS. Se
        // deja margen para que el acuse gps_ok llegue antes del timeout web.
        timeout: 60000,
        retries: 1
    },
    {
        id: 'chk-foto',
        name: 'Cámara (Foto)',
        run: () => { sendCommand('test_photo'); },
        check: () => checks.camera_foto,
        timeout: 30000,
        retries: 1
    }
];

// Orquestador: móvil secuencial + dos enlaces LoRa en paralelo.
function runSelfTest() {
    if (isSequenceRunning) return;
    isSequenceRunning = true;
    loraTestStartedAt = Date.now();
    aprsLoraTestStartedAt = Date.now();
    mobileChecksFinished = false;
    mobileChecksPassed = false;
    loraRadioCheckFinished = false;
    aprsRadioCheckFinished = false;
    clearTimeout(loraRadioCheckTimer);
    clearTimeout(aprsRadioCheckTimer);
    
    // Resetear estados locales
    checks.movil = false;
    checks.lora_telemetria = false;
    checks.aprs_lora = false;
    checks.camera_foto = false;
    checks.camera_video = false;
    checks.battery = false;
    checks.sensors = false;
    checks.gps = false;
    preflightPassed = false;
    videoConfirmed = false;
    checklistPassed = false;

    resetChecklistUI();
    
    currentStepIndex = 0;
    currentRetry = 0;
    stepAdvancing = false;
    
    const btn = document.getElementById('btn-test-systems');
    if (btn) {
        btn.textContent = 'COMPROBANDO SISTEMAS...';
        btn.className = 'btn secondary';
        btn.disabled = true;
    }

    logMessage('info', 'TEST', 'Iniciando móvil secuencial y comprobaciones LoRa en paralelo...');
    startRadioChecks();
    executeCurrentStep();
}

function executeCurrentStep() {
    if (currentStepIndex >= testSteps.length) {
        mobileChecksFinished = true;
        mobileChecksPassed = true;
        logMessage('ok', 'MÓVIL', 'Comprobaciones secuenciales del móvil completadas.');
        finishSelfTestIfComplete();
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
    // Un acuse y su resultado pueden llegar casi juntos. Solo el primero
    // puede completar el paso actual.
    if (stepAdvancing) return;
    stepAdvancing = true;
    clearTimeout(stepTimeoutTimer);
    const step = testSteps[currentStepIndex];
    if (!step) return;
    
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
    
    setTimeout(() => {
        currentStepIndex++;
        currentRetry = 0;
        stepAdvancing = false;
        executeCurrentStep();
    }, 500);
}

function handleStepTimeout() {
    if (stepAdvancing) return;
    const step = testSteps[currentStepIndex];
    if (!step) {
        clearTimeout(stepTimeoutTimer);
        return;
    }
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

        stopSelfTestOnFailure();
    }
}

function stopSelfTestOnFailure() {
    clearTimeout(stepTimeoutTimer);
    stepAdvancing = false;
    mobileChecksFinished = true;
    mobileChecksPassed = false;
    preflightPassed = false;
    checklistPassed = false;
    logMessage('err', 'MÓVIL', 'La secuencia móvil no se completó. Las comprobaciones LoRa continúan.');
    finishSelfTestIfComplete();
}

function startRadioChecks() {
    updateChecklistUI('chk-lora', 'testing', 'Esperando trama nueva...');
    updateChecklistUI('chk-aprs-lora', 'testing', 'Esperando posición y sensores...');

    loraRadioCheckTimer = setTimeout(() => completeRadioCheck('lora', false), 120000);
    aprsRadioCheckTimer = setTimeout(() => completeRadioCheck('aprs', false), 120000);
}

function completeRadioCheck(kind, passed) {
    const isLora = kind === 'lora';
    if (isLora ? loraRadioCheckFinished : aprsRadioCheckFinished) return;

    if (isLora) {
        loraRadioCheckFinished = true;
        clearTimeout(loraRadioCheckTimer);
        if (passed) {
            updateChecklistUI('chk-lora', 'ok', 'CONFIRMADO');
            logMessage('ok', 'LORA', 'Enlace LoRa confirmado.');
        } else {
            checks.lora_telemetria = false;
            updateChecklistUI('chk-lora', 'ko', 'ERROR (KO)');
            logMessage('err', 'LORA', 'No se recibió una trama LoRa durante 2 minutos.');
        }
    } else {
        aprsRadioCheckFinished = true;
        clearTimeout(aprsRadioCheckTimer);
        if (passed) {
            updateChecklistUI('chk-aprs-lora', 'ok', aprsChecklistLabel());
            logMessage('ok', 'LORA APRS', 'Posición, temperatura y presión confirmadas.');
        } else {
            checks.aprs_lora = false;
            updateChecklistUI('chk-aprs-lora', 'ko', 'ERROR (KO)');
            logMessage('err', 'LORA APRS', 'No se recibieron todos los datos APRS durante 2 minutos.');
        }
    }
    finishSelfTestIfComplete();
}

function finishSelfTestIfComplete() {
    if (!mobileChecksFinished || !loraRadioCheckFinished || !aprsRadioCheckFinished) return;

    isSequenceRunning = false;
    const passed = mobileChecksPassed && checks.movil && checks.battery && checks.sensors &&
        checks.gps && checks.camera_foto && checks.lora_telemetria && checks.aprs_lora;
    const btn = document.getElementById('btn-test-systems');
    if (btn) {
        btn.textContent = passed ? 'SISTEMAS COMPROBADOS' : 'REINTENTAR COMPROBACIONES';
        btn.className = 'btn primary';
        btn.disabled = false;
    }
    if (passed) {
        logMessage('ok', 'TEST', 'Todas las comprobaciones técnicas se han completado.');
        tryApprovePreflight();
    } else {
        logMessage('err', 'TEST', 'Hay comprobaciones pendientes o fallidas. No se habilita el pre-vuelo.');
    }
    validateChecklist();
}

function resetChecklistUI() {
    const ids = ['chk-movil', 'chk-lora', 'chk-aprs-lora', 'chk-gps', 'chk-battery', 'chk-sensors', 'chk-foto', 'chk-video'];
    ids.forEach(id => {
        const item = document.getElementById(id);
        if (item) item.className = 'checklist-item ko';
        const val = document.getElementById(id + '-val');
        if (val) val.textContent = 'Sin Verificar';
    });
    
    checklistPassed = false;
    stepAdvancing = false;
    checks.movil = false;
    checks.lora_telemetria = false;
    checks.aprs_lora = false;
    checks.camera_foto = false;
    checks.camera_video = false;
    checks.battery = false;
    checks.sensors = false;
    checks.gps = false;
    preflightPassed = false;
    videoConfirmed = false;
    checklistPassed = false;
    if (typeof updatePreflightSummary === 'function') updatePreflightSummary();
}

// Vigilante de Enlaces (Heartbeat Watchdog)
setInterval(() => {
    const now = Date.now();
    
    // LoRa Telemetría (timeout de 120s / 2 minutos para soportar cadencias de radio espaciadas)
    if (now - lastLoraPing > 120000) {
        loraOnline = false;
        updateLinkState('lora', false);
        if (lastLoraPing > 0) logMessage('err', 'ENLACE', 'Receptor LoRa sin datos por más de 2 minutos.');
    } else if (lastLoraPing > 0) {
        loraOnline = true;
        updateLinkState('lora', true);
    }

    updateGeneralStatusLarge();
    validateChecklist();
}, 4000);

function tryApprovePreflight() {
    if (!isSequenceRunning && checks.movil && checks.lora_telemetria && checks.aprs_lora && checks.gps &&
        checks.battery && checks.sensors && checks.camera_foto) {
        preflightPassed = true;
        checklistPassed = true;
        fetch('/control_lanzamiento', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'preflight_ok'})
        }).catch(() => logMessage('err', 'MISIÓN', 'No se pudo registrar el pre-vuelo en el servidor.'));
        logMessage('ok', 'TEST', 'Pre-vuelo aprobado. Ahora hay que verificar el vídeo en OBS.');
    }
}
