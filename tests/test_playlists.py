"""Reading playlists from the user's account, with the YouTube API simulated (no network)."""

import glob
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from infinifind_music import paths, server, youtube_api, youtube_auth


class FakeSession:
    """Answers the YouTube Data API like Google would, page by page."""

    def __init__(self, fail_videos=False):
        self.calls = []
        self.fail_videos = fail_videos

    def status(self):
        return {"configured": True, "signed_in": True, "channel": "Me", "remembered": False}

    def api_get(self, url, params):
        self.calls.append((url, dict(params)))
        if url.endswith("/channels"):
            return {"items": [{"contentDetails": {"relatedPlaylists": {"likes": "LL"}},
                               "snippet": {"country": "br"}}]}
        if url.endswith("/videos"):
            if self.fail_videos:
                raise youtube_auth.AuthError("expired")
            return {"items": [VIDEO_INFO[i] for i in params["id"].split(",") if i in VIDEO_INFO]}
        if url.endswith("/playlists"):
            if params.get("pageToken") == "p2":
                return {"items": [{"id": "PL2", "snippet": {"title": "Rock"},
                                   "contentDetails": {"itemCount": 1},
                                   "status": {"privacyStatus": "public"}}]}
            return {"nextPageToken": "p2",
                    "items": [{"id": "PL1", "snippet": {"title": "Anime"},
                               "contentDetails": {"itemCount": 3}, "status": {"privacyStatus": "private"}}]}
        if url.endswith("/playlistItems"):
            videos = VIDEOS[params["playlistId"]]
            return {"items": videos[: int(params["maxResults"])], "pageInfo": {"totalResults": len(videos)}}
        raise AssertionError(url)


def item(video_id, title, channel):
    snippet = {"title": title, "videoOwnerChannelTitle": channel, "resourceId": {"videoId": video_id}}
    return {"snippet": snippet, "contentDetails": {"videoId": video_id}}


VIDEO_INFO = {
    "aaaaaaaaaaa": {"id": "aaaaaaaaaaa", "snippet": {"title": "x", "channelTitle": "fan"},
                    "status": {"uploadStatus": "processed", "privacyStatus": "public"}, "contentDetails": {}},
    # Blocked in Brazil, the country set on the test channel.
    "bbbbbbbbbbb": {"id": "bbbbbbbbbbb", "snippet": {"title": "Song Two", "channelTitle": "Band - Topic"},
                    "status": {"uploadStatus": "processed", "privacyStatus": "public"},
                    "contentDetails": {"regionRestriction": {"blocked": ["BR", "DE"]}}},
    "ddddddddddd": {"id": "ddddddddddd", "snippet": {"title": "Liked Song", "channelTitle": "Singer - Topic"},
                    "status": {"uploadStatus": "processed", "privacyStatus": "public"},
                    "contentDetails": {"regionRestriction": {"allowed": ["BR", "US"]}}},
    "dQw4w9WgXcQ": {"id": "dQw4w9WgXcQ",
                    "snippet": {"title": "Rick Astley - Never Gonna Give You Up (Official Video)",
                                "channelTitle": "Rick Astley"},
                    "status": {"uploadStatus": "processed", "privacyStatus": "public"}, "contentDetails": {}},
}

VIDEOS = {
    "PL1": [item("aaaaaaaaaaa", "My Show Opening 1 FULL - Song One", "fan"),
            item("bbbbbbbbbbb", "Song Two", "Band - Topic"),
            {"snippet": {"title": "Deleted video", "resourceId": {"videoId": "ccccccccccc"}},
             "contentDetails": {"videoId": "ccccccccccc"}}],
    "PL2": [item("bbbbbbbbbbb", "Song Two", "Band - Topic")],
    "LL": [item("ddddddddddd", "Liked Song", "Singer - Topic")],
}


def test_list_playlists_follows_pages_and_adds_liked_videos():
    playlists = youtube_api.list_playlists(FakeSession())
    assert [p["id"] for p in playlists] == ["LL", "PL1", "PL2"]
    assert playlists[0]["likes"] is True and playlists[1]["count"] == 3
    assert playlists[0]["count"] == 1  # liked videos: total read from the first page


def test_playlist_videos_marks_deleted_entries():
    videos = youtube_api.playlist_videos("PL1", FakeSession())
    assert [v["gone"] for v in videos] == [False, False, True]
    assert videos[1]["channel"] == "Band - Topic"


# ---------- through the local server ----------

@pytest.fixture
def base_url(tmp_path, monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(youtube_auth, "session", fake)
    out = tmp_path / "results"
    out.mkdir()
    before = paths.load_settings()
    paths.save_settings({**before, "output_dir": str(out)})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", out
    httpd.shutdown()
    paths.save_settings(before)


def call(url, data=None):
    headers = {"X-Token": server.TOKEN}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers)) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def run_find(base, request):
    status, body = call(base + "/api/find", request)
    assert status == 200, body
    server.task.wait(60)
    return server.task.state()


FAST = {"source": "account", "mode": "youtube", "check": False, "lang": "en-US"}


def test_playlists_route(base_url):
    base, _ = base_url
    status, body = call(base + "/api/playlists")
    assert status == 200 and [p["title"] for p in body["playlists"]] == [None, "Anime", "Rock"]


def test_combined_page_from_several_playlists(base_url):
    base, out = base_url
    state = run_find(base, {**FAST, "playlists": ["PL1", "PL2"], "output": "mine.html"})
    assert state["code"] == 0, state["log"]
    assert any("Reading “Anime” (3 videos)" in line for line in state["log"])
    lines = (out / "mine.txt").read_text(encoding="utf-8").splitlines()
    # The video in both playlists appears once; the deleted one goes to the unavailable list.
    assert len(lines) == 2 and sum("bbbbbbbbbbb" in line for line in lines) == 1
    assert "Song One" in lines[0] and "Band – Song Two" in lines[1]
    assert "ccccccccccc" in (out / "mine_unavailable.txt").read_text(encoding="utf-8")
    page = (out / "mine.html").read_text(encoding="utf-8")
    assert "▸ Anime · Rock" in page and "source: Anime, Rock" in page
    # The temporary CSV with the playlist data is gone.
    assert not glob.glob(os.path.join(paths.cache_dir(), "account-*.csv"))


def test_one_file_per_playlist_with_a_typed_prefix(base_url):
    base, out = base_url
    state = run_find(base, {**FAST, "playlists": ["PL1", "LL"], "per_playlist": True, "output": "Set.html"})
    assert state["code"] == 0, state["log"]
    assert (out / "set_anime.html").exists() and (out / "set_liked_videos.html").exists()
    assert "ddddddddddd" in (out / "set_liked_videos.txt").read_text(encoding="utf-8")


def test_one_file_per_playlist_with_suggested_names(base_url):
    base, out = base_url
    state = run_find(base, {**FAST, "playlists": ["PL1", "PL2"], "per_playlist": True,
                            "output": "anime_rock.html", "auto_name": True})
    assert state["code"] == 0, state["log"]
    assert (out / "anime.html").exists() and (out / "rock.html").exists()


def test_file_names_are_command_line_friendly(base_url):
    assert server.slugify("Vídeos curtidos: Rock & Pop!") == "videos_curtidos_rock_pop"
    assert server.slugify("ＴＩＭ　ＭＡＩＡ") == "tim_maia"
    assert server.slugify("***", "my_songs") == "my_songs"
    base, out = base_url
    state = run_find(base, {**FAST, "playlists": ["PL2"], "output": "Minhas Músicas.html"})
    assert state["code"] == 0, state["log"]
    assert (out / "minhas_musicas.html").exists() and (out / "minhas_musicas.txt").exists()


def test_only_the_users_own_playlists_are_accepted(base_url):
    base, _ = base_url
    status, body = call(base + "/api/find", {**FAST, "playlists": ["SOMEONE_ELSES"], "output": "x.html"})
    assert status == 400 and body["error"] == "need_playlists"
    status, body = call(base + "/api/find", {**FAST, "playlists": "PL1", "output": "x.html"})
    assert status == 400 and body["error"] == "need_playlists"


def test_signed_out_user_gets_a_clear_error(base_url, monkeypatch):
    base, _ = base_url

    def expired(url, params):
        raise youtube_auth.AuthError("not_signed_in")

    monkeypatch.setattr(youtube_auth.session, "api_get", expired)
    status, body = call(base + "/api/playlists")
    assert status == 401 and body["error"] == "not_signed_in"


# ---------- Phase 4: availability through the official API ----------

def test_availability_rules():
    def video(status=None, restriction=None):
        return {"status": status or {"uploadStatus": "processed", "privacyStatus": "public"},
                "contentDetails": {"regionRestriction": restriction} if restriction else {}}

    assert youtube_api.availability_of(video(), "BR") == "OK"
    assert youtube_api.availability_of(video({"privacyStatus": "private"}), "BR") == "UNPLAYABLE"
    assert youtube_api.availability_of(video({"uploadStatus": "rejected"}), "BR") == "UNPLAYABLE"
    assert youtube_api.availability_of(video(restriction={"blocked": ["BR"]}), "BR") == "BLOCKED"
    assert youtube_api.availability_of(video(restriction={"allowed": ["US"]}), "BR") == "BLOCKED"
    assert youtube_api.availability_of(video(restriction={"allowed": ["BR", "US"]}), "BR") == "OK"


def test_videos_info_uses_batches_of_50_and_marks_missing_as_gone():
    fake = FakeSession()
    ids = ["aaaaaaaaaaa"] + [f"id{n:09d}" for n in range(119)]
    info = youtube_api.videos_info(ids, "BR", fake)
    assert len([u for u, _ in fake.calls if u.endswith("/videos")]) == 3
    assert info["aaaaaaaaaaa"]["status"] == "OK"
    assert info["id000000000"]["status"] == youtube_api.GONE


def test_region_comes_from_the_channel_or_the_default():
    assert youtube_api.user_region("US", FakeSession()) == "BR"

    class NoCountry(FakeSession):
        def api_get(self, url, params):
            return {"items": [{"snippet": {}}]}

    assert youtube_api.user_region("es", NoCountry()) == "ES"


def test_account_playlists_are_checked_with_the_api(base_url):
    base, out = base_url
    state = run_find(base, {**FAST, "check": True, "playlists": ["PL1", "PL2"], "output": "api.html"})
    assert state["code"] == 0, state["log"]
    assert any("Checking 2 videos with the YouTube API (country: BR)" in line for line in state["log"])
    playable = (out / "api.txt").read_text(encoding="utf-8")
    unavailable = (out / "api_unavailable.txt").read_text(encoding="utf-8")
    assert "aaaaaaaaaaa" in playable
    assert "bbbbbbbbbbb" in unavailable and "ccccccccccc" in unavailable  # blocked in BR + deleted


def test_takeout_csv_uses_the_api_when_signed_in(base_url):
    base, out = base_url
    csv_path = os.path.join(os.path.dirname(__file__), os.pardir, "examples", "playlist_example.csv")
    state = run_find(base, {"source": "takeout", "csv": os.path.abspath(csv_path), "mode": "youtube",
                            "check": True, "lang": "en-US", "output": "takeout.html"})
    assert state["code"] == 0, state["log"]
    lines = (out / "takeout.txt").read_text(encoding="utf-8").splitlines()
    # The playlist export only has the video ID: the title came from the API, cleaned.
    assert lines == ["Rick Astley – Never Gonna Give You Up: https://music.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert "source: playlist_example.csv" in (out / "takeout.html").read_text(encoding="utf-8")


def test_takeout_falls_back_to_page_checks_when_the_api_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_auth, "session", FakeSession(fail_videos=True))
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "examples",
                                            "library_example.csv"))
    log = []
    commands = server.takeout_job(csv_path, str(tmp_path / "x.html"), "en-US", [])(log.append)
    assert commands[0][1] == csv_path  # the original CSV goes to the finder, which checks the pages
    assert any("could not be used" in line for line in log)
