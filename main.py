import requests
import html
from datetime import datetime, timezone

# CONFIGURACIÓN: Lista de Revistas
JOURNALS = {
    "HAHR": "1527-1900",
    "The Americas": "1538-1234",
    "Gender & History": "1468-0424", 
    "Radical History": "1534-1453",
    "GLQ": "1527-9375",
    "LARR": "1542-4278",
    "JLAS": "1469-767X",
    "Mexican Studies": "1533-8320",
    "JILAR": "1469-9524",
    "Arenal": "1134-6396"
}

def generate_rss():
    rss_items = ""
    print("Iniciando escaneo de CrossRef...")

    for name, issn in JOURNALS.items():
        try:
            # Limpiamos el nombre de la revista para evitar error con '&'
            safe_name = html.escape(name)
            
            url = f"https://api.crossref.org/journals/{issn}/works?sort=published&order=desc&rows=5&filter=type:journal-article"
            r = requests.get(url, timeout=15)
            data = r.json()
            
            if "message" in data and "items" in data["message"]:
                for item in data["message"]["items"]:
                    # Limpiamos título y autores
                    title_raw = item.get("title", ["Sin título"])[0]
                    title = html.escape(title_raw)
                    
                    link = html.escape(item.get("URL", ""))
                    doi = item.get("DOI", "")
                    
                    # Fecha
                    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                    if "created" in item and "date-time" in item["created"]:
                        try:
                            pub_date = datetime.fromisoformat(item["created"]["date-time"].replace("Z", "+00:00")).strftime("%a, %d %b %Y %H:%M:%S GMT")
                        except:
                            pass # Usar fecha actual si falla el parseo

                    # Autores
                    authors = []
                    if "author" in item:
                        for a in item["author"]:
                            authors.append(f"{a.get('given', '')} {a.get('family', '')}")
                    author_str = html.escape(", ".join(authors))

                    # Construimos el ítem RSS
                    rss_items += f"""
                    <item>
                        <title>[{safe_name}] {title}</title>
                        <link>{link}</link>
                        <guid isPermaLink="false">{doi}</guid>
                        <pubDate>{pub_date}</pubDate>
                        <description><![CDATA[Autores: {author_str}]]></description>
                    </item>"""
                print(f"✅ {name}: Procesado correctamente.")
            else:
                print(f"⚠️ {name}: Sin datos recientes.")
        except Exception as e:
            print(f"❌ Error con {name}: {e}")

    # Estructura final
    rss_feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>Academic Watchlist</title>
    <description>Feed generado via CrossRef</description>
    <link>https://github.com/saulmx-sketch/academic-watch</link>
    {rss_items}
</channel>
</rss>"""

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss_feed)
    print("Feed generado exitosamente.")

if __name__ == "__main__":
    generate_rss()
