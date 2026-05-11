# F1 25 League Discord Bot

Real-time telemetry capture for F1 25 + automatic post-race animated GIF generation.

---

## For Recorders: Quick Start

> The recorder runs this program during the race, then uploads the generated file to Discord after the race ends.

### Option 1: Download the exe directly (recommended — no software installation required)

1. Go to the [Releases](../../releases) page and download the latest `F1_Recorder.exe`
2. Double-click to run it and follow the on-screen instructions to configure UDP in F1 25
3. Start the race and keep the program running in the background
4. After the race, press `Ctrl+C` — the program automatically generates `race.zip` in the same directory
5. Upload `race.zip` to the designated Discord channel

**About security**: This exe is automatically built by GitHub Actions from this repository's source code. The build process is fully transparent — visit the [Actions](../../actions) page to view detailed logs for every build. The downloaded file corresponds directly to the source code.

### Option 2: Run with Python directly

```bash
git clone https://github.com/zwan2016/f1_leagure_discord_bot.git
cd f1_leagure_discord_bot
pip install -r requirements.txt
python -m udp_capture.capture --db data/race.db
```

### F1 25 In-Game Settings

Go to `Settings → Telemetry Settings` and configure as follows:

| Option | Value |
|--------|-------|
| UDP Telemetry | On |
| UDP Format | 2025 |
| UDP IP Address | `127.0.0.1` (same PC as game) or recorder's LAN IP |
| UDP Port | `20777` (default) or the port you entered at startup |
| UDP Send Rate | 60Hz (recommended) |

---

## For Developers: Project Structure

```
├── recorder_app.py              # Windows exe entry point, includes in-game setup guide
├── requirements.txt
├── .env.example                 # Bot environment variable template
├── build/
│   └── recorder.spec            # PyInstaller build config
├── .github/workflows/
│   └── build-recorder.yml       # GitHub Actions auto-build and release
├── udp_capture/                 # Telemetry capture (stdlib only, no third-party deps)
│   ├── capture.py               # UDP listener main loop, saves zip on Ctrl+C
│   ├── recorder.py              # SQLite writer, handles Flashback rewind
│   └── packets/                 # F1 25 UDP packet parsers
│       ├── header.py            # Common header (29 bytes)
│       ├── session.py           # Packet ID 1: track, laps, session type
│       ├── lap_data.py          # Packet ID 2: live position, lap time, pit status
│       ├── event.py             # Packet ID 3: fastest lap, overtake, penalty, flashback
│       ├── participants.py      # Packet ID 4: driver names, teams
│       └── final_classification.py  # Packet ID 8: final results
├── bot/                         # Discord Bot
│   ├── main.py                  # Bot entry point
│   ├── cogs/race.py             # Receive file upload → parse → send embed + GIF
│   └── utils/db.py              # Async SQLite query utilities
└── visualizer/
    └── race_animation.py        # matplotlib animated GIF generator
```

### Build exe locally

```bash
pip install pyinstaller
pyinstaller build/recorder.spec
# Output: dist/F1_Recorder.exe
```

### Run the Bot locally

```bash
echo "your-discord-token" > config/discord_token
echo "your-channel-id"   > config/channels   # one ID per line; empty = all channels
python3 -m bot.main
```

### Deploy the Bot to a Server (Oracle Cloud Free Tier recommended)

**1. Create a VM**

In the OCI Console, go to **Compute → Instances → Create Instance**:
- Shape: `VM.Standard.A1.Flex` (ARM, Always Free) — 2 OCPUs, 12 GB RAM
- OS: Ubuntu 22.04
- Make sure to assign a public IP and download the SSH private key

**2. SSH into the VM**

```bash
chmod 400 ~/Downloads/your-key.key
ssh -i ~/Downloads/your-key.key ubuntu@<public-ip>
```

**3. Install dependencies**

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv ffmpeg git
```

**4. Clone and set up**

```bash
git clone https://github.com/zwan2016/f1_leagure_discord_bot.git
cd f1_leagure_discord_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**5. Configure**

```bash
echo "your-discord-token" > config/discord_token
echo "your-channel-id"   > config/channels
# Optionally restrict by role:
echo "League Member" > config/roles
```

**6. Test run**

```bash
python3 -m bot.main
# Should print: [bot] Logged in as ...
# Ctrl+C to stop
```

**7. Set up systemd for auto-start and crash recovery**

```bash
sudo nano /etc/systemd/system/f1bot.service
```

Paste:

```ini
[Unit]
Description=F1 League Discord Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/f1_leagure_discord_bot
ExecStart=/home/ubuntu/f1_leagure_discord_bot/.venv/bin/python3 -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable f1bot
sudo systemctl start f1bot
sudo systemctl status f1bot
```

**Useful commands**

```bash
journalctl -u f1bot -f          # live logs
sudo systemctl restart f1bot    # restart after git pull
```

**Updating the bot**

```bash
cd ~/f1_leagure_discord_bot && git pull && sudo systemctl restart f1bot
```

---

## Publishing a New Release

```bash
git tag v1.0.0
git push --tags
```

GitHub Actions automatically builds the exe in a Windows environment and creates a Release with the file ready to download.
