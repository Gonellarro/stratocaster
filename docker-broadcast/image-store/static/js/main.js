// Obtener el identificador del dispositivo a controlar de los parámetros de la URL
const urlParams = new URLSearchParams(window.location.search);
const targetDeviceID = (window.CONFIG && window.CONFIG.deviceId) || urlParams.get('device_id') || 'movil_sonda_1';
const targetLoraDeviceID = (window.CONFIG && window.CONFIG.loraDeviceId) || 'rx_sonda';
const targetAprsLoraDeviceID = (window.CONFIG && window.CONFIG.aprsLoraDeviceId) || 'EA2FMQ-8';

function sendCommand(cmdName, extra = {}) {
    const commandId = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
    fetch('/device_command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cmd: cmdName, device_id: targetDeviceID, command_id: commandId, ...extra})
    }).then(async response => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${body.error || body.message || 'sin detalle'}`);
        console.log('Orden aceptada por Flask:', cmdName, commandId, body);
        logMessage('ok', 'COMANDO', `${cmdName} aceptado por Flask (${commandId})`);
    }).catch(error => logMessage('err', 'COMANDO', `No se pudo enviar ${cmdName}: ${error.message}`));
}

// Inicialización de Conexión MQTT
const serverIP = window.location.hostname;
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

// Si accedemos por HTTPS (producción/internet), pasamos por Nginx Proxy Manager en /mqtt (puerto 443).
// Si accedemos por HTTP (IP local), conectamos directo al puerto 9001.
const mqttUrl = protocol === 'wss:' ? `wss://${serverIP}/mqtt` : `ws://${serverIP}:9001`;

const mqttUser = (window.CONFIG && window.CONFIG.mqttUser) || urlParams.get('mqtt_user') || '';
const mqttPass = (window.CONFIG && window.CONFIG.mqttPass) || urlParams.get('mqtt_pass') || '';

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
    
    // Solo el receptor LoRa asignado a esta misión puede alimentar el control.
    client.subscribe(`sonda/lora/${targetLoraDeviceID}/telemetry`);
    client.subscribe(`sonda/lora/${targetAprsLoraDeviceID}/telemetry`);
    
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
        
        if (payload.status === 'diagnostico') {
            handleSondaDiagnostics(payload);
        } else {
            handleSondaEvent(payload);
        }
    } 
    else if (topic === `sonda/mobile/${targetDeviceID}/telemetry`) {
        lastSondaPing = Date.now();
        handleMobileTelemetry(payload);
    }
    else if (topic === `sonda/mobile/${targetDeviceID}/camera`) {
        lastSondaPing = Date.now();
        handleCameraEvent(payload);
    }
    // 2. Mensajes del receptor LoRa asignado a esta misión.
    else if (topic === `sonda/lora/${targetLoraDeviceID}/telemetry`) {
        lastLoraPing = Date.now();
        loraOnline = true;
        updateLinkState('lora', true);
        handleLoraTelemetry(payload);
    }
    else if (topic === `sonda/lora/${targetAprsLoraDeviceID}/telemetry`) {
        handleAprsLoraTelemetry(payload);
    }
    
    // Si la secuencia de autotest está activa, comprobar éxito del paso actual
    if (isSequenceRunning) {
        const step = testSteps[currentStepIndex];
        if (step && step.check()) {
            handleStepSuccess();
        }
    }
});

// La primera representación también procede del estado persistido en Flask.
// El navegador no crea ni reinicia una misión al cargarse.
pollLaunchStatus();
