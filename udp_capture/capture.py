"""
Run on the recorder's machine during a race:
    python -m udp_capture.capture --db data/race.db

Listens on UDP port 20777, parses F1 25 packets,
writes to SQLite, then zips the db for upload.
"""
import argparse
import signal
import socket
import sys
import zipfile
from pathlib import Path

from .packets import PACKET_MAP
from .packets.header import PacketHeader, HEADER_SIZE
from .recorder import Recorder


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

        packets_received += 1

        if len(data) < HEADER_SIZE:
            continue

        try:
            header = PacketHeader.from_bytes(data)
        except Exception:
            continue

        packet_cls = PACKET_MAP.get(header.packet_id)
        if packet_cls is None:
            continue

        try:
            pkt = packet_cls.from_bytes(data)
        except Exception as e:
            print(f"[recorder] Parse error packet_id={header.packet_id}: {e}", file=sys.stderr)
            continue

        packets_parsed += 1

        try:
            from .packets.session import PacketSessionData
            from .packets.participants import PacketParticipantsData
            from .packets.lap_data import PacketLapData
            from .packets.event import PacketEventData
            from .packets.final_classification import PacketFinalClassificationData

            if isinstance(pkt, PacketSessionData):
                recorder.handle_session(pkt)
            elif isinstance(pkt, PacketParticipantsData):
                recorder.handle_participants(pkt)
            elif isinstance(pkt, PacketLapData):
                recorder.handle_lap_data(pkt)
            elif isinstance(pkt, PacketEventData):
                recorder.handle_event(pkt)
            elif isinstance(pkt, PacketFinalClassificationData):
                recorder.handle_final_classification(pkt)
        except Exception as e:
            print(f"[recorder] DB write error: {e}", file=sys.stderr)

    sock.close()
    recorder.close()
    print(f"\n[recorder] Stopped. Received={packets_received} Parsed={packets_parsed}")
    zip_db(args.db)


if __name__ == "__main__":
    run()
