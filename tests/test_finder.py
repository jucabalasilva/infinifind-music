import os
import subprocess
import sys

from infinifind_music import finder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


def clean(title, author):
    c = finder.clean_youtube_title(title, author)
    return c["title"], c["artist"], c["album"]


def test_clean_title_from_official_channel():
    assert clean("Song Name (Official Video) (4K Remaster)", "Some Artist - Topic") == (
        "Song Name", "Some Artist", "")
    assert clean("Some Artist - Song Name [Lyrics]", "SomeArtistVEVO") == ("Song Name", "SomeArtist", "")


def test_clean_title_from_anime_fan_upload():
    # "Show - Opening N - Song": the uploader is not the artist; the show becomes the album.
    assert clean("My Show Opening 5 FULL - Song Name", "fan channel") == ("Song Name", "", "My Show")
    assert clean("My Show - Opening 4 (Song Name) - Full - 【Legendado PT-BR】", "fan") == (
        "Song Name", "", "My Show")
    assert clean("My Show OP 2 [FULL] Song Name", "fan") == ("Song Name", "", "My Show")


def test_clean_title_keeps_brackets_and_fixes_width_and_quotes():
    title, artist, _ = clean("Song (Mashup - A, B, C)", "Uploader")
    assert (title, artist) == ("Song (Mashup - A, B, C)", "Uploader")
    assert clean("ＡＢＣ - ＳＯＮＧ", "x")[:2] == ("SONG", "ABC")
    assert clean('Show: "Song" OPENING 10', "x")[0] == "Show: Song"
    assert clean("Song Name【Show OP 2】ENGLISH COVER by Someone", "Someone")[:2] == ("Song Name", "Someone")


def test_store_search_uses_main_artist_only():
    song = {"title": "Track", "artist": "Band, Singer, Drummer", "artists": ["Band", "Singer", "Drummer"],
            "album": "", "id": "abcdefghijk"}
    assert finder.search_term(song) == "Band Track"
    # A band name that contains a comma stays whole when it comes from a single field.
    assert finder.search_term({"title": "T", "artist": "Fear, and Loathing", "album": "", "id": ""}) == (
        "Fear, and Loathing T")
    links = finder.search_links(song, "en-US")
    assert links["Bandcamp"] == "https://bandcamp.com/search?q=Band%20Track"
    # The video link comes from the ID, never from the title.
    assert finder.youtube_links(song, "en-US")["YouTube Music"] == "https://music.youtube.com/watch?v=abcdefghijk"


def test_detect_columns_in_three_languages():
    pt = finder.detect_columns(["ID do vídeo", "Song Title", "Album Title", "Artist Name 1", "Artist Name 2"])
    assert pt["id"] == "ID do vídeo" and pt["title"] == "Song Title"
    assert pt["artists"] == ["Artist Name 1", "Artist Name 2"]

    es = finder.detect_columns(["ID del video", "Título de la canción", "Álbum", "Artista"])
    assert es["id"] == "ID del video" and es["title"] == "Título de la canción"
    assert es["album"] == "Álbum" and es["artists"] == ["Artista"]


def test_read_example_library():
    _, songs = finder.read_csv(os.path.join(EXAMPLES, "library_example.csv"))
    assert len(songs) == 2
    assert songs[0]["artist"] == "Rick Astley"
    assert songs[1]["artist"] == "Stan Getz, João Gilberto"


def test_generated_page_escapes_text(tmp_path):
    song = {"title": "<script>alert(1)</script>", "artist": "A & B", "album": "", "id": "dQw4w9WgXcQ"}
    out = tmp_path / "page.html"
    finder.build_html([song], str(out), "x.csv", "en-US", youtube_only=True)
    html = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and "A &amp; B" in html
    assert 'rel="noopener noreferrer"' in html


def test_command_line_youtube_only(tmp_path):
    env = dict(os.environ, INFINIFIND_CACHE_DIR=str(tmp_path / "cache"),
               PYTHONPATH=os.path.join(ROOT, "src"))
    out = tmp_path / "links.html"
    result = subprocess.run(
        [sys.executable, "-m", "infinifind_music.finder", os.path.join(EXAMPLES, "library_example.csv"),
         "--youtube-only", "--skip-availability", "--exclude-artists", "Rick Astley", "--lang", "es",
         "--output", str(out)],
        capture_output=True, text=True, env=env, check=True)
    assert "1 canciones eliminadas" in result.stdout
    lines = (tmp_path / "links.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and "Garota de Ipanema" in lines[0]
    assert '<html lang="es">' in out.read_text(encoding="utf-8")


def sample_songs():
    return [
        {"title": "Plays", "artist": "A", "album": "", "id": "aaaaaaaaaaa", "availability": "OK",
         "itunes": {"track": "Plays", "artist": "A", "album": "X", "price": 1.29, "currency": "USD",
                    "link": "https://music.apple.com/x"}},
        {"title": "Blocked", "artist": "B", "album": "", "id": "bbbbbbbbbbb", "availability": "UNPLAYABLE",
         "itunes": None},
    ]


def test_complete_page_has_youtube_itunes_and_stores(tmp_path):
    out = tmp_path / "page.html"
    finder.build_html(sample_songs(), str(out), "x.csv", "en-US")
    html = out.read_text(encoding="utf-8")
    assert "<th>YouTube</th><th>iTunes Store</th><th>Search on</th>" in html
    assert "watch?v=aaaaaaaaaaa" in html and "music.apple.com/x" in html and "bandcamp.com/search" in html
    assert "unavailable in your region" in html and "1 unavailable on YouTube" in html


def test_youtube_only_page_has_only_the_youtube_column(tmp_path):
    out = tmp_path / "page.html"
    finder.build_html(sample_songs(), str(out), "x.csv", "en-US", youtube_only=True)
    html = out.read_text(encoding="utf-8")
    assert "<th>YouTube</th></tr>" in html and "iTunes Store" not in html and "bandcamp" not in html


def test_unavailable_videos_go_to_a_separate_list(tmp_path):
    written = finder.write_link_lists(sample_songs(), str(tmp_path / "out.html"), "en-US")
    assert [os.path.basename(p) for p in written] == ["out.txt", "out_unavailable.txt"]
    assert "aaaaaaaaaaa" in (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "bbbbbbbbbbb" not in (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "bbbbbbbbbbb" in (tmp_path / "out_unavailable.txt").read_text(encoding="utf-8")
