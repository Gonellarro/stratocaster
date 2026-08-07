#!/data/data/com.termux/files/usr/bin/bash

# Lanzador aislado para pruebas. Mantiene intacto el sonda_loop.sh de producción
# y fuerza el uso de la configuración de staging.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export SONDA_CONFIG_FILE="$SCRIPT_DIR/sonda.env_staging"
exec "$SCRIPT_DIR/sonda_loop.sh" "$@"
