"""
Run on the recorder's machine during a race:
    python -m udp_capture.capture --db data/race.db

Listens on UDP, parses F1 25 packets via f1-packets library,
writes to SQLite, then zips the db for upload.
"""
import argparse
import signal
import socket
import sys
import zipfile
from pathlib import Path

from f1.packets import PacketHeader, resolve

from .recorder import Recorder

HANDLED_PACKET_IDS = {1, 2, 3, 4, 7, 8}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="F1 25 UDP recorder")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=20777)
    p.add_argument("--db", default="data/race.db")
    return p.parse_args()


def zip_db(db_path: str) -> str:
    out = db_path.replace(".db", ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, Path(db_path).name)
    print(f"[recorder] Saved: {out}")
    return out


def _to_signed_uid(uid) -> int:
    uid = int(uid)
    return uid if uid < 2**63 else uid - 2**64


def run() -> None:
    args = parse_args()
    recorder = Recorder(args.db)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.settimeout(1.0)

    print(f"[recorder] Listening on {args.host}:{args.port} → {args.db}")
    print("[recorder] Press Ctrl+C to stop and save.")

    running = True

    def _stop(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    packets_received = 0
    packets_parsed = 0

    while running:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break

        # Parse header to get packet_id and session_uid for raw storage
        try:
            header = PacketHeader.from_buffer_copy(data)
        except Exception:
            continue

        packet_id = int(header.packet_id)
        session_uid = _to_signed_uid(header.session_uid)
        packets_received += 1

        if packet_id not in HANDLED_PACKET_IDS:
            continue

        try:
            pkt = resolve(data)
        except Exception as e:
            print(f"[recorder] Parse error packet_id={packet_id}: {e}", file=sys.stderr)
            continue

        packets_parsed += 1

        try:
            if packet_id == 1:
                recorder.handle_session(pkt)
            elif packet_id == 2:
                recorder.handle_lap_data(pkt)
            elif packet_id == 3:
                recorder.handle_event(pkt)
            elif packet_id == 4:
                recorder.handle_participants(pkt)
            elif packet_id == 7:
                recorder.handle_car_status(pkt)
            elif packet_id == 8:
                recorder.handle_final_classification(pkt)
        except Exception as e:
            print(f"[recorder] DB write error packet_id={packet_id}: {e}", file=sys.stderr)

    sock.close()
    recorder.close()
    print(f"\n[recorder] Stopped. Received={packets_received} Parsed={packets_parsed}")
    zip_db(args.db)


if __name__ == "__main__":
    run()
