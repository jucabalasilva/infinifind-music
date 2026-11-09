"""
Reads the signed-in user's playlists through the YouTube Data API v3 (read-only scope).

Costs 1 quota unit per call of up to 50 items. The data is only used to build the user's own
pages and lists; nothing is kept in a cache here (see the 30-day rule in YouTube's developer
policies).
"""

from . import youtube_auth

API = "https://www.googleapis.com/youtube/v3"
# Titles YouTube uses for playlist entries whose video is gone or private.
HIDDEN_TITLES = ("Deleted video", "Private video")
GONE = "PRIVATE_OR_DELETED"  # availability status for those entries


def _pages(path, params, session):
    """Yields every item of a paginated list call."""
    params = dict(params, maxResults="50")
    while True:
        data = session.api_get(f"{API}/{path}", params)
        yield from data.get("items") or []
        token = data.get("nextPageToken")
        if not token:
            return
        params["pageToken"] = token


def list_playlists(session=None):
    """The user's playlists: [{"id", "title", "count", "privacy"}], liked videos first if available."""
    session = session or youtube_auth.session
    playlists = []
    try:
        channel = next(_pages("channels", {"part": "contentDetails", "mine": "true"}, session), {})
        likes = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("likes")
    except Exception:  # liked videos are a bonus; the regular playlists still load
        likes = None
    if likes:
        # The liked-videos playlist doesn't come with a count: ask for one item and read the total
        # (1 quota unit), so the user knows its size before choosing it (it can be thousands).
        try:
            params = {"part": "id", "playlistId": likes, "maxResults": "1"}
            page = session.api_get(f"{API}/playlistItems", params)
            count = page.get("pageInfo", {}).get("totalResults")
        except Exception:
            count = None
        playlists.append({"id": likes, "title": None, "count": count, "privacy": "private", "likes": True})
    for item in _pages("playlists", {"part": "snippet,contentDetails,status", "mine": "true"}, session):
        playlists.append({
            "id": item["id"],
            "title": item.get("snippet", {}).get("title", ""),
            "count": item.get("contentDetails", {}).get("itemCount"),
            "privacy": item.get("status", {}).get("privacyStatus", ""),
            "likes": False,
        })
    return playlists


def playlist_videos(playlist_id, session=None):
    """Videos of one playlist: [{"id", "title", "channel", "gone"}] in playlist order."""
    session = session or youtube_auth.session
    videos = []
    params = {"part": "snippet,contentDetails", "playlistId": playlist_id}
    for item in _pages("playlistItems", params, session):
        snippet = item.get("snippet", {})
        details = item.get("contentDetails", {})
        video_id = details.get("videoId") or snippet.get("resourceId", {}).get("videoId")
        if not video_id:
            continue
        channel = snippet.get("videoOwnerChannelTitle", "")
        title = snippet.get("title", "")
        videos.append({
            "id": video_id,
            "title": title,
            "channel": channel,
            # Deleted/private entries keep their ID but have a placeholder title and no owner.
            "gone": not channel and title in HIDDEN_TITLES,
        })
    return videos


BLOCKED = "BLOCKED"  # not playable in the user's country (regionRestriction)


def user_region(default, session=None):
    """Country set on the user's channel (ISO 3166 code), or `default` when it isn't set."""
    session = session or youtube_auth.session
    try:
        channel = next(_pages("channels", {"part": "snippet", "mine": "true"}, session), {})
        country = channel.get("snippet", {}).get("country")
    except Exception:
        country = None
    return (country or default).upper()


def availability_of(item, region):
    """Status for one item of videos.list: OK, BLOCKED (country) or UNPLAYABLE."""
    status = item.get("status", {})
    removed = status.get("uploadStatus") in ("deleted", "failed", "rejected")
    if removed or status.get("privacyStatus") == "private":
        return "UNPLAYABLE"
    restriction = item.get("contentDetails", {}).get("regionRestriction", {})
    if "allowed" in restriction and region not in restriction["allowed"]:
        return BLOCKED
    if region in restriction.get("blocked", []):
        return BLOCKED
    return "OK"


def videos_info(video_ids, region, session=None):
    """{video_id: {"title", "channel", "status"}} for up to thousands of IDs, 50 per call (1 unit each).
    Videos the API doesn't return were deleted or made private."""
    session = session or youtube_auth.session
    ids = list(dict.fromkeys(i for i in video_ids if i))
    info = {}
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        params = {"part": "snippet,status,contentDetails", "id": ",".join(chunk), "maxResults": "50"}
        data = session.api_get(f"{API}/videos", params)
        for item in data.get("items") or []:
            snippet = item.get("snippet", {})
            info[item["id"]] = {"title": snippet.get("title", ""), "channel": snippet.get("channelTitle", ""),
                                "status": availability_of(item, region)}
        for video_id in chunk:
            info.setdefault(video_id, {"title": "", "channel": "", "status": GONE})
    return info
