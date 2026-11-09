# academic-watch

Vigía de revistas académicas. Cada mañana pregunta a Crossref (el registro mundial de DOI) qué artículos nuevos dieron de alta las revistas de la lista y publica el resultado en dos formas:

- Feed RSS, para el lector (Readwise Reader, Feedly, etc.): https://saulmx-sketch.github.io/academic-watch/feed.xml
- Página web, para leer y filtrar en el navegador: https://saulmx-sketch.github.io/academic-watch/

## Agregar o quitar una revista

1. Abre `revistas.txt` aquí en GitHub y pulsa el lápiz (Edit).
2. Agrega un renglón con el formato `Sigla | ISSN | Grupo`, o pon `#` al inicio del renglón que quieras apagar. Al final del archivo hay revistas sugeridas, ya verificadas, que se activan quitándoles el `#`.
3. Pulsa "Commit changes". El feed se regenera solo en un par de minutos.

Si un ISSN está mal escrito o no existe en Crossref, la corrida se marca como fallida y GitHub avisa por correo; las demás revistas se publican igual.

## Qué hace y qué no

- Muestra lo que cada revista registró en los últimos 60 días. Si un día la corrida falla, al siguiente se recupera sola: no se pierde nada.
- Cada entrada trae autores, revista, volumen, número, páginas y el resumen cuando la revista lo entrega a Crossref.
- Quita las piezas que no son textos (portadas, índices, listas de colaboradores).
- No distingue artículos de reseñas, porque Crossref no lo indica. En la página web la casilla "Solo los que traen resumen" deja fuera casi todas las reseñas.
- Las revistas que no registran DOI en Crossref no pueden vigilarse por esta vía.

## Piezas

| Archivo | Para qué sirve |
|---|---|
| `revistas.txt` | La lista de revistas. Es lo único que hace falta tocar. |
| `main.py` | El programa. Solo usa la biblioteca estándar de Python; no instala nada. |
| `.github/workflows/daily_update.yml` | La tarea automática: corre a diario (5:23 h de Ciudad de México), al editar la lista y a mano con el botón "Run workflow" de la pestaña Actions. |
| `feed.xml`, `index.html` | Los resultados. Los escribe el programa; no se editan a mano. |

Ajustes al inicio de `main.py`: `VENTANA_DIAS` (cuántos días hacia atrás muestra el feed) y `ANTIGUEDAD_MAX_DIAS` (descarta artículos viejos que una revista registra en bloque).

Opcional: Crossref atiende con prioridad a quien deja un correo de contacto. Para dárselo, crea en Settings > Secrets and variables > Actions > Variables una variable llamada `CROSSREF_MAILTO` con el correo. El programa funciona igual sin ella.

Para correrlo en una computadora: `python main.py` dentro de la carpeta.
