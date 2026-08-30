// Inicialización del Mapa Leaflet
let map = L.map('map-container').setView([41.12345, 1.98765], 13);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
}).addTo(map);

// Capa Satélite
let satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri'
});

let baseLayers = {
    "Mapa": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
    "Satélite": satelliteLayer
};
L.control.layers(baseLayers).addTo(map);

// Marcadores neón y rutas (se añaden dinámicamente al recibir coordenadas válidas)
let markers = {
    movil: L.circleMarker([0, 0], { color: '#0891b2', fillColor: '#0891b2', fillOpacity: 0.85, radius: 8 }),
    lora: L.circleMarker([0, 0], { color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.85, radius: 8 })
};

let markerAdded = {
    movil: false,
    lora: false
};

// El mapa de control muestra la posición actual de cada enlace, no un trazado
// que pueda unir puntos de fuentes o momentos distintos.
let paths = {};

// Función para actualizar posición y trazar rutas
function updateMapCoordinates(type, lat, lng) {
    if (lat === null || lat === undefined || lat === 0 || lat === 'null' || isNaN(parseFloat(lat)) || isNaN(parseFloat(lng))) return;
    
    const latnum = parseFloat(lat);
    const lngnum = parseFloat(lng);
    if (latnum === 0 && lngnum === 0) return;
    
    const latlng = [latnum, lngnum];
    if (markers[type]) {
        markers[type].setLatLng(latlng);
        if (!markerAdded[type]) {
            markers[type].addTo(map);
            markerAdded[type] = true;
        }
    }
    
    // Auto-centrar en el primer paquete válido recibido de la sonda (vía Móvil o LoRa)
    if ((type === 'movil' || type === 'lora') && !mapCentered) {
        map.setView(latlng, 15);
        mapCentered = true;
    }
}
