# 🎵 Vinyl Now Playing TV Display

A lightweight, automated vinyl listening companion built for the Raspberry Pi. It digitizes analog audio directly from your turntable via a **Behringer UFO202** (integrated phono preamplifier & USB audio interface), identifies the currently spinning record in real time using Shazam's acoustic fingerprinting, and renders high-resolution album artwork, metadata, and production trivia onto your television or smart screen.

Identified albums are seamlessly synced to your **Discogs** collection while preventing duplicate entries during replay sessions.

---

## ✨ Features

- **Direct Phono Input & Plug-and-Play Digitization:** Specifically configured for the **Behringer UFO202** USB audio interface, eliminating the need for an external phono stage.
- **Smart Silence & Drone Detection (RMS Volume Gating):** Samples audio in 5-second intervals and analyzes the root mean square (RMS) amplitude. Needle lift-offs, lead-in/run-out groove crackle, and monotonous ground hums are prevented from triggering false positive recognition (e.g., meditative drone frequencies).
- **Multi-Language Support (`LANGUAGE=de` / `LANGUAGE=en`):** Configurable directly in your `.env` file. Switches all dashboard labels dynamically and queries either German (`de.wikipedia.org`) or English (`en.wikipedia.org`) Wikipedia for localized recording anecdotes and artist background stories.
- **Authentic Record Label Detection:** Dynamically extracts the actual vinyl label (e.g., *EMI Electrola*, *Columbia*, *Scotti Bros.*) via the Discogs API and MusicBrainz.
- **TV-Optimized Dark UI:** High-contrast dashboard with dynamic ambient background glow, live SVG turntable standby graphics, and responsive metadata tiles.
- **Recently Played History:** Compact, horizontal thumbnail carousel displaying the last 5 records played during your listening session.
- **Automated Discogs Synchronization:** Automatically locates the exact vinyl press and adds it to your collection without duplicate additions.
- **Self-Healing `systemd` Service:** Runs headless in the background and restarts automatically on reboot.

---

## 🎛️ Hardware Setup

1. **Raspberry Pi:** Raspberry Pi 3B, 3B+, 4, or 5 running Raspberry Pi OS (Debian Bookworm or newer recommended).
2. **Turntable:** Any standard record player with RCA phono cables and ground wire.
3. **Audio Interface:** **Behringer U-Phono UFO202**:
   - Set the physical input switch on the side of the UFO202 to **PHONO** (unless your turntable already features an integrated line preamp, in which case set it to **LINE**).
   - Connect your turntable's ground lead to the ground thumb screw on the UFO202 to eliminate 50/60 Hz mains hum.
   - Connect the UFO202's USB cable directly to a USB port on the Raspberry Pi.
4. **Display:** Any TV running an integrated browser (Fire TV Silk Browser, LG webOS, Samsung Tizen) or a dedicated screen connected via HDMI.

---

## 🚀 Installation & System Configuration

### 1. Install System Dependencies

Open a terminal on your Raspberry Pi and install the necessary audio capture utilities, compilers, and Git:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv alsa-utils git ffmpeg
```

### 2. Identify the Behringer UFO202 ALSA Address

List all attached recording devices:

```bash
arecord -l
```

Look for the USB Audio entry (e.g., `card 2: CODEC [USB Audio CODEC], device 0`). The resulting ALSA hardware identifier is formatted as:

```text
plughw:2,0
```

*(If the audio codec appears under card 1, use `plughw:1,0`).*

### 3. Clone Repository & Set Up Virtual Environment

```bash
cd /home/admin
git clone https://github.com/Gusmax777/vinyl-display.git /home/admin/vinyl-display
cd /home/admin/vinyl-display

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create your production configuration from the template:

```bash
cp .env.example .env
nano .env
```

Set your configuration parameters:

```ini
# ALSA hardware device identifier for the Behringer UFO202
AUDIO_DEVICE=plughw:2,0

# Web server port
PORT=8080

# Language preference: 'de' for German, 'en' for English
LANGUAGE=de

# Optional Discogs Collection Integration
DISCOGS_TOKEN=your_personal_access_token_here
DISCOGS_USERNAME=your_discogs_username_here
```

> **Discogs Setup:**
> - Generate a Personal Access Token under **Discogs Settings -> Developers -> Generate new token**.
> - Set `DISCOGS_USERNAME` to your public profile handle (e.g., `VinylCollector`), **not** your login email.

---

## ⚙️ Running as a Persistent Service (`systemd`)

To run the application continuously in the background and ensure automatic restarts upon system boot:

1. Create a `systemd` service file:

```bash
sudo nano /etc/systemd/system/vinyl.service
```

2. Add the following unit configuration (verify that your user and working paths match):

```ini
[Unit]
Description=Vinyl Now Playing Display Service
After=network.target sound.target

[Service]
User=admin
WorkingDirectory=/home/admin/vinyl-display
ExecStart=/home/admin/vinyl-display/venv/bin/python3 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vinyl.service
sudo systemctl restart vinyl.service
```

4. Monitor live status and audio recognition logs:

```bash
journalctl -u vinyl.service -f
```

---

## 📺 Television Display Setup

### Amazon Fire TV / Silk Browser
1. Launch the **Silk Browser** on your Fire TV.
2. Navigate to `http://<RASPBERRY_PI_IP>:8080`.
3. Press the **Menu button (☰)** on the remote and select **Enter Fullscreen**.
4. Bookmark the URL or install **Bookmarker 1** from the Amazon Appstore to pin a launcher tile to your Fire TV home ribbon.

### Smart TV (LG webOS / Samsung Tizen)
1. Open the integrated web browser.
2. Navigate to `http://<RASPBERRY_PI_IP>:8080`.
3. Activate the browser's full-screen toggle and save the site to your favorites.

---

## 🛠️ Troubleshooting

- **Audio levels too low or buzzing:**
  - Verify that the physical switch on the Behringer UFO202 is set to **PHONO**.
  - Ensure the turntable's thin ground cable is firmly screwed to the UFO202 ground terminal.
- **Test manual recording:**
  Run a 5-second capture test to verify input:
  ```bash
  arecord -D plughw:2,0 -f cd -d 5 /tmp/test.wav
  ls -lh /tmp/test.wav
  ```
  The file should be approximately ~880 KB.
- **Discogs 404 Error:**
  Ensure `DISCOGS_USERNAME` is your public profile username, not an email address.
- **Git Push rejected on Pi:**
  Synchronize remote changes with `git pull origin main --rebase` before running `git push origin main`.

---

## 📄 License

Distributed under the [MIT License](LICENSE).
