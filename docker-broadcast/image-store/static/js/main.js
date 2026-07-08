// MQTT Client Connection and Message Router (Orchestrator)

function sendCommand(cmdName) {
    if (!client || !client.connected) return;
    const payload = JSON.stringify({ cmd: cmdName });
    client.publish('sonda/comando', payload);
    console.log('MQTT Publish sonda/comando:', cmdName);
}

// Inicialización de Conexión MQTT
const serverIP = window.location.hostname;
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

// Si accedemos por HTTPS (producción/internet), pasamos por Nginx Proxy Manager en /mqtt (puerto 443).
// Si accedemos por HTTP (IP local), conectamos directo al puerto 9001.
const mqttUrl = protocol === 'wss:' ? `wss://${serverIP}/mqtt` : `ws://${serverIP}:9001`;

logMessage('info', 'MQTT', 'Conectando a ' + mqttUrl + '...');
client = mqtt.connect(mqttUrl, {
    username: 'admin',
    password: 'AWLCxdfGxwohHF2qpScJLK9AbRAFxD'
});

client.on('connect', () => {
    logMessage('ok', 'MQTT', 'Conectado al Broker MQTT.');
    client.subscribe('sonda/status');
    client.subscribe('sonda/camera');
    client.subscribe('gps/data');
    client.subscribe('sonda/meshtastic');
    
    // Solicitar primer reporte de estado
    sendCommand('get_status');
});

client.on('message', (topic, message) => {
    let payload;
    try {
        payload = JSON.parse(message.toString());
    } catch (e) {
        console.error('Error al decodificar mensaje JSON en MQTT:', e);
        return;
    }
    
    if (topic === 'sonda/status') {
        lastSondaPing = Date.now();
        checks.movil = true;
        updateLinkState('movil', true);
        
        if (payload.status === 'diagnostico') {
            handleSondaDiagnostics(payload);
        } else {
            handleSondaEvent(payload);
        }
    } 
    else if (topic === 'gps/data') {
        if (payload.accuracy !== undefined) {
            lastSondaPing = Date.now();
            checks.movil = true;
            updateLinkState('movil', true);
            handleMobileTelemetry(payload);
        } else {
            lastLoraPing = Date.now();
            checks.lora_telemetria = true;
            updateLinkState('lora', true);
            handleLoraTelemetry(payload);
        }
    }
    else if (topic === 'sonda/camera') {
        lastSondaPing = Date.now();
        updateLinkState('movil', true);
        handleCameraEvent(payload);
    }
    else if (topic === 'sonda/meshtastic') {
        lastMeshPing = Date.now();
        checks.lora_meshtastic = true;
        updateLinkState('meshtastic', true);
        handleMeshtasticEvent(payload);
    }
    
    // Si la secuencia de autotest está activa, comprobar éxito del paso actual
    if (isSequenceRunning) {
        const step = testSteps[currentStepIndex];
        if (step && step.check()) {
            handleStepSuccess();
        }
    }
});
