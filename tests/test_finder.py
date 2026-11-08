import os
import subprocess
import sys

from infinifind_music import finder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


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
         "--youtube-only", "--exclude-artists", "Rick Astley", "--lang", "es", "--output", str(out)],
        capture_output=True, text=True, env=env, check=True)
    assert "1 canciones eliminadas" in result.stdout
    lines = (tmp_path / "links.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and "Garota de Ipanema" in lines[0]
    assert '<html lang="es">' in out.read_text(encoding="utf-8")
