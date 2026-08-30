#!/usr/bin/env python3
"""Exporta telemetría de InfluxDB a un KML o KMZ para Google Earth.

No necesita paquetes externos. Lee INFLUX_TOKEN, INFLUX_ORG e INFLUX_BUCKET
del entorno o de docker-TIG/.env.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / "docker-TIG" / ".env"
LOCAL_TIMEZONE = ZoneInfo("Europe/Madrid")


def load_env_file(path: Path) -> dict[str, str]:
    """Lee el formato simple KEY=VALUE usado por Docker Compose."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def parse_time(value: str) -> datetime:
    """Convierte una fecha ISO; sin zona se interpreta como Europe/Madrid."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def flux_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def build_flux(bucket: str, start: datetime, stop: datetime) -> str:
    return f'''from(bucket: {json.dumps(bucket)})
  |> range(start: time(v: {json.dumps(flux_timestamp(start))}), stop: time(v: {json.dumps(flux_timestamp(stop))}))
  |> filter(fn: (r) =>
    r["topic"] == "gps/data" or
    (r["subsystem"] == "mobile" and r["data_type"] == "telemetry") or
    (r["subsystem"] == "lora" and r["data_type"] == "telemetry")
  )
  |> filter(fn: (r) => r["_field"] == "lat" or r["_field"] == "lng" or r["_field"] == "altitude" or r["_field"] == "accuracy")
  |> pivot(rowKey: ["_time", "topic", "subsystem", "device_id"], columnKey: ["_field"], valueColumn: "_value")
  |> filter(fn: (r) => exists r.lat and exists r.lng)
  |> keep(columns: ["_time", "topic", "subsystem", "device_id", "lat", "lng", "altitude", "accuracy"])
  |> sort(columns: ["_time"])
'''


def query_influx(url: str, org: str, token: str, flux: str) -> list[dict[str, str]]:
    body = json.dumps(
        {
            "query": flux,
            "type": "flux",
            "dialect": {"annotations": [], "header": True, "delimiter": ","},
        }
    ).encode("utf-8")
    endpoint = f"{url.rstrip('/')}/api/v2/query?org={urllib.parse.quote(org, safe='')}"
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "text/csv",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"InfluxDB respondió HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"No se pudo conectar con InfluxDB: {error.reason}") from error

    lines = [line for line in content.splitlines() if line and not line.startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def number(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def source_name(row: dict[str, str]) -> str:
    """Clasifica los tres enlaces igual que el dashboard de Grafana."""
    device_id = row.get("device_id", "")
    topic = row.get("topic", "")
    if topic == "sonda/lora/EA2FMQ-8/telemetry" or device_id == "EA2FMQ-8":
        return "aprs"
    if row.get("subsystem") == "mobile":
        return "mobile"
    return "lora"


def group_points(
    rows: list[dict[str, str]], selected_source: str
) -> dict[tuple[str, str], list[dict[str, object]]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        lat = number(row.get("lat"), float("nan"))
        lng = number(row.get("lng"), float("nan"))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        source = source_name(row)
        if selected_source != "all" and source != selected_source:
            continue
        device_id = row.get("device_id") or {
            "mobile": "Móvil 4G",
            "lora": "LoRa ESP32",
            "aprs": "LoRa APRS",
        }[source]
        groups[(source, device_id)].append(
            {
                "time": row["_time"],
                "lat": lat,
                "lng": lng,
                "altitude": number(row.get("altitude")),
                "accuracy": number(row.get("accuracy"), float("nan")),
            }
        )
    return groups


def xml(value: object) -> str:
    return xml_escape(str(value))


def kml_color(source: str) -> str:
    # KML usa el orden alfa-azul-verde-rojo (aabbggrr).
    return {
        "mobile": "ffffff00",  # Cian
        "lora": "ff0000ff",  # Rojo
        "aprs": "ff008000",  # Verde
    }[source]


def source_label(source: str) -> str:
    return {
        "mobile": "Móvil 4G",
        "lora": "LoRa ESP32",
        "aprs": "LoRa APRS",
    }[source]


def make_kml(groups: dict[tuple[str, str], list[dict[str, object]]], name: str) -> str:
    folders: list[str] = []
    for (source, device_id), points in sorted(groups.items()):
        style_id = f"{source}-{device_id}".replace(" ", "_")
        line_coords = "\n".join(
            f"          {point['lng']:.7f},{point['lat']:.7f},0"
            for point in points
        )
        start, end = points[0], points[-1]
        folders.append(
            f'''    <Folder>
      <name>{xml(source_label(source))} · {xml(device_id)}</name>
      <Style id="{xml(style_id)}"><LineStyle><color>{kml_color(source)}</color><width>4</width></LineStyle></Style>
      <Placemark>
        <name>Trayectoria {xml(device_id)} ({len(points)} puntos)</name>
        <styleUrl>#{xml(style_id)}</styleUrl>
        <description>Fuente: {xml(source_label(source))}. Desde {xml(start['time'])} hasta {xml(end['time'])}.</description>
        <LineString>
          <tessellate>1</tessellate>
          <altitudeMode>clampToGround</altitudeMode>
          <coordinates>
{line_coords}
          </coordinates>
        </LineString>
      </Placemark>
      <Placemark><name>Inicio · {xml(device_id)}</name><styleUrl>#{xml(style_id)}</styleUrl><Point><coordinates>{start['lng']:.7f},{start['lat']:.7f},{start['altitude']:.1f}</coordinates></Point></Placemark>
      <Placemark><name>Final · {xml(device_id)}</name><styleUrl>#{xml(style_id)}</styleUrl><Point><coordinates>{end['lng']:.7f},{end['lat']:.7f},{end['altitude']:.1f}</coordinates></Point></Placemark>
    </Folder>'''
        )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{xml(name)}</name>
{chr(10).join(folders)}
  </Document>
</kml>
'''


def default_output(start: datetime, stop: datetime, output_format: str) -> Path:
    local_start = start.astimezone(LOCAL_TIMEZONE).strftime("%Y%m%d_%H%M")
    local_stop = stop.astimezone(LOCAL_TIMEZONE).strftime("%H%M")
    return PROJECT_ROOT / "exports" / f"sonda_{local_start}_{local_stop}.{output_format}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta telemetría InfluxDB a KML/KMZ.")
    parser.add_argument("--start", default="2026-08-23T11:00:00+02:00", help="Inicio ISO 8601; sin zona equivale a Europe/Madrid.")
    parser.add_argument("--stop", default="2026-08-23T17:30:00+02:00", help="Fin ISO 8601; sin zona equivale a Europe/Madrid.")
    parser.add_argument(
        "--source",
        choices=("mobile", "lora", "aprs", "all"),
        default="all",
        help="Origen de las trazas.",
    )
    parser.add_argument("--format", choices=("kml", "kmz"), default="kmz")
    parser.add_argument("--output", type=Path, help="Archivo de salida.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE, help="Archivo .env de TIG.")
    parser.add_argument("--influx-url", default=os.environ.get("INFLUX_URL", "http://localhost:8086"))
    args = parser.parse_args()

    start, stop = parse_time(args.start), parse_time(args.stop)
    if stop <= start:
        parser.error("--stop debe ser posterior a --start")

    env = load_env_file(args.env_file)
    token = os.environ.get("INFLUX_TOKEN", env.get("INFLUX_TOKEN", ""))
    org = os.environ.get("INFLUX_ORG", env.get("INFLUX_ORG", ""))
    bucket = os.environ.get("INFLUX_BUCKET", env.get("INFLUX_BUCKET", ""))
    if not all((token, org, bucket)):
        parser.error("Faltan INFLUX_TOKEN, INFLUX_ORG o INFLUX_BUCKET en el entorno o en el .env indicado")

    rows = query_influx(args.influx_url, org, token, build_flux(bucket, start, stop))
    groups = group_points(rows, args.source)
    if not groups:
        print("No se encontraron posiciones válidas en el intervalo indicado.", file=sys.stderr)
        return 2

    output = args.output or default_output(start, stop, args.format)
    output.parent.mkdir(parents=True, exist_ok=True)
    kml = make_kml(groups, f"Sonda · {args.start} a {args.stop}")
    if args.format == "kmz":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("doc.kml", kml)
    else:
        output.write_text(kml, encoding="utf-8")

    total = sum(len(points) for points in groups.values())
    print(f"Exportados {total} puntos de {len(groups)} trazas a {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
