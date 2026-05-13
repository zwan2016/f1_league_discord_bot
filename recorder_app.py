"""
Entry point for the Windows exe.
Double-click to run; press Ctrl+C or close the window to stop and save.
"""
import os
import sys
import socket

BANNER = r"""
  _____ _   _     ____  ____    ____                        _
 |  ___/ | | |   |___ \| ___|  |  _ \ ___  ___ ___  _ __ __| | ___ _ __
 | |_  | | | |_____  ) |___ \  | |_) / _ \/ __/ _ \| '__/ _` |/ _ \ '__|
 |  _| | | | |___/ /  ___) |  |  _ <  __/ (_| (_) | | | (_| |  __/ |
 |_|   |_| |_|  /____||____/   |_| \_\___|\___\___/|_|  \__,_|\___|_|

  F1 25 Telemetry Recorder  |  github.com/zwan2016/f1_leagure_discord_bot
"""


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


DEFAULT_PORT = 20777


def _prompt_port() -> int:
    while True:
        try:
            raw = input(f"  UDP port to listen on [{DEFAULT_PORT}]: ").strip()
            if raw == "":
                return DEFAULT_PORT
            port = int(raw)
            if 1 <= port <= 65535:
                return port
            print("  Please enter a number between 1 and 65535.")
        except ValueError:
            print("  Invalid input — please enter a port number.")


def main() -> None:
    print(BANNER)
    print("=" * 70)
    print(f"  Your local IP : {_local_ip()}")
    print()
    print("  Some setups (SimHub, Moza Portal) forward telemetry to a different")
    print("  port. Enter the port your forwarder is sending to, or press Enter")
    print("  to use the F1 25 default (20777).")
    print()
    port = _prompt_port()
    print()
    print("  In F1 25, go to:")
    print("    Settings → Telemetry Settings")
    print("    UDP Telemetry  : On")
    print("    UDP Format     : 2025")
    print("    UDP IP Address : 127.0.0.1  (same PC)  or your IP above (LAN)")
    print(f"    UDP Port       : {port}")
    print("    UDP Send Rate  : 20Hz  (recommended)")
    print("=" * 70)
    print()

    # Determine output path: next to the exe when frozen, else ./data/
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.join(os.path.dirname(__file__), "data")

    os.makedirs(base_dir, exist_ok=True)
    db_path = os.path.join(base_dir, "race.db")

    print(f"  Output file   : {db_path}")
    print()
    print("  Press Ctrl+C (or close this window) to STOP recording and save.\n")

    # Patch sys.argv so capture.run() picks up our db path and port
    sys.argv = ["recorder", "--db", db_path, "--port", str(port)]

    try:
        from udp_capture.capture import run
        run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        input("\nPress Enter to exit...")
        sys.exit(1)

    # Keep window open on Windows so the user can read the final message
    if sys.platform == "win32":
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
