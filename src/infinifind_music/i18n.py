"""
Translations for the command-line scripts and the pages they generate.

Supported languages: en-US (default), pt-BR, es.
The desktop/web interface has its own copy of the UI strings in ui.html.
"""

DEFAULT = "en-US"
LANGUAGES = ("en-US", "pt-BR", "es")

# iTunes Store country and Amazon Music domain used by default for each language.
COUNTRY = {"en-US": "US", "pt-BR": "BR", "es": "ES"}
AMAZON = {"en-US": "music.amazon.com", "pt-BR": "music.amazon.com.br", "es": "music.amazon.es"}

MESSAGES = {
    "en-US": {
        "file_not_found": "File not found: {path}",
        "no_songs": "No songs found in this CSV. Detected columns: {columns}",
        "songs_read": "{n} songs read from {path}",
        "excluded": "{n} songs removed by the excluded artists",
        "fetching_titles": "Looking up the name of {n} songs from their video IDs…",
        "search_error": "   search error ({error}); trying again…",
        "interrupted": "\nInterrupted. Building the page with what was found so far (run again to continue).",
        "done": "Done! Open the file: {path}",
        "text_list": "Text list: {path}",
        "summary_check": "{ok} available, {bad} unavailable",
        "list_updated": "List updated: {path}",
        "unavailable_list": "Unavailable: {path}",
        # generated page
        "page_title": "My songs",
        "songs": "{n} songs",
        "found_itunes": "{n} found in the iTunes Store",
        "source": "source: {name}",
        "filter": "Filter by song or artist…",
        "col_song": "Song",
        "col_itunes": "iTunes Store",
        "col_search": "Search on",
        "col_link": "Link",
        "not_found": "not found",
        "no_title": "(no title)",
        "search_ytm": "Search on YouTube Music",
    },
    "pt-BR": {
        "file_not_found": "Arquivo não encontrado: {path}",
        "no_songs": "Não encontrei músicas nesse CSV. Colunas detectadas: {columns}",
        "songs_read": "{n} músicas lidas de {path}",
        "excluded": "{n} músicas removidas pelos artistas excluídos",
        "fetching_titles": "Buscando o nome de {n} músicas pelo ID do vídeo…",
        "search_error": "   erro na busca ({error}); tentando de novo…",
        "interrupted": ("\nInterrompido. Gerando a página com o que já foi encontrado "
                        "(rode de novo para continuar)."),
        "done": "Pronto! Abra o arquivo: {path}",
        "text_list": "Lista em texto: {path}",
        "summary_check": "{ok} disponíveis, {bad} indisponíveis",
        "list_updated": "Lista atualizada: {path}",
        "unavailable_list": "Indisponíveis: {path}",
        "page_title": "Minhas músicas",
        "songs": "{n} músicas",
        "found_itunes": "{n} encontradas na loja do iTunes",
        "source": "origem: {name}",
        "filter": "Filtrar por música ou artista…",
        "col_song": "Música",
        "col_itunes": "Loja do iTunes",
        "col_search": "Procurar em",
        "col_link": "Link",
        "not_found": "não encontrado",
        "no_title": "(sem título)",
        "search_ytm": "Buscar no YouTube Music",
    },
    "es": {
        "file_not_found": "Archivo no encontrado: {path}",
        "no_songs": "No encontré canciones en este CSV. Columnas detectadas: {columns}",
        "songs_read": "{n} canciones leídas de {path}",
        "excluded": "{n} canciones eliminadas por los artistas excluidos",
        "fetching_titles": "Buscando el nombre de {n} canciones por el ID del video…",
        "search_error": "   error en la búsqueda ({error}); intentando de nuevo…",
        "interrupted": ("\nInterrumpido. Generando la página con lo encontrado hasta ahora "
                        "(ejecútalo de nuevo para continuar)."),
        "done": "¡Listo! Abre el archivo: {path}",
        "text_list": "Lista en texto: {path}",
        "summary_check": "{ok} disponibles, {bad} no disponibles",
        "list_updated": "Lista actualizada: {path}",
        "unavailable_list": "No disponibles: {path}",
        "page_title": "Mis canciones",
        "songs": "{n} canciones",
        "found_itunes": "{n} encontradas en la tienda de iTunes",
        "source": "origen: {name}",
        "filter": "Filtrar por canción o artista…",
        "col_song": "Canción",
        "col_itunes": "Tienda de iTunes",
        "col_search": "Buscar en",
        "col_link": "Enlace",
        "not_found": "no encontrada",
        "no_title": "(sin título)",
        "search_ytm": "Buscar en YouTube Music",
    },
}


def normalize(lang):
    """Accepts 'pt', 'pt-br', 'es-MX', etc. Falls back to the default (en-US)."""
    lang = (lang or "").strip().lower()
    if lang.startswith("pt"):
        return "pt-BR"
    if lang.startswith("es"):
        return "es"
    return DEFAULT


def t(lang, key, **values):
    text = MESSAGES.get(lang, MESSAGES[DEFAULT]).get(key) or MESSAGES[DEFAULT][key]
    return text.format(**values)


def price(lang, currency, value):
    text = f"{currency} {value:.2f}"
    return text.replace(".", ",") if lang in ("pt-BR", "es") else text
