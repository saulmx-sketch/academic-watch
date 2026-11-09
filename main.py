#!/usr/bin/env python3
"""Vigía de revistas académicas.

Pregunta a Crossref (el registro mundial de DOI) qué artículos nuevos dieron de
alta las revistas de revistas.txt y escribe dos archivos:

  feed.xml    para el lector RSS (Readwise Reader, Feedly, etc.)
  index.html  la misma lista, para leerla en el navegador

Solo usa la biblioteca estándar de Python: no hay nada que instalar.
Uso:  python main.py
"""
from __future__ import annotations

import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

# ----------------------------------------------------------------- ajustes
VENTANA_DIAS = 60          # el feed muestra lo dado de alta en los últimos N días
ANTIGUEDAD_MAX_DIAS = 730  # ignora artículos viejos que una revista registra en bloque
RESUMEN_MAX = 3000         # tope de caracteres del resumen

RAIZ = Path(__file__).resolve().parent
REPO = os.environ.get("GITHUB_REPOSITORY", "saulmx-sketch/academic-watch")
DUENO, _, NOMBRE_REPO = REPO.partition("/")
URL_PAGINA = f"https://{DUENO.lower()}.github.io/{NOMBRE_REPO}/"
URL_FEED = URL_PAGINA + "feed.xml"

API = "https://api.crossref.org/works"
CAMPOS = "DOI,title,subtitle,author,container-title,ISSN,created,published,volume,issue,page,abstract"
# Crossref atiende mejor a quien se identifica; el correo es opcional y se toma
# de la variable CROSSREF_MAILTO del repositorio, nunca se escribe aquí.
CORREO = os.environ.get("CROSSREF_MAILTO", "").strip()
AGENTE = f"academic-watch/2.0 (https://github.com/{REPO}" + (f"; mailto:{CORREO})" if CORREO else ")")

RE_ISSN = re.compile(r"^\d{4}-\d{3}[\dXx]$")
RE_ETIQUETA = re.compile(r"</?[A-Za-z][^>]*>")
RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Piezas que las revistas registran con DOI pero no son artículos.
RE_RUIDO = re.compile(
    r"^(issue information|volume information|.*\bfront ?matter\b.*|.*\bback ?matter\b.*|"
    r"(about the |notes on |list of )?contributors|editorial board|(table of )?contents|"
    r"(other )?books? received|thanks to reviewers|periodical literature|notes and comments|masthead|cover|index|[íi]ndice|directorio|preliminares|"
    r"p[áa]gina legal|cr[ée]ditos|tabla de contenidos?)$",
    re.I,
)
MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()

DC = "http://purl.org/dc/elements/1.1/"
ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("dc", DC)
ET.register_namespace("atom", ATOM)


# ------------------------------------------------------------- utilidades
def limpiar(texto: str) -> str:
    """Quita etiquetas (<i>, <jats:p>...), entidades y saltos de línea."""
    texto = html.unescape(RE_ETIQUETA.sub(" ", texto or ""))
    texto = " ".join(RE_CONTROL.sub("", texto).split())
    return re.sub(r" ([,.;:!?])", r"\1", texto)  # el hueco que deja una etiqueta antes de un signo


def leer_revistas() -> list[dict]:
    revistas, vistos = [], {}
    lineas = (RAIZ / "revistas.txt").read_text(encoding="utf-8-sig").splitlines()
    for n, linea in enumerate(lineas, 1):
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        partes = [p.strip() for p in linea.split("|")]
        if len(partes) < 2 or not partes[0] or not RE_ISSN.match(partes[1]):
            sys.exit(f"revistas.txt, renglón {n}: esperaba 'Sigla | ISSN | Grupo' y encontré: {linea!r}")
        issn = partes[1].upper()
        if issn in vistos:
            sys.exit(f"revistas.txt, renglón {n}: el ISSN {issn} ya está en el renglón {vistos[issn]}")
        vistos[issn] = n
        grupo = partes[2] if len(partes) > 2 and partes[2] else "General"
        revistas.append({"sigla": partes[0], "issn": issn, "grupo": grupo})
    if not revistas:
        sys.exit("revistas.txt no tiene ninguna revista activa")
    return revistas


def pedir(parametros: dict) -> dict:
    """Una consulta a Crossref, con reintentos si el servidor falla o pide esperar."""
    url = API + "?" + urllib.parse.urlencode(parametros)
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept-Encoding": "gzip"})
    error: Exception | None = None
    for intento in range(1, 5):
        try:
            with urllib.request.urlopen(peticion, timeout=60) as r:
                cuerpo = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    cuerpo = gzip.decompress(cuerpo)
            return json.loads(cuerpo)["message"]
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:  # error nuestro: reintentar no ayuda
                raise
            error = e
        except (OSError, ValueError) as e:  # red caída, tiempo agotado, respuesta trunca
            error = e
        if intento < 4:
            time.sleep(2 ** intento)
    raise RuntimeError(f"Crossref no respondió tras 4 intentos: {error}")


def filtro_issn(revistas: list[dict]) -> str:
    return ",".join(f"issn:{r['issn']}" for r in revistas)


# ---------------------------------------------------------------- Crossref
def descargar(revistas: list[dict], hoy: date) -> list[dict]:
    """Trae en una sola consulta lo nuevo de todas las revistas."""
    filtro = (
        f"{filtro_issn(revistas)},type:journal-article,"
        f"from-created-date:{hoy - timedelta(days=VENTANA_DIAS)},"
        f"from-pub-date:{hoy - timedelta(days=ANTIGUEDAD_MAX_DIAS)}"
    )
    crudos, cursor = [], "*"
    while True:
        m = pedir({"filter": filtro, "select": CAMPOS, "sort": "created", "order": "desc",
                   "rows": 1000, "cursor": cursor})
        crudos += m["items"]
        if len(m["items"]) < 1000:
            return crudos
        cursor = m["next-cursor"]


def issn_desconocidos(revistas: list[dict]) -> list[dict]:
    """Revistas cuyo ISSN no tiene un solo artículo en Crossref (mal escrito o inexistente)."""
    m = pedir({"filter": filtro_issn(revistas), "rows": 0, "facet": "issn:*"})
    conocidos = {clave.rsplit("/", 1)[-1].upper()
                 for clave, n in m["facets"]["issn"]["values"].items() if n}
    return [r for r in revistas if r["issn"] not in conocidos]


def normalizar(crudos: list[dict], revistas: list[dict]) -> list[dict]:
    por_issn = {r["issn"]: r for r in revistas}
    articulos, vistos = [], set()
    for c in crudos:
        doi = c.get("DOI", "")
        revista = next((por_issn[i.upper()] for i in c.get("ISSN", []) if i.upper() in por_issn), None)
        titulo = limpiar((c.get("title") or [""])[0])
        if not doi or not revista or not titulo or doi.lower() in vistos or RE_RUIDO.match(titulo):
            continue
        vistos.add(doi.lower())
        subtitulo = limpiar((c.get("subtitle") or [""])[0])
        if subtitulo and subtitulo.lower() not in titulo.lower():
            titulo = f"{titulo}: {subtitulo}"
        autores = [limpiar(f"{a.get('given', '')} {a.get('family', '')}") or limpiar(a.get("name", ""))
                   for a in c.get("author", [])]
        resumen = limpiar(re.sub(r"<jats:title>.*?</jats:title>", " ", c.get("abstract", ""), flags=re.S))
        if len(resumen) > RESUMEN_MAX:
            resumen = resumen[:RESUMEN_MAX].rsplit(" ", 1)[0] + "…"
        partes_fecha = (c.get("published", {}).get("date-parts") or [[]])[0]
        articulos.append({
            "doi": doi,
            "url": "https://doi.org/" + urllib.parse.quote(doi, safe="/:()"),
            "sigla": revista["sigla"],
            "grupo": revista["grupo"],
            "revista": limpiar((c.get("container-title") or [revista["sigla"]])[0]),
            "titulo": titulo,
            "autores": [a for a in autores if a],
            "alta": datetime.fromisoformat(c["created"]["date-time"].replace("Z", "+00:00")),
            "publicado": "-".join(f"{p:02d}" for p in partes_fecha if p),
            "volumen": c.get("volume", ""), "numero": c.get("issue", ""), "paginas": c.get("page", ""),
            "resumen": resumen,
        })
    articulos.sort(key=lambda a: (a["alta"], a["doi"]), reverse=True)
    return articulos


# ------------------------------------------------------------------ salidas
def ficha(a: dict) -> str:
    """'Revista, vol. 3, núm. 2, pp. 1-20 · publicado 2026-10'."""
    trozos = [a["revista"]]
    if a["volumen"]:
        trozos.append(f"vol. {a['volumen']}")
    if a["numero"]:
        trozos.append(f"núm. {a['numero']}")
    if a["paginas"]:
        trozos.append(f"pp. {a['paginas']}")
    return ", ".join(trozos) + (f" · publicado {a['publicado']}" if a["publicado"] else "")


def hacer_rss(articulos: list[dict]) -> str:
    rss = ET.Element("rss", version="2.0")
    canal = ET.SubElement(rss, "channel")
    ET.SubElement(canal, "title").text = "Academic Watchlist"
    ET.SubElement(canal, "link").text = URL_PAGINA
    ET.SubElement(canal, "description").text = (
        f"Artículos nuevos de las revistas vigiladas, vía Crossref (últimos {VENTANA_DIAS} días)")
    ET.SubElement(canal, f"{{{ATOM}}}link", href=URL_FEED, rel="self", type="application/rss+xml")
    if articulos:
        ET.SubElement(canal, "lastBuildDate").text = format_datetime(articulos[0]["alta"], usegmt=True)
    for a in articulos:
        e = ET.SubElement(canal, "item")
        ET.SubElement(e, "title").text = f"[{a['sigla']}] {a['titulo']}"
        ET.SubElement(e, "link").text = a["url"]
        ET.SubElement(e, "guid", isPermaLink="false").text = a["doi"]
        ET.SubElement(e, "pubDate").text = format_datetime(a["alta"], usegmt=True)
        if a["autores"]:
            ET.SubElement(e, f"{{{DC}}}creator").text = ", ".join(a["autores"])
        ET.SubElement(e, "category").text = a["grupo"]
        cuerpo = ""
        if a["autores"]:
            cuerpo += f"<p><b>{html.escape(', '.join(a['autores']))}</b></p>"
        cuerpo += f"<p><i>{html.escape(ficha(a))}</i></p>"
        if a["resumen"]:
            cuerpo += f"<p>{html.escape(a['resumen'])}</p>"
        ET.SubElement(e, "description").text = cuerpo
    ET.indent(rss)
    texto = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"
    ET.fromstring(texto)  # si el XML saliera mal formado, falla aquí y no se publica
    return texto


def fecha_corta(d: datetime) -> str:
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def hacer_pagina(articulos: list[dict], revistas: list[dict], invalidos: list[dict]) -> str:
    e = html.escape
    conteo: dict[str, int] = {}
    for a in articulos:
        conteo[a["sigla"]] = conteo.get(a["sigla"], 0) + 1
    malos = {r["issn"] for r in invalidos}

    grupos: dict[str, list[dict]] = {}
    for r in revistas:
        grupos.setdefault(r["grupo"], []).append(r)
    panel = ""
    for grupo, lista in grupos.items():
        chips = ""
        for r in lista:
            n = conteo.get(r["sigla"], 0)
            clase = "chip malo" if r["issn"] in malos else "chip" if n else "chip callada"
            nota = "ISSN no encontrado" if r["issn"] in malos else f"{n}" if n else "sin novedades"
            chips += (f'<button class="{clase}" data-f="[{e(r["sigla"])}]" title="ISSN {r["issn"]}">'
                      f'{e(r["sigla"])} <small>{nota}</small></button>')
        panel += f"<h3>{e(grupo)}</h3><p>{chips}</p>"

    filas = ""
    for a in articulos:
        resumen = f"<details><summary>Resumen</summary><p>{e(a['resumen'])}</p></details>" if a["resumen"] else ""
        autores = f'<p class="autores">{e(", ".join(a["autores"]))}</p>' if a["autores"] else ""
        filas += (
            f'<article><p class="meta"><span class="sigla">[{e(a["sigla"])}]</span> '
            f'{fecha_corta(a["alta"])}</p>'
            f'<h2><a href="{e(a["url"])}">{e(a["titulo"])}</a></h2>{autores}'
            f'<p class="ficha">{e(ficha(a))}</p>{resumen}</article>\n')

    ultima = fecha_corta(articulos[0]["alta"]) if articulos else "sin datos"
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vigía de revistas</title>
<link rel="alternate" type="application/rss+xml" title="Academic Watchlist" href="feed.xml">
<style>
:root {{ --fondo:#fbfaf7; --texto:#1f1d1a; --tenue:#6b665e; --linea:#e3dfd6; --acento:#7a1f2b; --chip:#f0ece3; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fondo:#191817; --texto:#ebe7df; --tenue:#a39d92; --linea:#34312d; --acento:#e39aa3; --chip:#262422; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0 auto; max-width:46rem; padding:1.5rem 1rem 4rem; background:var(--fondo); color:var(--texto);
  font:1rem/1.55 Georgia, 'Times New Roman', serif; }}
h1 {{ font-size:1.7rem; margin:0 0 .2rem; }}
h2 {{ font-size:1.12rem; line-height:1.35; margin:.1rem 0 .2rem; font-weight:600; }}
h3 {{ font:600 .78rem/1.2 system-ui, sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--tenue); margin:1rem 0 .3rem; }}
a {{ color:var(--acento); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
p {{ margin:.2rem 0; }}
.sub, .meta, .ficha, small, input, button {{ font-family:system-ui, sans-serif; }}
.sub, .meta, .ficha {{ color:var(--tenue); font-size:.85rem; }}
.sigla {{ color:var(--acento); font-weight:600; }}
.autores {{ font-style:italic; }}
article {{ padding:.9rem 0; border-top:1px solid var(--linea); }}
details {{ margin-top:.3rem; font-size:.95rem; }} summary {{ cursor:pointer; color:var(--tenue); font:.85rem system-ui, sans-serif; }}
input[type=checkbox] {{ margin-right:.3rem; }}
input[type=search] {{ width:100%; padding:.6rem .8rem; margin:1rem 0 .3rem; font-size:1rem; color:inherit; background:var(--chip);
  border:1px solid var(--linea); border-radius:.5rem; }}
.chip {{ margin:.15rem .2rem .15rem 0; padding:.25rem .6rem; font-size:.85rem; color:inherit; background:var(--chip);
  border:1px solid var(--linea); border-radius:1rem; cursor:pointer; }}
.chip small {{ color:var(--tenue); }} .callada {{ opacity:.55; }} .malo {{ border-color:#c0392b; }}
.activo {{ border-color:var(--acento); }}
#vacio {{ display:none; padding:1rem 0; color:var(--tenue); }}
</style>
</head>
<body>
<h1>Vigía de revistas</h1>
<p class="sub">{len(articulos)} artículos dados de alta en los últimos {VENTANA_DIAS} días · última novedad: {ultima} ·
<a href="feed.xml">suscribirse por RSS</a></p>
<input id="q" type="search" placeholder="Filtrar por título, autor o revista…" aria-label="Filtrar">
<label class="sub"><input id="r" type="checkbox"> Solo los que traen resumen (deja fuera casi todas las reseñas)</label>
<section id="panel">{panel}</section>
<main>
{filas}<p id="vacio">Nada coincide con el filtro.</p>
</main>
<script>
const q = document.getElementById('q'), arts = [...document.querySelectorAll('article')],
      chips = [...document.querySelectorAll('.chip')], vacio = document.getElementById('vacio');
const r = document.getElementById('r'), texto = arts.map(a => a.textContent.toLowerCase());
function filtrar() {{
  const t = q.value.trim().toLowerCase(); let n = 0;
  arts.forEach((a, i) => {{
    const ver = (!t || texto[i].includes(t)) && (!r.checked || a.querySelector('details'));
    a.hidden = !ver; n += ver;
  }});
  vacio.style.display = n ? 'none' : 'block';
  chips.forEach(c => c.classList.toggle('activo', c.dataset.f.toLowerCase() === t));
}}
q.addEventListener('input', filtrar); r.addEventListener('change', filtrar);
chips.forEach(c => c.addEventListener('click', () => {{ q.value = q.value === c.dataset.f ? '' : c.dataset.f; filtrar(); }}));
</script>
</body>
</html>
"""


def escribir_si_cambio(nombre: str, texto: str) -> bool:
    ruta = RAIZ / nombre
    if ruta.exists() and ruta.read_text(encoding="utf-8") == texto:
        return False
    ruta.write_text(texto, encoding="utf-8", newline="\n")
    return True


# ------------------------------------------------------------------- main
def main() -> int:
    t0 = time.time()
    revistas = leer_revistas()
    try:
        articulos = normalizar(descargar(revistas, date.today()), revistas)
    except Exception as e:  # sin datos no se toca el feed publicado
        print(f"::error::No pude consultar Crossref; el feed queda como estaba. {e}")
        return 2
    if not articulos:
        print("::error::Crossref devolvió cero artículos; el feed queda como estaba.")
        return 2
    try:
        invalidos = issn_desconocidos(revistas)
    except Exception as e:  # la verificación es un extra: si falla, se avisa y se sigue
        print(f"::warning::No pude verificar los ISSN esta vez: {e}")
        invalidos = []

    feed_viejo = (RAIZ / "feed.xml").read_text(encoding="utf-8") if (RAIZ / "feed.xml").exists() else ""
    ya_estaban = set(re.findall(r"<guid[^>]*>([^<]+)</guid>", feed_viejo))
    nuevos = [a for a in articulos if html.escape(a["doi"], quote=False) not in ya_estaban]

    cambio = escribir_si_cambio("feed.xml", hacer_rss(articulos))
    cambio |= escribir_si_cambio("index.html", hacer_pagina(articulos, revistas, invalidos))

    conteo: dict[str, int] = {}
    for a in articulos:
        conteo[a["sigla"]] = conteo.get(a["sigla"], 0) + 1
    lineas = [f"{len(articulos)} artículos en el feed, {len(nuevos)} nuevos desde la corrida anterior "
              f"({time.time() - t0:.1f} s; {'archivos actualizados' if cambio else 'sin cambios'})", ""]
    lineas += [f"- {r['sigla']}: {conteo.get(r['sigla'], 0)}" for r in revistas]
    for r in invalidos:
        lineas.append(f"- ISSN no encontrado en Crossref: {r['sigla']} ({r['issn']}); corrígelo en revistas.txt")
        print(f"::error file=revistas.txt::{r['sigla']}: el ISSN {r['issn']} no existe en Crossref")
    print("\n".join(lineas))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"nuevos={len(nuevos)}\n")
    return 1 if invalidos else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
