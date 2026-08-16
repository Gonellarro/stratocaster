// Helpers de Interfaz de Usuario (UI)
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

    const summary = document.getElementById('preflight-summary');
    if (summary) {
        const checkIds = ['chk-movil', 'chk-lora', 'chk-aprs-lora', 'chk-gps', 'chk-battery', 'chk-sensors', 'chk-foto', 'chk-video'];
        const passed = checkIds.filter(checkId => document.getElementById(checkId)?.classList.contains('ok')).length;
        summary.textContent = `${passed}/8`;
    }
}

function updatePreflightSummary() {
    const summary = document.getElementById('preflight-summary');
    if (!summary) return;
    const ids = ['chk-movil', 'chk-lora', 'chk-aprs-lora', 'chk-gps', 'chk-battery', 'chk-sensors', 'chk-foto', 'chk-video'];
    summary.textContent = `${ids.filter(checkId => document.getElementById(checkId)?.classList.contains('ok')).length}/8`;
}

function updateLinkState(linkId, connected) {
    const badge = document.getElementById('link-' + linkId);
    
    if (connected) {
        if (badge) {
            badge.textContent = 'Conectado';
            badge.className = 'link-badge connected';
        }
        if (linkId === 'movil') {
            const lastPingEl = document.getElementById('sys-last-ping');
            if (lastPingEl) {
                lastPingEl.textContent = new Date().toLocaleTimeString();
            }
        }
    } else {
        if (badge) {
            badge.textContent = 'Sin comunicación';
            badge.className = 'link-badge disconnected';
        }
    }
}

function updateGeneralStatusLarge() {
    const large = document.getElementById('sys-status-large');
    if (!large) return;

    // La recuperación es un estado operativo cerrado, no una alarma de
    // comunicaciones aunque el móvil ya no tenga cobertura.
    if (mission.state === 'recuperacion') {
        large.textContent = 'RECUPERACIÓN';
        large.className = 'header-pill waiting';
        return;
    }
    if (mission.state === 'finalizada') {
        large.textContent = 'FINALIZADA';
        large.className = 'header-pill waiting';
        return;
    }

    // Al iniciar no hay todavía ningún enlace que declarar como perdido. La
    // alerta se reserva para una desconexión real tras haber tenido datos.
    if (mission.state === 'espera' && !mobileOnline && lastSondaPing === 0) {
        large.textContent = 'ESPERA';
        large.className = 'header-pill waiting';
        return;
    }
    
    let disconnectedCount = 0;
    if (!mobileOnline) disconnectedCount++;
    
    if (disconnectedCount === 0) {
        large.textContent = 'OK';
        large.className = 'header-pill';
    } else {
        large.textContent = 'ALERTA';
        large.className = 'header-pill alarm';
    }
}

function updateTestModeUI() {
    const toggle = document.getElementById('test-mode-toggle');
    const label = document.getElementById('test-mode-label');
    if (toggle) toggle.checked = testModeEnabled;
    if (label) {
        label.textContent = testModeEnabled ? 'ACTIVO' : 'NORMAL';
        label.className = 'test-mode-label' + (testModeEnabled ? ' active' : '');
    }
}

function switchCameraTab(tabName) {
    const streamFrame = document.getElementById('video-stream');
    // La consola ya no muestra fotografías. Se conserva esta función porque
    // la usan los eventos de cámara, pero solo actúa sobre el visor de vídeo.
    if (tabName !== 'video' || !streamFrame) return;
    const vdoUrl = (window.CONFIG && window.CONFIG.vdoViewUrl) || 'https://vdo.ninja/?view=sonda_stratocaster';
    if (streamFrame.src !== vdoUrl) {
        streamFrame.src = vdoUrl;
    }
}

function reloadVideoViewer() {
    const streamFrame = document.getElementById('video-stream');
    if (!streamFrame) return;
    const vdoUrl = (window.CONFIG && window.CONFIG.vdoViewUrl) || 'https://vdo.ninja/?view=sonda_stratocaster';
    streamFrame.src = '';
    window.setTimeout(() => {
        streamFrame.src = vdoUrl;
        switchCameraTab('video');
    }, 500);
}

function logMessage(level, tag, text) {
    const display = document.getElementById('log-display');
    if (!display) return;
    
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

function openGpsModal(data) {
    const modal = document.getElementById('gps-debug-modal');
    const pre = document.getElementById('gps-modal-raw-json');
    if (modal && pre) {
        pre.textContent = JSON.stringify(data, null, 2);
        modal.style.display = 'flex';
    }
}

function closeGpsModal() {
    const modal = document.getElementById('gps-debug-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function getWindDirection(deg) {
    const sectors = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    const index = Math.round(deg / 22.5) % 16;
    return sectors[index];
}
