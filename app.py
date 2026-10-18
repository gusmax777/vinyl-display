import asyncio
import os
import requests
import re
import wave
import math
import struct
import subprocess
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from shazamio import Shazam
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN", "")
DISCOGS_USERNAME = os.getenv("DISCOGS_USERNAME", "")
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "plughw:2,0")
PORT = int(os.getenv("PORT", 8080))
LANGUAGE = os.getenv("LANGUAGE", "en").lower().strip()
SAMPLE_FILE = "/tmp/sample.wav"

SILENCE_THRESHOLD = 400

# UI Label translations based on LANGUAGE
I18N = {
    "de": {
        "status_badge": "VINYL ANALOG WIEDERGABE",
        "idle_title": "Warte auf Nadel...",
        "idle_artist": "Starte den Plattenspieler",
        "idle_summary": "Lege eine Schallplatte auf, um Hintergrundgeschichten und Details anzuzeigen.",
        "label_album": "Album",
        "label_year": "Erscheinungsjahr",
        "label_genre": "Genre",
        "label_record_label": "Plattenlabel",
        "label_history": "Hintergrund & Geschichte",
        "label_recent": "Zuletzt gespielte Alben",
        "fallback_story": "Aktuelle Wiedergabe: '{title}' aus dem Album '{album}' von {artist}."
    },
    "en": {
        "status_badge": "VINYL ANALOG PLAYBACK",
        "idle_title": "Waiting for needle...",
        "idle_artist": "Start the turntable",
        "idle_summary": "Put a record on to display background stories and album details.",
        "label_album": "Album",
        "label_year": "Release Year",
        "label_genre": "Genre",
        "label_record_label": "Record Label",
        "label_history": "Background & History",
        "label_recent": "Recently Played Albums",
        "fallback_story": "Now playing '{title}' from the album '{album}' by {artist}."
    }
}

t = I18N.get(LANGUAGE, I18N["en"])

app = FastAPI()
shazam = Shazam()

# Serve static directory for SVGs and local assets
app.mount("/static", StaticFiles(directory="/home/admin/vinyl-display/templates"), name="static")

IDLE_STATE = {
    "title": t["idle_title"],
    "artist": t["idle_artist"],
    "album": "",
    "year": "",
    "label": "",
    "genre": "",
    "summary": t["idle_summary"],
    "cover": "",
    "discogs_status": "",
    "recent": [],
    "i18n": t
}

current_track = dict(IDLE_STATE)
recent_albums = []
silence_counter = 0
added_albums_cache = set()

def get_audio_rms(file_path: str) -> float:
    try:
        with wave.open(file_path, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            count = len(frames) // 2
            shorts = struct.unpack(f"{count}h", frames)
            sum_squares = sum(s ** 2 for s in shorts)
            return math.sqrt(sum_squares / count)
    except Exception as e:
        print(f"[RMS Measurement Error] {e}")
        return 1000.0

def add_album_to_discogs_collection(album: str, artist: str):
    detected_label = "—"
    if not DISCOGS_TOKEN or DISCOGS_TOKEN.startswith("your_"):
        return "Discogs token not configured", detected_label

    if any(k in album.lower() or k in artist.lower() for k in ["solfeggio", "hz", "binaural", "meditation"]):
        return "Ignored generic drone", detected_label

    search_key = f"{artist} - {album}".lower()
    headers = {
        "User-Agent": "VinylDisplayPi/2.0 (contact@local.home)",
        "Authorization": f"Discogs token={DISCOGS_TOKEN}"
    }

    try:
        search_url = "https://api.discogs.com/database/search"
        params = {
            "release_title": album,
            "artist": artist,
            "format": "Vinyl",
            "type": "release",
            "per_page": 1
        }
        r = requests.get(search_url, params=params, headers=headers, timeout=5)
        results = r.json().get("results", [])
        if not results:
            del params["format"]
            r = requests.get(search_url, params=params, headers=headers, timeout=5)
            results = r.json().get("results", [])

        if not results:
            return "Album not found on Discogs", detected_label

        release = results[0]
        release_id = release["id"]
        release_title = release.get("title", f"{artist} - {album}")

        labels = release.get("label", [])
        if labels and isinstance(labels, list):
            detected_label = labels[0]

        if search_key in added_albums_cache:
            return f"Already in collection ({release_title})", detected_label

        folder_url = f"https://api.discogs.com/users/{DISCOGS_USERNAME}/collection/folders"
        f_res = requests.get(folder_url, headers=headers, timeout=5)
        folders = f_res.json().get("folders", []) if f_res.status_code == 200 else []
        target_folder_id = next((f["id"] for f in folders if f["id"] != 0), 1)

        check_url = f"https://api.discogs.com/users/{DISCOGS_USERNAME}/collection/folders/0/releases"
        check_res = requests.get(check_url, headers=headers, timeout=5)
        if check_res.status_code == 200:
            existing = [item["id"] for item in check_res.json().get("releases", [])]
            if release_id in existing:
                added_albums_cache.add(search_key)
                return f"Already in collection ({release_title})", detected_label

        add_url = f"https://api.discogs.com/users/{DISCOGS_USERNAME}/collection/folders/{target_folder_id}/releases/{release_id}"
        add_res = requests.post(add_url, headers=headers, timeout=5)

        if add_res.status_code in [200, 201]:
            added_albums_cache.add(search_key)
            print(f"[Discogs] Added to collection: {release_title} (Label: {detected_label})")
            return f"Added to Discogs: {release_title}", detected_label
        else:
            return f"Error adding release ({add_res.status_code})", detected_label

    except Exception as e:
        print(f"[Discogs Error] {e}")
        return f"Discogs Error: {e}", detected_label

def clean_wiki_text(text: str, max_chars: int = 950) -> str:
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
    if not text:
        return ""
    text = re.sub(r'\(.*?(remaster|deluxe|bonus|live|version|anniversary).*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?(remaster|deluxe|bonus|live|version|anniversary).*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'-\s*(remaster|live).*$', '', text, flags=re.IGNORECASE)
    return text.strip()

def get_wiki_story(album: str, artist: str, title: str):
    wiki_lang = "de" if LANGUAGE == "de" else "en"
    headers = {"User-Agent": "VinylDisplayPi/2.0 (contact@local.home)"}
    clean_alb = clean_music_title(album)
    clean_art = clean_music_title(artist)
    clean_tit = clean_music_title(title)

    music_terms = ["album", "studioalbum", "band", "musiker", "lied", "single", "rock", "pop", "titel", "aufgenommen", "veröffentlicht"] if wiki_lang == "de" else ["album", "studio album", "band", "musician", "song", "single", "rock", "pop", "track", "recorded", "released"]
    block_terms = ["solfeggio", "meditation", "porn", "award", "fußball", "football"]

    search_queries = [
        f'"{clean_art}" "{clean_alb}"',
        f'"{clean_alb}" (Album)' if wiki_lang == "de" else f'"{clean_alb}" (album)',
        f'"{clean_art}"',
        f'"{clean_tit}" {clean_art}'
    ]

    for query in search_queries:
        if not query or query.strip() in ['""', '']:
            continue
        try:
            search_url = f"https://{wiki_lang}.wikipedia.org/w/api.php"
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
                    is_music = any(kw in extract_lower for kw in music_terms)
                    is_wrong = any(bad in extract_lower for bad in block_terms)

                    if is_music and not is_wrong and len(extract) > 100:
                        found_year = ""
                        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', extract)
                        if year_match:
                            found_year = year_match.group(1)
                        story = clean_wiki_text(extract)
                        return story, found_year
        except Exception:
            continue

    fallback = t["fallback_story"].format(title=clean_tit, album=clean_alb, artist=clean_art)
    return fallback, ""

def fetch_rich_metadata(artist_name: str, track_title: str, shazam_album: str):
    final_album = clean_music_title(shazam_album) or track_title
    details = {
        "album": final_album,
        "year": "—",
        "label": "—",
        "summary": "",
        "discogs_status": ""
    }

    disc_status, disc_label = add_album_to_discogs_collection(final_album, artist_name)
    details["discogs_status"] = disc_status
    if disc_label and disc_label != "—":
        details["label"] = disc_label

    try:
        url = "https://musicbrainz.org/ws/2/recording"
        params = {
            "query": f'recording:"{track_title}" AND artist:"{artist_name}"',
            "fmt": "json",
            "limit": 3
        }
        r = requests.get(url, params=params, headers={"User-Agent": "VinylDisplayPi/2.0"}, timeout=4)
        if r.status_code == 200:
            recordings = r.json().get("recordings", [])
            if recordings:
                releases = recordings[0].get("releases", [])
                years = []
                for rel in releases:
                    d = rel.get("date", "")
                    match = re.search(r'\b(19\d\d|20\d\d)\b', d)
                    if match:
                        years.append(int(match.group(1)))
                    if details["label"] == "—":
                        label_info = rel.get("label-info-list", [])
                        if label_info and label_info[0].get("label"):
                            details["label"] = label_info[0]["label"].get("name", "—")
                if years:
                    details["year"] = str(min(years))
    except Exception as e:
        print(f"[MusicBrainz Error] {e}")

    wiki_text, wiki_year = get_wiki_story(final_album, artist_name, track_title)
    details["summary"] = wiki_text or t["fallback_story"].format(title=track_title, album=final_album, artist=artist_name)
    if details["year"] == "—" and wiki_year:
        details["year"] = wiki_year

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
    global current_track, recent_albums, silence_counter
    while True:
        try:
            await record_sample(seconds=5)
            if os.path.exists(SAMPLE_FILE):
                volume = get_audio_rms(SAMPLE_FILE)

                if volume < SILENCE_THRESHOLD:
                    silence_counter += 1
                    if silence_counter >= 2 and current_track["title"] != IDLE_STATE["title"]:
                        print(f"[Audio] Silence detected (RMS: {volume:.1f}). Resetting display to idle.")
                        current_track = dict(IDLE_STATE)
                        current_track["recent"] = recent_albums
                    await asyncio.sleep(8)
                    continue

                silence_counter = 0
                out = await shazam.recognize(SAMPLE_FILE)
                track = out.get("track")
                if track:
                    title = track.get("title", "Unknown Track")
                    artist = track.get("subtitle", "Unknown Artist")

                    block_terms = ["solfeggio", "hz", "binaural", "meditation frequency", "brown noise", "white noise"]
                    if any(b in title.lower() or b in artist.lower() for b in block_terms):
                        print(f"[Shazam Ignored] Filtered drone artifact: {title} by {artist}")
                        await asyncio.sleep(8)
                        continue

                    cover = track.get("images", {}).get("coverart", "")
                    genres = track.get("genres", {}).get("primary", "Rock / Vinyl")

                    shazam_album = ""
                    for section in track.get("sections", []):
                        if section.get("type") == "SONG":
                            for meta in section.get("metadata", []):
                                if meta.get("title") == "Album":
                                    shazam_album = meta.get("text")

                    if current_track["title"] != title:
                        print(f"[Track Detected] {artist} - {title} (RMS: {volume:.1f})")
                        meta = await asyncio.to_thread(fetch_rich_metadata, artist, title, shazam_album)
                        album_name = meta["album"] or title

                        if not recent_albums or recent_albums[0].get("album") != album_name:
                            if cover:
                                recent_albums.insert(0, {
                                    "album": album_name,
                                    "artist": artist,
                                    "cover": cover
                                })
                                recent_albums = recent_albums[:5]

                        current_track = {
                            "title": title,
                            "artist": artist,
                            "album": album_name,
                            "year": meta["year"],
                            "label": meta["label"],
                            "genre": genres,
                            "summary": meta["summary"],
                            "cover": cover,
                            "discogs_status": meta["discogs_status"],
                            "recent": recent_albums,
                            "i18n": t
                        }
        except Exception as e:
            print(f"[Loop Error] {e}")

        await asyncio.sleep(10)

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

@app.get("/sonos.mp3")
async def stream_for_sonos():
    """Streams live vinyl audio as high-quality MP3 for Sonos speakers."""
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "alsa",
        "-i", "plug:shared_vinyl",
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        "-ar", "44100",
        "-ac", "2",
        "-f", "mp3",
        "pipe:1"
    ]
    
    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1024 * 64
    )

    def generate_chunks():
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.terminate()
            proc.wait()

    return StreamingResponse(
        generate_chunks(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
