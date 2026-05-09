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

### Run the Bot

```bash
cp .env.example .env   # Fill in Discord Token and channel ID
python -m bot.main
```

---

## Publishing a New Release

```bash
git tag v1.0.0
git push --tags
```

GitHub Actions automatically builds the exe in a Windows environment and creates a Release with the file ready to download.
