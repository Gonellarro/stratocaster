// Gestión de Acciones de Lanzamiento y Secuencias REST
function readyLaunch() {
    logMessage('warn', 'MISIÓN', 'Preparando despegue: Armando la sonda e iniciando señal de vídeo...');
    
    // Enviar arm al móvil por MQTT para iniciar Fase 1
    sendCommand('arm');

    // Avisar a Flask para registrar el inicio de misión
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'armar' })
    }).then(validateChecklist);
}

function startCountdown() {
    logMessage('warn', 'MISIÓN', 'Iniciando la cuenta atrás para el lanzamiento en el HUD...');
    
    // Avisar a Flask para arrancar el segundero de la cuenta atrás
    fetch('/control_lanzamiento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'ok' })
    }).then(validateChecklist);
}

function abortLaunch() {
    logMessage('err', 'MISIÓN', '¡ALERTA! Secuencia de lanzamiento abortada por el operador.');
    
    // Detener vídeo en móvil y resetear script
    sendCommand('abort');

    // Reiniciar estados locales
    isTesting = false;
    checks.camera_foto = false;
    checks.camera_video = false;
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

function validateChecklist() {
    const btnReady = document.getElementById('btn-ready');
    const btnArm = document.getElementById('btn-arm');
    const btnAbort = document.getElementById('btn-abort');
    
    if (!btnReady || !btnArm || !btnAbort) return;

    // Checklist de despegue requiere obligatoriamente los checks del móvil y sus sensores completados:
    const isReady = checks.movil && checks.gps && checks.battery && checks.sensors && checks.audio && checks.camera_foto;
    
    // El botón de abortar siempre debe estar disponible si hay una misión en curso,
    // permitiendo abortar de emergencia incluso si se pierden las conexiones (isReady = false).
    if (mission.state === 'armando' || mission.state === 'cuenta_atras' || mission.state === 'lanzado') {
        btnAbort.disabled = false;
    } else {
        btnAbort.disabled = true;
    }

    // SI LA MISIÓN YA HA INICIADO (estado diferente de 'espera'):
    // Congelamos el estado de los controles. No evaluamos el checklist para no deshabilitar
    // los botones si la sonda pierde temporalmente cobertura (al apagar WiFi / cambiar a 4G).
    if (mission.state !== 'espera') {
        btnReady.disabled = true;
        if (mission.state === 'armando') {
            btnArm.disabled = false;
        } else {
            btnArm.disabled = true;
        }
        return; // Salir sin evaluar isReady
    }

    if (!isReady) {
        btnReady.disabled = true;
        btnArm.disabled = true;
    } else {
        btnReady.disabled = false;
        btnArm.disabled = true;
    }
}

function pollLaunchStatus() {
    fetch('/control_lanzamiento')
        .then(r => r.json())
        .then(data => {
            mission.state = data.estado;
            
            const stateCard = document.getElementById('mission-state-card');
            if (stateCard) {
                stateCard.textContent = data.estado.toUpperCase();
            }
            
            // Sincronizar Fases visuales
            updatePhaseIndicators(data.estado);

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

// Polling activo del estado del servidor
setInterval(pollLaunchStatus, 1000);
