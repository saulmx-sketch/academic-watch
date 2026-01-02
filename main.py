import requests
import html
from datetime import datetime, timezone

# CONFIGURACIÓN: Lista de Revistas (Nombre e ISSN)
# Puedes añadir más buscando su "Online ISSN" en Google.
JOURNALS = {
    "HAHR": "1527-1900",  # Hispanic American Historical Review
    "The Americas": "1538-1234",
    "Gender & History": "1468-0424",
    "Radical History": "1534-1453",
    "GLQ": "1527-9375",
    "LARR": "1542-4278",  # Latin American Research Review
    "JLAS": "1469-767X",  # J. Lat. Am. Studies
    "Mexican Studies": "1533-8320",
    "JILAR": "1469-9524"  # J. Iberian & Lat. Am. Research
}

def generate_rss():
    rss_items = ""
    print("Iniciando escaneo de CrossRef...")

    for name, issn in JOURNALS.items():
        try:
            # Consultamos la API pública de CrossRef
            url = f"https://api.crossref.org/journals/{issn}/works?sort=published&order=desc&rows=5&filter=type:journal-article"
            r = requests.get(url, timeout=10)
            data = r.json()
            
            if "message" in data and "items" in data["message"]:
                for item in data["message"]["items"]:
                    title = item.get("title", ["Sin título"])[0]
                    link = item.get("URL", "")
                    doi = item.get("DOI", "")
                    
                    # Intentar parsear fecha
                    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                    if "created" in item and "date-time" in item["created"]:
                        pub_date = datetime.fromisoformat(item["created"]["date-time"].replace("Z", "+00:00")).strftime("%a, %d %b %Y %H:%M:%S GMT")

                    # Autores
                    authors = []
                    if "author" in item:
                        for a in item["author"]:
                            authors.append(f"{a.get('given', '')} {a.get('family', '')}")
                    author_str = ", ".join(authors)

                    # Construimos el ítem RSS
                    rss_items += f"""
                    <item>
                        <title>[{name}] {html.escape(title)}</title>
                        <link>{link}</link>
                        <guid isPermaLink="false">{doi}</guid>
                        <pubDate>{pub_date}</pubDate>
                        <description><![CDATA[Autores: {html.escape(author_str)}]]></description>
                    </item>"""
                print(f"✅ {name}: Procesado correctamente.")
            else:
                print(f"⚠️ {name}: Sin datos recientes.")
        except Exception as e:
            print(f"❌ Error con {name}: {e}")

    # Estructura final del RSS
    rss_feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>Academic Watchlist</title>
    <description>Feed generado automáticamente via CrossRef</description>
    <link>https://github.com/tu-usuario/academic-watch</link>
    {rss_items}
</channel>
</rss>"""

    # Guardamos el archivo
    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss_feed)
    print("Feed generado exitosamente: feed.xml")

if __name__ == "__main__":
    generate_rss()
