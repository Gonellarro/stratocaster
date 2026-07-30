// Obtener el identificador del dispositivo a controlar de los parámetros de la URL
const urlParams = new URLSearchParams(window.location.search);
const targetDeviceID = urlParams.get('device_id') || 'movil_sonda_1';

function sendCommand(cmdName) {
    if (!client || !client.connected) return;
    const payload = JSON.stringify({ cmd: cmdName });
    client.publish(`sonda/mobile/${targetDeviceID}/command`, payload);
    console.log(`MQTT Publish sonda/mobile/${targetDeviceID}/command:`, cmdName);
}

// Inicialización de Conexión MQTT
const serverIP = window.location.hostname;
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

// Si accedemos por HTTPS (producción/internet), pasamos por Nginx Proxy Manager en /mqtt (puerto 443).
// Si accedemos por HTTP (IP local), conectamos directo al puerto 9001.
const mqttUrl = protocol === 'wss:' ? `wss://${serverIP}/mqtt` : `ws://${serverIP}:9001`;

const mqttUser = (window.CONFIG && window.CONFIG.mqttUser) || urlParams.get('mqtt_user') || '';
const mqttPass = (window.CONFIG && window.CONFIG.mqttPass) || urlParams.get('mqtt_pass') || '';

// Inicializar checklist en estado estrictamente rojo (Sin Verificar) al cargar
if (typeof resetChecklistUI === 'function') {
    resetChecklistUI();
}

logMessage('info', 'MQTT', 'Conectando a ' + mqttUrl + '...');
client = mqtt.connect(mqttUrl, {
    username: mqttUser,
    password: mqttPass
});

client.on('connect', () => {
    logMessage('ok', 'MQTT', 'Conectado al Broker MQTT.');
    
    // Suscripciones dinámicas específicas del dispositivo seleccionado en el control
    client.subscribe(`sonda/mobile/${targetDeviceID}/status`);
    client.subscribe(`sonda/mobile/${targetDeviceID}/camera`);
    client.subscribe(`sonda/mobile/${targetDeviceID}/telemetry`);
    
    // Suscripciones de telemetría de radio generales (LoRa y Mesh)
    client.subscribe('sonda/lora/+/telemetry');
    client.subscribe('sonda/mesh/+/telemetry');
    client.subscribe('gps/data');
    
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
    
    const topicParts = topic.split('/');
    
    // 1. Mensajes específicos del móvil que estamos controlando/monitoreando
    if (topic === `sonda/mobile/${targetDeviceID}/status`) {
        lastSondaPing = Date.now();
        checks.movil = true;
        updateLinkState('movil', true);
        
        if (payload.status === 'diagnostico') {
            handleSondaDiagnostics(payload);
        } else {
            handleSondaEvent(payload);
        }
    } 
    else if (topic === `sonda/mobile/${targetDeviceID}/telemetry`) {
        lastSondaPing = Date.now();
        checks.movil = true;
        updateLinkState('movil', true);
        handleMobileTelemetry(payload);
    }
    else if (topic === `sonda/mobile/${targetDeviceID}/camera`) {
        lastSondaPing = Date.now();
        checks.movil = true;
        updateLinkState('movil', true);
        handleCameraEvent(payload);
    }
    // 2. Mensajes de receptor LoRa (estructura estandarizada sonda/lora/+/telemetry o legacy gps/data)
    else if ((topicParts[0] === 'sonda' && topicParts[1] === 'lora' && topicParts[3] === 'telemetry') || topic === 'gps/data') {
        lastLoraPing = Date.now();
        checks.lora_telemetria = true;
        updateLinkState('lora', true);
        handleLoraTelemetry(payload);
    }
    // 3. Mensajes de Meshtastic (el ID de nodo se extrae del topic)
    else if (topicParts[0] === 'sonda' && topicParts[1] === 'mesh' && topicParts[3] === 'telemetry') {
        lastMeshPing = Date.now();
        checks.lora_meshtastic = true;
        updateLinkState('meshtastic', true);
        const nodeId = parseInt(topicParts[2]) || payload.node_id;
        handleMeshtasticEvent(payload, nodeId);
    }
    
    // Si la secuencia de autotest está activa, comprobar éxito del paso actual
    if (isSequenceRunning) {
        const step = testSteps[currentStepIndex];
        if (step && step.check()) {
            handleStepSuccess();
        }
    }
});
