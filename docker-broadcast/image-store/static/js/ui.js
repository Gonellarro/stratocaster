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
            badge.textContent = 'Desconectado';
            badge.className = 'link-badge disconnected';
        }
    }
}

function updateGeneralStatusLarge() {
    const large = document.getElementById('sys-status-large');
    if (!large) return;
    
    let disconnectedCount = 0;
    if (!checks.movil) disconnectedCount++;
    
    if (disconnectedCount === 0) {
        large.textContent = 'OK';
        large.className = 'header-pill';
    } else {
        large.textContent = 'ALERTA';
        large.className = 'header-pill alarm';
    }
}

function switchCameraTab(tabName) {
    const tabFoto = document.getElementById('tab-foto');
    const tabVideo = document.getElementById('tab-video');
    const viewer = document.getElementById('camera-frame');
    const streamFrame = document.getElementById('video-stream');
    
    if (tabName === 'foto') {
        if (tabFoto) tabFoto.className = 'camera-tab active';
        if (tabVideo) tabVideo.className = 'camera-tab';
        if (viewer) viewer.className = 'camera-viewer';
        if (streamFrame) streamFrame.src = ""; // limpiar para no consumir datos
    } else {
        if (tabFoto) tabFoto.className = 'camera-tab';
        if (tabVideo) tabVideo.className = 'camera-tab active';
        if (viewer) viewer.className = 'camera-viewer video-mode';
        
        // Asignar el stream WebRTC local/P2P matching el ID de la sonda
        if (streamFrame) streamFrame.src = "https://vdo.ninja/?view=sonda_stratocaster&clean";
    }
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
