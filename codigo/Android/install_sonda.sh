#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"

if ! command -v pkg >/dev/null 2>&1; then
    echo "[ERROR] Este instalador debe ejecutarse dentro de Termux."
    exit 1
fi

echo "[INFO] Actualizando índices de paquetes..."
pkg update

mapfile -t PACKAGES < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$REQUIREMENTS_FILE")
echo "[INFO] Instalando dependencias: ${PACKAGES[*]}"
pkg install -y "${PACKAGES[@]}"

echo "[INFO] Preparando almacenamiento compartido..."
termux-setup-storage || true
mkdir -p "$HOME/sonidos"

echo
echo "[ATENCIÓN] Debes instalar también la aplicación Android 'Termux:API'"
echo "           desde la misma fuente que Termux (preferiblemente F-Droid)."
echo "           Después, concede permisos de ubicación, cámara y audio."
echo "           Copia ~/sonidos/alarma_recuperacion.mp3: se usará para la"
echo "           prueba de audio y como baliza de recuperación."
echo
echo "[OK] Instalación de paquetes completada."
