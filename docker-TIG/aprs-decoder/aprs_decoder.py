"""Convierte telemetría APRS raw de LoRa al formato JSON del sistema Sonda."""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import aprslib
import paho.mqtt.client as mqtt


MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
RAW_TOPIC = os.environ.get("APRS_RAW_TOPIC", "sonda/lora/aprs/telemetry/+")
OUTPUT_PREFIX = os.environ.get("OUTPUT_TOPIC_PREFIX", "sonda/lora")
CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "aprs_decoder")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("aprs-decoder")


@dataclass
class TelemetryDefinition:
    names: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    equations: list[tuple[float, float, float]] = field(default_factory=list)


class AprsDecoder:
    def __init__(self) -> None:
        self.definitions: dict[str, TelemetryDefinition] = {}

    @staticmethod
    def device_id(value: str) -> str:
        """Deja sólo caracteres seguros para emplear el indicativo en un topic."""
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", value.strip().upper())
        return safe or "unknown"

    def definition_for(self, device_id: str) -> TelemetryDefinition:
        return self.definitions.setdefault(device_id, TelemetryDefinition())

    def update_definition(self, device_id: str, parsed: dict[str, Any]) -> bool:
        definition = self.definition_for(device_id)
        changed = False
        if "tPARM" in parsed:
            definition.names = [str(value) for value in parsed["tPARM"]]
            changed = True
        if "tUNIT" in parsed:
            definition.units = [str(value) for value in parsed["tUNIT"]]
            changed = True
        if "tEQNS" in parsed:
            definition.equations = [tuple(map(float, values)) for values in parsed["tEQNS"]]
            changed = True
        if changed:
            LOG.info("Definición APRS actualizada para %s: canales=%s unidades=%s", device_id, definition.names, definition.units)
        return changed

    @staticmethod
    def numeric(value: Any) -> float | int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def channel_field(name: str, unit: str, index: int) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        unit_normalized = unit.lower().strip()
        if normalized in {"celsius", "temperature", "temp"} or "celsius" in normalized:
            return "temperature_c"
        if "press" in normalized or "atm" in normalized or unit_normalized in {"hpa", "mbar"}:
            return "pressure_hpa"
        return f"aprs_{normalized or f'channel_{index + 1}'}"

    def telemetry_fields(self, device_id: str, parsed: dict[str, Any]) -> dict[str, float | int]:
        telemetry = parsed.get("telemetry") or {}
        values = telemetry.get("vals") or []
        definition = self.definition_for(device_id)
        fields: dict[str, float | int] = {}

        sequence = self.numeric(telemetry.get("seq"))
        if sequence is not None:
            fields["aprs_sequence"] = sequence

        for index, raw_value in enumerate(values):
            value = self.numeric(raw_value)
            if value is None:
                continue
            if index < len(definition.equations):
                a, b, c = definition.equations[index]
                value = a * value * value + b * value + c
            name = definition.names[index] if index < len(definition.names) else ""
            unit = definition.units[index] if index < len(definition.units) else ""
            # APRS rellena los cinco canales analógicos, pero PARM/UNIT deja
            # vacíos los que el emisor no utiliza. No publicarlos en Influx.
            if definition.names and not name.strip() and not unit.strip():
                continue
            fields[self.channel_field(name, unit, index)] = value
        return fields

    def normalize(self, topic: str, raw_packet: str) -> tuple[str, dict[str, Any]] | None:
        try:
            parsed = aprslib.parse(raw_packet)
        except Exception as exc:  # aprslib expone distintas excepciones según formato.
            LOG.warning("Trama APRS no decodificable en %s: %s (%r)", topic, exc, raw_packet)
            return None

        topic_device = topic.rsplit("/", 1)[-1]
        device_id = self.device_id(str(parsed.get("from") or topic_device))
        self.update_definition(device_id, parsed)

        payload: dict[str, Any] = {"status": "aprs"}
        mappings = {
            "latitude": "lat",
            "longitude": "lng",
            "altitude": "altitude",
            "speed": "speed",
            "course": "course",
        }
        for source_key, target_key in mappings.items():
            value = self.numeric(parsed.get(source_key))
            if value is not None:
                payload[target_key] = value

        payload.update(self.telemetry_fields(device_id, parsed))
        if len(payload) == 1:
            # Los mensajes PARM/UNIT/EQNS sólo configuran el decodificador;
            # no añaden una fila vacía a InfluxDB.
            return None
        return f"{OUTPUT_PREFIX}/{device_id}/telemetry", payload


DECODER = AprsDecoder()


def on_connect(client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
    if getattr(reason_code, "is_failure", False):
        LOG.error("Conexión MQTT rechazada: %s", reason_code)
        return
    client.subscribe(RAW_TOPIC, qos=1)
    LOG.info("Suscrito a %s; publicando JSON normalizado bajo %s/<indicativo>/telemetry", RAW_TOPIC, OUTPUT_PREFIX)


def on_message(client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
    try:
        raw_packet = message.payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        raw_packet = message.payload.decode("latin-1").strip()
    decoded = DECODER.normalize(message.topic, raw_packet)
    if decoded is None:
        return
    output_topic, payload = decoded
    result = client.publish(output_topic, json.dumps(payload, separators=(",", ":")), qos=1, retain=False)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        LOG.error("No se pudo publicar %s: rc=%s", output_topic, result.rc)
        return
    LOG.info("%s → %s %s", message.topic, output_topic, payload)


def build_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    return client


def main() -> None:
    while True:
        client = build_client()
        try:
            LOG.info("Conectando al broker MQTT %s:%s", MQTT_HOST, MQTT_PORT)
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            client.loop_forever(retry_first_connection=True)
        except Exception as exc:
            LOG.warning("Conexión MQTT terminada: %s. Reintento en 5 s.", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
