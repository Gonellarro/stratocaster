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
        timeout: 15000,
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
        timeout: 20000,
        retries: 1
    }
];

// Orquestador de Autotest Secuencial
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
    if (btn) {
        btn.textContent = '🤖 EJECUTANDO AUTO-TEST...';
        btn.className = 'btn btn-quick btn-outline-red';
        btn.style.color = 'var(--yellow-accent)';
        btn.style.borderColor = 'var(--yellow-accent)';
        btn.disabled = true;
    }

    logMessage('info', 'TEST', 'Iniciando secuencia de comprobación de sistemas paso a paso...');
    executeCurrentStep();
}

function executeCurrentStep() {
    if (currentStepIndex >= testSteps.length) {
        isSequenceRunning = false;
        checklistPassed = true;
        const btn = document.getElementById('btn-test-systems');
        if (btn) {
            btn.textContent = '🤖 SISTEMAS COMPROBADOS';
            btn.className = 'btn btn-accent';
            btn.style.color = '#000';
            btn.style.borderColor = 'none';
            btn.disabled = false;
        }
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
        executeCurrentStep();
    }, 500);
}

function handleStepTimeout() {
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
        if (item) item.className = 'checklist-item ko';
        const val = document.getElementById(id + '-val');
        if (val) val.textContent = 'Sin Verificar';
    });
    
    checklistPassed = false;
    checks.movil = false;
    checks.lora_telemetria = false;
    checks.lora_meshtastic = false;
    checks.camera_foto = false;
    checks.camera_video = false;
    checks.battery = false;
    checks.sensors = false;
    checks.gps = false;
    checks.audio = false;
}

// Vigilante de Enlaces (Heartbeat Watchdog)
setInterval(() => {
    const now = Date.now();
    
    // El timeout del teléfono debe ser más tolerante durante el lanzamiento/vuelo (35s)
    // que en rampa (20s) para soportar la transición de red (Wi-Fi a 4G) y el arranque del vídeo.
    const mobileTimeout = (mission.state !== 'espera') ? 35000 : 20000;
    
    if (now - lastSondaPing > mobileTimeout) {
        if (checks.movil) {
            checks.movil = false;
            updateLinkState('movil', false);
            logMessage('err', 'CONEXIÓN', 'Pérdida de cobertura de la Sonda Móvil.');
        }
    } else if (lastSondaPing > 0) {
        checks.movil = true;
        updateLinkState('movil', true);
    }
    
    // LoRa Telemetría (timeout de 120s / 2 minutos para soportar cadencias de radio espaciadas)
    if (now - lastLoraPing > 120000) {
        if (checks.lora_telemetria) {
            checks.lora_telemetria = false;
            updateLinkState('lora', false);
            logMessage('err', 'CONEXIÓN', 'Receptor LoRa de Telemetría fuera de línea (sin recepción por >2 min).');
        }
    } else if (lastLoraPing > 0) {
        checks.lora_telemetria = true;
        updateLinkState('lora', true);
    }

    updateGeneralStatusLarge();
    validateChecklist();
}, 4000);
