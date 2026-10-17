# 🎵 Vinyl Now Playing TV Display

A lightweight, automated vinyl listening companion built for Raspberry Pi. It captures analog audio directly from your turntable or stereo receiver via a USB audio interface, identifies the current track in real-time using audio fingerprinting (Shazam), and renders high-resolution cover artwork, album metadata, and background production stories on your TV or smart display.

Optionally, it automatically syncs each identified record directly into your **Discogs** collection folder without duplicate entries.

---

## ✨ Features

- **Automated Audio Recognition:** Periodically samples audio from your USB audio interface and identifies songs using Shazam's algorithm without requiring paid API keys.
- **TV-Optimized Modern Dashboard:** Tailored for 1080p and 4K displays (Amazon Silk Browser, Smart TV web browsers, or Raspberry Pi HDMI Kiosk mode) featuring dynamic ambient blur and clean typography.
- **Album Context & Trivia:** Automatically fetches curated Wikipedia articles covering album recording sessions, studio anecdotes, and production details.
- **Automatic Discogs Synchronization:** Locates the matching vinyl edition on Discogs and adds it to your collection without creating duplicate entries during replay sessions.
- **Low Overhead & Headless Operation:** Runs smoothly in the background as a self-healing `systemd` service on Raspberry Pi 3B, 4, or 5 hardware.

---

## 🎛️ Hardware Requirements

1. **Raspberry Pi:** Model 3B, 3B+, 4, or 5 running Raspberry Pi OS (Debian Bookworm or newer recommended).
2. **Audio Source:** Turntable with an internal/external phono pre-amplifier, or an amplifier with a dedicated line-level output (`Tape Out`, `Rec Out`, or `Zone 2`).
3. **USB Audio Interface:** Class-compliant stereo line-in adapter, such as the **Behringer U-Control UCA202** or **UCA222** (RCA stereo line-in).
4. **Display:** Any television with an integrated browser (Amazon Fire TV running Silk Browser, LG webOS, Samsung Tizen) or a dedicated screen connected via HDMI.

---

## 🚀 Installation & Setup

### 1. Install System Dependencies
Update package indexes and install ALSA audio utilities, Git, and FFmpeg:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv alsa-utils git ffmpeg
```

### 2. Identify Audio Capture Card
Plug your USB audio interface into the Raspberry Pi and inspect the ALSA recording hardware list:

```bash
arecord -l
```

Look for your USB codec (for example: `card 2: CODEC [USB Audio CODEC], device 0`). The resulting ALSA hardware address is formatted as:

```text
plughw:2,0
```

*(If your card index is 1, use `plughw:1,0` instead).*

### 3. Clone Repository & Set Up Virtual Environment

```bash
git clone https://github.com/YOUR_USERNAME/vinyl-display.git /home/admin/vinyl-display
cd /home/admin/vinyl-display

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the template configuration file:

```bash
cp .env.example .env
nano .env
```

Define your runtime settings:

```ini
# ALSA Audio Device identifier (e.g., plughw:2,0 or plughw:1,0)
AUDIO_DEVICE=plughw:2,0

# Optional Discogs Collection Integration
DISCOGS_TOKEN=your_personal_access_token_here
DISCOGS_USERNAME=your_discogs_username_here

# Local Web Server Port
PORT=8080
```

> **Note on Discogs Setup:**
> - Generate your personal token under **Discogs Settings -> Developers -> Generate new token**.
> - Set `DISCOGS_USERNAME` to your public profile username (e.g., `VinylCollector99`), **not** your login email address.

### 5. Interactive Test Run
Verify audio recognition and metadata fetching manually:

```bash
source venv/bin/activate
python3 app.py
```

Drop the needle on a record. After approximately 10 to 15 seconds, the console will print:

```text
[Track Detected] Artist - Track Title (Album: Album Title)
```

Open `http://<YOUR_RASPBERRY_IP>:8080` in your computer or mobile browser to verify the dashboard layout. Press `Ctrl + C` in the terminal to exit the test run.

---

## ⚙️ Running as a Persistent Service (systemd)

To keep the application running continuously in the background and ensure it restarts after reboots:

1. Create a systemd service definition file:

```bash
sudo nano /etc/systemd/system/vinyl.service
```

2. Add the following unit configuration (verify that the user and paths match your installation):

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

3. Reload the systemd daemon, enable the service, and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vinyl.service
sudo systemctl start vinyl.service
```

4. Monitor live service activity and recognition logs:

```bash
journalctl -u vinyl.service -f
```

---

## 📺 Television Display Setup

### Amazon Fire TV / Silk Browser
1. Open the **Amazon Silk Browser** on your Fire TV.
2. Navigate to `http://<YOUR_RASPBERRY_IP>:8080`.
3. Press the **Menu button (☰)** on your Fire TV remote control and select **Enter Fullscreen** (or click the fullscreen icon on the toolbar).
4. Bookmark the link or install **Bookmarker 1** from the Amazon Appstore to place a direct launcher tile on your Fire TV home screen.

### Smart TV (LG webOS / Samsung Tizen)
1. Open the integrated web browser.
2. Enter the Raspberry Pi dashboard address: `http://<YOUR_RASPBERRY_IP>:8080`.
3. Enable fullscreen mode via the browser toolbar and save the address as a browser bookmark or speed-dial item.

---

## 🛠️ Troubleshooting

- **No track recognized ("Waiting for needle..."):**
  Verify audio capture by running a manual 5-second recording test:
  ```bash
  arecord -D plughw:2,0 -f cd -d 5 /tmp/test.wav
  ls -lh /tmp/test.wav
  ```
  Ensure the resulting file is approximately ~880 KB. If it is empty or silent, check your RCA cables and pre-amp output levels.
- **Discogs Error 404:**
  Ensure that `DISCOGS_USERNAME` is set to your exact public profile name on Discogs, not your email address.
- **Port Conflicts:**
  If port 8080 is already occupied by another service on your Raspberry Pi, adjust `PORT=8080` inside your `.env` file to another port (e.g., `8085`).

---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
