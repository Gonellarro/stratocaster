#!/usr/bin/env python3
"""Exporta telemetría de InfluxDB a un KMZ animado para Google Earth Pro.

Es la variante temporal del exportador normal. Google Earth Pro de escritorio
admite gx:Track; Google Earth web no. No necesita paquetes externos.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from export_influx_kmz import (
    DEFAULT_ENV_FILE,
    LOCAL_TIMEZONE,
    build_flux,
    group_points,
    kml_color,
    load_env_file,
    parse_time,
    query_influx,
    source_label,
    xml,
)


def make_temporal_kml(groups: dict[tuple[str, str], list[dict[str, object]]], name: str) -> str:
    """Genera un KML con un gx:Track por dispositivo.

    Google Earth Pro espera los elementos <when> y <gx:coord> intercalados;
    mantenerlos emparejados evita que el tiempo se desincronice de la posición.
    """
    folders: list[str] = []
    for (source, device_id), points in sorted(groups.items()):
        style_id = f"{source}-{device_id}".replace(" ", "_")
        track = "\n".join(
            f"          <when>{xml(point['time'])}</when>\n"
            f"          <gx:coord>{point['lng']:.7f} {point['lat']:.7f} {point['altitude']:.1f}</gx:coord>"
            for point in points
        )
        start, end = points[0], points[-1]
        folders.append(
            f'''    <Folder>
      <name>{xml(source_label(source))} · {xml(device_id)}</name>
      <Placemark>
        <name>Trayectoria temporal · {xml(device_id)} ({len(points)} puntos)</name>
        <Style id="{xml(style_id)}"><LineStyle><color>{kml_color(source)}</color><width>4</width></LineStyle></Style>
        <description>Desde {xml(start['time'])} hasta {xml(end['time'])}. Pulsa Play en Google Earth Pro.</description>
        <gx:Track>
          <altitudeMode>absolute</altitudeMode>
{track}
        </gx:Track>
      </Placemark>
      <Placemark><name>Inicio · {xml(device_id)}</name><Point><altitudeMode>absolute</altitudeMode><coordinates>{start['lng']:.7f},{start['lat']:.7f},{start['altitude']:.1f}</coordinates></Point></Placemark>
      <Placemark><name>Final · {xml(device_id)}</name><Point><altitudeMode>absolute</altitudeMode><coordinates>{end['lng']:.7f},{end['lat']:.7f},{end['altitude']:.1f}</coordinates></Point></Placemark>
    </Folder>'''
        )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>{xml(name)}</name>
{chr(10).join(folders)}
  </Document>
</kml>
'''


def default_output(start, stop) -> Path:
    local_start = start.astimezone(LOCAL_TIMEZONE).strftime("%Y%m%d_%H%M")
    local_stop = stop.astimezone(LOCAL_TIMEZONE).strftime("%H%M")
    return Path("exports") / f"sonda_{local_start}_{local_stop}_temporal.kmz"


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta telemetría a un KMZ animado para Google Earth Pro.")
    parser.add_argument("--start", default="2026-08-23T11:00:00+02:00")
    parser.add_argument("--stop", default="2026-08-23T17:30:00+02:00")
    parser.add_argument("--source", choices=("mobile", "lora", "aprs", "all"), default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--influx-url", default="http://localhost:8086")
    args = parser.parse_args()

    start, stop = parse_time(args.start), parse_time(args.stop)
    if stop <= start:
        parser.error("--stop debe ser posterior a --start")

    env = load_env_file(args.env_file)
    import os

    token = os.environ.get("INFLUX_TOKEN", env.get("INFLUX_TOKEN", ""))
    org = os.environ.get("INFLUX_ORG", env.get("INFLUX_ORG", ""))
    bucket = os.environ.get("INFLUX_BUCKET", env.get("INFLUX_BUCKET", ""))
    if not all((token, org, bucket)):
        parser.error("Faltan INFLUX_TOKEN, INFLUX_ORG o INFLUX_BUCKET en el entorno o en el .env indicado")

    rows = query_influx(args.influx_url, org, token, build_flux(bucket, start, stop))
    groups = group_points(rows, args.source)
    if not groups:
        print("No se encontraron posiciones válidas en el intervalo indicado.")
        return 2

    output = args.output or default_output(start, stop)
    output.parent.mkdir(parents=True, exist_ok=True)
    kml = make_temporal_kml(groups, f"Sonda · {args.start} a {args.stop}")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml)

    total = sum(len(points) for points in groups.values())
    print(f"Exportados {total} puntos temporales de {len(groups)} trazas a {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
