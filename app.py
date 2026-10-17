import asyncio
import os
import requests
import re
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from shazamio import Shazam
from dotenv import load_dotenv

# Load configuration from .env
load_dotenv()

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN", "")
DISCOGS_USERNAME = os.getenv("DISCOGS_USERNAME", "")
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "plughw:2,0")
PORT = int(os.getenv("PORT", 8080))
SAMPLE_FILE = "/tmp/sample.wav"

app = FastAPI()
shazam = Shazam()

current_track = {
    "title": "Waiting for needle...",
    "artist": "Start the turntable",
    "album": "",
    "year": "",
    "label": "",
    "genre": "",
    "summary": "Put a record on to display background stories and album details.",
    "cover": "",
    "discogs_status": ""
}

# Prevents multiple additions during the same listening session
added_albums_cache = set()

def add_album_to_discogs_collection(album: str, artist: str):
    """Searches for the album on Discogs and adds it to the user's collection."""
    if not DISCOGS_TOKEN or DISCOGS_TOKEN.startswith("your_"):
        return "Discogs token not configured"

    search_key = f"{artist} - {album}".lower()
    if search_key in added_albums_cache:
        return "Already processed in this session"

    headers = {
        "User-Agent": "VinylDisplayPi/2.0 (contact@local.home)",
        "Authorization": f"Discogs token={DISCOGS_TOKEN}"
    }

    try:
        # 1. Fetch valid target folder dynamically
        folder_url = f"https://api.discogs.com/users/{DISCOGS_USERNAME}/collection/folders"
        f_res = requests.get(folder_url, headers=headers, timeout=5)
        if f_res.status_code == 404:
            return f"Error 404: User '{DISCOGS_USERNAME}' not found on Discogs"
        elif f_res.status_code != 200:
            return f"Error fetching folders ({f_res.status_code})"

        folders = f_res.json().get("folders", [])
        target_folder_id = None
        for f in folders:
            if f["id"] != 0:
                target_folder_id = f["id"]
                break

        if target_folder_id is None:
            target_folder_id = 1

        # 2. Search for the vinyl release on Discogs
        search_url = "https://api.discogs.com/database/search"
        params = {
            "release_title": album,
            "artist": artist,
            "format": "Vinyl",
            "type": "release",
            "per_page": 1
        }
        r = requests.get(search_url, params=params, headers=headers, timeout=5)
        if r.status_code != 200:
            return f"Discogs search failed ({r.status_code})"

        results = r.json().get("results", [])
        if not results:
            del params["format"]
            r = requests.get(search_url, params=params, headers=headers, timeout=5)
            results = r.json().get("results", [])

        if not results:
            return "Album not found on Discogs"

        release_id = results[0]["id"]
        release_title = results[0].get("title", f"{artist} - {album}")

        # 3. Check if release is already in collection
        check_url = f"https://api.discogs.com/users/{DISCOGS_USERNAME}/collection/folders/0/releases"
        check_res = requests.get(check_url, headers=headers, timeout=5)
        if check_res.status_code == 200:
            existing = [item["id"] for item in check_res.json().get("releases", [])]
            if release_id in existing:
                added_albums_cache.add(search_key)
                return f"Already in collection ({release_title})"

        # 4. Add release to target collection folder
        add_url = f"https://api.discogs.com/users/{DISCOGS_USERNAME}/collection/folders/{target_folder_id}/releases/{release_id}"
        add_res = requests.post(add_url, headers=headers, timeout=5)

        if add_res.status_code in [200, 201]:
            added_albums_cache.add(search_key)
            print(f"[Discogs] Added to collection: {release_title}")
            return f"Added to Discogs: {release_title}"
        else:
            return f"Error adding release ({add_res.status_code})"

    except Exception as e:
        print(f"[Discogs Error] {e}")
        return f"Discogs Error: {e}"

def clean_wiki_text(text: str, max_chars: int = 950) -> str:
    """Strips headers, references, and Wikipedia formatting."""
    if not text:
        return ""
    text = re.sub(r'==+[^=]+==+', '', text)
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\(Catalog\s*Number:[^\)]+\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rfind('.')
    if cut > 250:
        return text[:cut + 1]
    return text[:max_chars] + "..."

def clean_music_title(text: str) -> str:
    """Removes release tags like (Remastered), (Deluxe Edition), etc."""
    if not text:
        return ""
    text = re.sub(r'\(.*?(remaster|deluxe|bonus|live|version|anniversary).*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?(remaster|deluxe|bonus|live|version|anniversary).*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'-\s*(remaster|live).*$', '', text, flags=re.IGNORECASE)
    return text.strip()

def get_wiki_story(album: str, artist: str, title: str):
    """Searches English Wikipedia with relevant music keyword filters."""
    headers = {"User-Agent": "VinylDisplayPi/2.0 (contact@local.home)"}
    
    clean_alb = clean_music_title(album)
    clean_art = clean_music_title(artist)
    clean_tit = clean_music_title(title)

    MUSIC_KEYWORDS = ["album", "studio album", "band", "musician", "song", "single", "rock", "pop", "track", "recorded", "released"]
    BLOCK_KEYWORDS = ["adult film", "porn", "holiday", "award ceremony", "football"]

    search_queries = [
        f'"{clean_alb}" (album)',
        f'"{clean_alb}" {clean_art}',
        f'"{clean_art}" (band)',
        f'"{clean_art}" (musician)',
        f'"{clean_tit}" {clean_art}',
        clean_alb,
        clean_art
    ]

    for query in search_queries:
        if not query or query.strip() in ['""', '']:
            continue
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1,
                "srlimit": 3
            }
            res = requests.get(search_url, params=params, headers=headers, timeout=3).json()
            results = res.get("query", {}).get("search", [])

            for hit in results:
                page_title = hit["title"]
                
                content_params = {
                    "action": "query",
                    "prop": "extracts",
                    "exsentences": 8,
                    "explaintext": 1,
                    "titles": page_title,
                    "format": "json",
                    "utf8": 1
                }
                page_res = requests.get(search_url, params=content_params, headers=headers, timeout=3).json()
                pages = page_res.get("query", {}).get("pages", {})

                for _, pdata in pages.items():
                    extract = pdata.get("extract", "")
                    extract_lower = extract.lower()

                    is_music = any(kw in extract_lower for kw in MUSIC_KEYWORDS)
                    is_wrong = any(bad in extract_lower for bad in BLOCK_KEYWORDS)

                    if is_music and not is_wrong and len(extract) > 100:
                        found_year = ""
                        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', extract)
                        if year_match:
                            found_year = year_match.group(1)

                        story = clean_wiki_text(extract)
                        return story, found_year
        except Exception:
            continue

    fallback = f"Now playing '{clean_tit}' from the album '{clean_alb}' by {clean_art}."
    return fallback, ""

def fetch_rich_metadata(artist_name: str, track_title: str, shazam_album: str):
    headers = {"User-Agent": "VinylDisplayPi/2.0 (contact@local.home)"}
    details = {
        "album": clean_music_title(shazam_album) or track_title,
        "year": "—",
        "label": "Vinyl Edition",
        "summary": "",
        "discogs_status": ""
    }

    try:
        url = "https://musicbrainz.org/ws/2/recording"
        params = {
            "query": f'recording:"{track_title}" AND artist:"{artist_name}"',
            "fmt": "json",
            "limit": 3
        }
        r = requests.get(url, params=params, headers=headers, timeout=4)
        if r.status_code == 200:
            recordings = r.json().get("recordings", [])
            if recordings:
                rec = recordings[0]
                releases = rec.get("releases", [])
                years = []
                for rel in releases:
                    d = rel.get("date", "")
                    match = re.search(r'\b(19\d\d|20\d\d)\b', d)
                    if match:
                        years.append(int(match.group(1)))
                    rel_title = rel.get("title", "")
                    if rel_title and not details["album"]:
                        details["album"] = clean_music_title(rel_title)
                    label_info = rel.get("label-info-list", [])
                    if label_info and label_info[0].get("label"):
                        details["label"] = label_info[0]["label"].get("name", details["label"])
                if years:
                    details["year"] = str(min(years))
    except Exception as e:
        print(f"[MusicBrainz Error] {e}")

    final_album = clean_music_title(shazam_album) if shazam_album else details["album"]
    details["album"] = final_album

    wiki_text, wiki_year = get_wiki_story(final_album, artist_name, track_title)
    if wiki_text:
        details["summary"] = wiki_text
    else:
        details["summary"] = f"Now playing: {track_title} from the album {final_album} by {artist_name}."

    if details["year"] == "—" and wiki_year:
        details["year"] = wiki_year

    # Sync to Discogs collection
    disc_status = add_album_to_discogs_collection(final_album, artist_name)
    details["discogs_status"] = disc_status

    return details

async def record_sample(seconds=5):
    cmd = [
        "arecord",
        "-D", AUDIO_DEVICE,
        "-f", "cd",
        "-d", str(seconds),
        "-q",
        SAMPLE_FILE
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()

async def recognition_loop():
    global current_track
    while True:
        try:
            await record_sample(seconds=5)
            if os.path.exists(SAMPLE_FILE):
                out = await shazam.recognize(SAMPLE_FILE)
                track = out.get("track")
                if track:
                    title = track.get("title", "Unknown Track")
                    artist = track.get("subtitle", "Unknown Artist")
                    cover = track.get("images", {}).get("coverart", "")
                    genres = track.get("genres", {}).get("primary", "Rock / Vinyl")

                    shazam_album = ""
                    for section in track.get("sections", []):
                        if section.get("type") == "SONG":
                            for meta in section.get("metadata", []):
                                if meta.get("title") == "Album":
                                    shazam_album = meta.get("text")

                    if current_track["title"] != title:
                        print(f"[Track Detected] {artist} - {title} (Album: {shazam_album})")
                        meta = await asyncio.to_thread(fetch_rich_metadata, artist, title, shazam_album)
                        current_track = {
                            "title": title,
                            "artist": artist,
                            "album": meta["album"] or title,
                            "year": meta["year"],
                            "label": meta["label"],
                            "genre": genres,
                            "summary": meta["summary"],
                            "cover": cover,
                            "discogs_status": meta["discogs_status"]
                        }
        except Exception as e:
            print(f"[Loop Error] {e}")

        await asyncio.sleep(12)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(recognition_loop())

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("/home/admin/vinyl-display/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/status")
async def get_status():
    return JSONResponse(current_track)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
