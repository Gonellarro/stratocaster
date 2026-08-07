let client = null;
let lastSondaPing = 0;
let lastLoraPing = 0;
let lastMeshPing = 0;
let streamActive = false;
let isTesting = false;
let currentPhase = 1;
let mapCentered = false;
let checklistPassed = false;
let preflightPassed = false;
let videoConfirmed = false;
let videoPreviewReady = false;
let videoPreviewTimer = null;
let videoPreviewInProgress = false;
let lastCoverageState = 'unknown';
let loraTestStartedAt = 0;
let mobileOnline = false;
let loraOnline = false;
let landingTransitionRequested = false;

// Checklist local status variables (Todas en false hasta ejecutar comprobación explícita)
let checks = {
    movil: false,
    lora_telemetria: false,
    camera_foto: false,
    camera_video: false,
    battery: false,
    sensors: false,
    gps: false
};

// Secuenciador de pruebas pre-vuelo
let currentStepIndex = -1;
let currentRetry = 0;
let stepTimeoutTimer = null;
let isSequenceRunning = false;
let stepAdvancing = false;

// Estructura de Misión
let mission = {
    id: 'MISIÓN_' + new Date().toISOString().slice(0,10).replace(/-/g, '_') + '_001',
    start: '--',
    state: 'espera',
    startTimestamp: 0
};

// Inicializar ID en UI
const missionIdCard = document.getElementById('mission-id-card');
if (missionIdCard) {
    missionIdCard.textContent = mission.id;
}
