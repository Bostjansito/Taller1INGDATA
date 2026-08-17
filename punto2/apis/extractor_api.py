"""Extrae y normaliza datos del Mundial 2022 desde API-Football.

Uso:
    ../.venv/bin/python extractor_api.py
    ../.venv/bin/python extractor_api.py --actualizar

La ejecución normal reutiliza la caché JSON. ``--actualizar`` fuerza una
consulta nueva y debe usarse con cuidado debido a la cuota diaria de la API.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv


BASE_URL = "https://v3.football.api-sports.io"
COMPETENCIA_ID = 1
TEMPORADA = 2022
EXTRAIDO_POR = "emanuel"
DIRECTORIO = Path(__file__).resolve().parent
CACHE_DIR = DIRECTORIO / "cache"

COLUMNAS_EQUIPOS = [
    "equipo_id", "nombre_equipo", "codigo_equipo", "pais",
    "anio_fundacion", "es_seleccion_nacional", "logo_url",
    "competencia_id", "temporada", "fecha_extraccion", "extraido_por",
    "endpoint_origen",
]

COLUMNAS_PARTIDOS = [
    "partido_id", "competencia_id", "competencia_nombre", "temporada",
    "ronda", "fecha_partido", "zona_horaria", "estado_partido",
    "minuto_transcurrido", "arbitro", "estadio_id", "estadio_nombre",
    "estadio_ciudad", "equipo_local_id", "equipo_local_nombre",
    "equipo_visitante_id", "equipo_visitante_nombre", "gano_local",
    "gano_visitante", "goles_local", "goles_visitante", "penales_local",
    "penales_visitante", "fecha_extraccion", "extraido_por",
    "endpoint_origen",
]

COLUMNAS_CLASIFICACION = [
    "grupo", "posicion", "equipo_id", "nombre_equipo", "puntos",
    "partidos_jugados", "partidos_ganados", "partidos_empatados",
    "partidos_perdidos", "goles_favor", "goles_contra", "diferencia_gol",
    "forma_reciente", "estado_clasificacion", "descripcion_clasificacion",
    "fecha_actualizacion", "competencia_id", "temporada",
    "fecha_extraccion", "extraido_por", "endpoint_origen",
]


class ErrorAPI(RuntimeError):
    """Error controlado al consultar o validar API-Football."""


def _validar_cuerpo(cuerpo: Any, endpoint: str) -> dict[str, Any]:
    if not isinstance(cuerpo, dict):
        raise ErrorAPI(f"/{endpoint}: la respuesta no es un objeto JSON.")
    errores = cuerpo.get("errors")
    if errores:
        raise ErrorAPI(f"/{endpoint}: la API reportó errores: {errores}")
    respuesta = cuerpo.get("response")
    if not isinstance(respuesta, list):
        raise ErrorAPI(f"/{endpoint}: falta la lista 'response'.")
    if not respuesta:
        raise ErrorAPI(
            f"/{endpoint}: no se encontraron datos para league={COMPETENCIA_ID} "
            f"y season={TEMPORADA}."
        )
    paginacion = cuerpo.get("paging")
    if not isinstance(paginacion, dict):
        raise ErrorAPI(f"/{endpoint}: falta la información de paginación.")
    try:
        actual = int(paginacion["current"])
        total = int(paginacion["total"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorAPI(f"/{endpoint}: paginación inválida: {paginacion}") from exc
    if actual < 1 or total < actual:
        raise ErrorAPI(f"/{endpoint}: paginación incoherente: {paginacion}")
    return cuerpo


def consultar_endpoint(
    endpoint: str,
    api_key: str,
    actualizar: bool = False,
) -> list[dict[str, Any]]:
    """Consulta todas las páginas de un endpoint y conserva una caché local."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    elementos: list[dict[str, Any]] = []
    pagina = 1
    total_paginas = 1

    with requests.Session() as sesion:
        sesion.headers.update({"x-apisports-key": api_key})
        while pagina <= total_paginas:
            archivo_cache = CACHE_DIR / f"{endpoint}_pagina_{pagina}.json"
            origen = "caché"
            if archivo_cache.exists() and not actualizar:
                try:
                    cuerpo = json.loads(archivo_cache.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ErrorAPI(f"Caché dañada: {archivo_cache.name}") from exc
            else:
                origen = "API"
                try:
                    parametros = {
                        "league": COMPETENCIA_ID,
                        "season": TEMPORADA,
                    }
                    # Algunos endpoints no aceptan ``page`` cuando su respuesta
                    # no es paginada. Solo se envía tras descubrir más páginas.
                    if pagina > 1:
                        parametros["page"] = pagina
                    respuesta = sesion.get(
                        f"{BASE_URL}/{endpoint}",
                        params=parametros,
                        timeout=30,
                    )
                    respuesta.raise_for_status()
                    cuerpo = respuesta.json()
                except requests.RequestException as exc:
                    raise ErrorAPI(f"/{endpoint}: fallo HTTP o de conexión: {exc}") from exc
                except requests.JSONDecodeError as exc:
                    raise ErrorAPI(f"/{endpoint}: la respuesta no contiene JSON válido.") from exc

                cuerpo = _validar_cuerpo(cuerpo, endpoint)
                temporal = archivo_cache.with_suffix(".tmp")
                temporal.write_text(
                    json.dumps(cuerpo, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temporal.replace(archivo_cache)

            cuerpo = _validar_cuerpo(cuerpo, endpoint)
            elementos.extend(cuerpo["response"])
            total_paginas = int(cuerpo["paging"]["total"])
            print(
                f"/{endpoint}: página {pagina}/{total_paginas} leída desde {origen} "
                f"({len(cuerpo['response'])} registros)."
            )
            pagina += 1

    return elementos


def _convertir_enteros(df: pd.DataFrame, columnas: list[str]) -> None:
    for columna in columnas:
        df[columna] = pd.to_numeric(df[columna], errors="coerce").astype("Int64")


def _convertir_textos(df: pd.DataFrame, columnas: list[str]) -> None:
    for columna in columnas:
        df[columna] = df[columna].astype("string")


def normalizar_equipos(
    datos: list[dict[str, Any]], fecha_extraccion: datetime
) -> pd.DataFrame:
    filas = []
    for item in datos:
        team = item.get("team") or {}
        filas.append({
            "equipo_id": team.get("id"),
            "nombre_equipo": team.get("name"),
            "codigo_equipo": team.get("code"),
            "pais": team.get("country"),
            "anio_fundacion": team.get("founded"),
            "es_seleccion_nacional": team.get("national"),
            "logo_url": team.get("logo"),
            "competencia_id": COMPETENCIA_ID,
            "temporada": TEMPORADA,
            "fecha_extraccion": fecha_extraccion,
            "extraido_por": EXTRAIDO_POR,
            "endpoint_origen": "/teams",
        })

    df = pd.DataFrame(filas, columns=COLUMNAS_EQUIPOS)
    _convertir_enteros(df, ["equipo_id", "anio_fundacion", "competencia_id", "temporada"])
    _convertir_textos(
        df,
        ["nombre_equipo", "codigo_equipo", "pais", "logo_url", "extraido_por", "endpoint_origen"],
    )
    df["es_seleccion_nacional"] = df["es_seleccion_nacional"].astype("boolean")
    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], utc=True)
    return df.drop_duplicates(subset=["equipo_id"], keep="last").sort_values("nombre_equipo").reset_index(drop=True)


def normalizar_partidos(
    datos: list[dict[str, Any]], fecha_extraccion: datetime
) -> pd.DataFrame:
    filas = []
    for item in datos:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        goals = item.get("goals") or {}
        score = item.get("score") or {}
        penalty = score.get("penalty") or {}
        status = fixture.get("status") or {}
        venue = fixture.get("venue") or {}
        filas.append({
            "partido_id": fixture.get("id"),
            "competencia_id": league.get("id", COMPETENCIA_ID),
            "competencia_nombre": league.get("name"),
            "temporada": league.get("season", TEMPORADA),
            "ronda": league.get("round"),
            "fecha_partido": fixture.get("date"),
            "zona_horaria": fixture.get("timezone"),
            "estado_partido": status.get("long"),
            "minuto_transcurrido": status.get("elapsed"),
            "arbitro": fixture.get("referee"),
            "estadio_id": venue.get("id"),
            "estadio_nombre": venue.get("name"),
            "estadio_ciudad": venue.get("city"),
            "equipo_local_id": home.get("id"),
            "equipo_local_nombre": home.get("name"),
            "equipo_visitante_id": away.get("id"),
            "equipo_visitante_nombre": away.get("name"),
            "gano_local": home.get("winner") is True,
            "gano_visitante": away.get("winner") is True,
            "goles_local": goals.get("home"),
            "goles_visitante": goals.get("away"),
            "penales_local": penalty.get("home"),
            "penales_visitante": penalty.get("away"),
            "fecha_extraccion": fecha_extraccion,
            "extraido_por": EXTRAIDO_POR,
            "endpoint_origen": "/fixtures",
        })

    df = pd.DataFrame(filas, columns=COLUMNAS_PARTIDOS)
    _convertir_enteros(
        df,
        [
            "partido_id", "competencia_id", "temporada", "minuto_transcurrido",
            "estadio_id", "equipo_local_id", "equipo_visitante_id", "goles_local",
            "goles_visitante", "penales_local", "penales_visitante",
        ],
    )
    _convertir_textos(
        df,
        [
            "competencia_nombre", "ronda", "zona_horaria", "estado_partido", "arbitro",
            "estadio_nombre", "estadio_ciudad", "equipo_local_nombre",
            "equipo_visitante_nombre", "extraido_por", "endpoint_origen",
        ],
    )
    df["gano_local"] = df["gano_local"].astype("boolean")
    df["gano_visitante"] = df["gano_visitante"].astype("boolean")
    df["fecha_partido"] = pd.to_datetime(df["fecha_partido"], errors="coerce", utc=True)
    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], utc=True)
    return df.drop_duplicates(subset=["partido_id"], keep="last").sort_values("fecha_partido").reset_index(drop=True)


def normalizar_clasificacion(
    datos: list[dict[str, Any]], fecha_extraccion: datetime
) -> pd.DataFrame:
    filas = []
    for item in datos:
        league = item.get("league") or {}
        for grupo_standings in league.get("standings") or []:
            for posicion in grupo_standings:
                team = posicion.get("team") or {}
                total = posicion.get("all") or {}
                goles = total.get("goals") or {}
                filas.append({
                    "grupo": posicion.get("group"),
                    "posicion": posicion.get("rank"),
                    "equipo_id": team.get("id"),
                    "nombre_equipo": team.get("name"),
                    "puntos": posicion.get("points"),
                    "partidos_jugados": total.get("played"),
                    "partidos_ganados": total.get("win"),
                    "partidos_empatados": total.get("draw"),
                    "partidos_perdidos": total.get("lose"),
                    "goles_favor": goles.get("for"),
                    "goles_contra": goles.get("against"),
                    "diferencia_gol": posicion.get("goalsDiff"),
                    "forma_reciente": posicion.get("form"),
                    "estado_clasificacion": posicion.get("status"),
                    "descripcion_clasificacion": posicion.get("description"),
                    "fecha_actualizacion": posicion.get("update"),
                    "competencia_id": league.get("id", COMPETENCIA_ID),
                    "temporada": league.get("season", TEMPORADA),
                    "fecha_extraccion": fecha_extraccion,
                    "extraido_por": EXTRAIDO_POR,
                    "endpoint_origen": "/standings",
                })

    df = pd.DataFrame(filas, columns=COLUMNAS_CLASIFICACION)
    if df.empty:
        raise ErrorAPI("/standings: la respuesta no contiene filas de clasificación.")
    _convertir_enteros(
        df,
        [
            "posicion", "equipo_id", "puntos", "partidos_jugados",
            "partidos_ganados", "partidos_empatados", "partidos_perdidos",
            "goles_favor", "goles_contra", "diferencia_gol", "competencia_id", "temporada",
        ],
    )
    _convertir_textos(
        df,
        [
            "grupo", "nombre_equipo", "forma_reciente", "estado_clasificacion",
            "descripcion_clasificacion", "extraido_por", "endpoint_origen",
        ],
    )
    df["fecha_actualizacion"] = pd.to_datetime(df["fecha_actualizacion"], errors="coerce", utc=True)
    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], utc=True)
    return (
        df.drop_duplicates(subset=["grupo", "equipo_id"], keep="last")
        .sort_values(["grupo", "posicion"])
        .reset_index(drop=True)
    )


def _validar_dataframe(
    df: pd.DataFrame,
    columnas: list[str],
    claves: list[str],
    nombre: str,
) -> None:
    if df.empty:
        raise ValueError(f"{nombre}: el DataFrame está vacío.")
    if list(df.columns) != columnas:
        raise ValueError(f"{nombre}: las columnas no coinciden con el esquema requerido.")
    if df[claves].isna().any(axis=None):
        raise ValueError(f"{nombre}: existen claves nulas en {claves}.")
    if df.duplicated(subset=claves).any():
        raise ValueError(f"{nombre}: existen claves duplicadas en {claves}.")
    columnas_anidadas = [
        columna
        for columna in df.columns
        if df[columna].map(lambda valor: isinstance(valor, (list, dict))).any()
    ]
    if columnas_anidadas:
        raise ValueError(f"{nombre}: hay datos anidados en {columnas_anidadas}.")


def ejecutar(actualizar: bool = False) -> None:
    load_dotenv(DIRECTORIO / ".env")
    api_key = os.getenv("API_SPORTS_KEY", "").strip()
    if not api_key:
        raise ErrorAPI("Falta API_SPORTS_KEY en el archivo .env.")

    fecha_extraccion = datetime.now(timezone.utc)
    datos_equipos = consultar_endpoint("teams", api_key, actualizar)
    datos_partidos = consultar_endpoint("fixtures", api_key, actualizar)
    datos_clasificacion = consultar_endpoint("standings", api_key, actualizar)

    equipos = normalizar_equipos(datos_equipos, fecha_extraccion)
    partidos = normalizar_partidos(datos_partidos, fecha_extraccion)
    clasificacion = normalizar_clasificacion(datos_clasificacion, fecha_extraccion)

    _validar_dataframe(equipos, COLUMNAS_EQUIPOS, ["equipo_id"], "equipos")
    _validar_dataframe(partidos, COLUMNAS_PARTIDOS, ["partido_id"], "partidos")
    _validar_dataframe(
        clasificacion,
        COLUMNAS_CLASIFICACION,
        ["grupo", "equipo_id"],
        "clasificacion",
    )

    salidas = {
        "equipos.parquet": equipos,
        "partidos.parquet": partidos,
        "clasificacion.parquet": clasificacion,
    }
    for nombre, df in salidas.items():
        destino_temporal = DIRECTORIO / f".{nombre}.tmp"
        destino_final = DIRECTORIO / nombre
        df.to_parquet(destino_temporal, index=False, engine="pyarrow")
        destino_temporal.replace(destino_final)
        print(f"{nombre}: {len(df)} registros, {len(df.columns)} columnas.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--actualizar",
        action="store_true",
        help="Ignora la caché y vuelve a consultar todos los endpoints.",
    )
    argumentos = parser.parse_args()
    try:
        ejecutar(actualizar=argumentos.actualizar)
    except (ErrorAPI, ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
