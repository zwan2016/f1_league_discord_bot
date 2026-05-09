"""
Writes parsed UDP packets to SQLite.
Schema is append-only during a race; one recording = one session_uid.
"""
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .packets.lap_data import PacketLapData
from .packets.participants import PacketParticipantsData
from .packets.event import PacketEventData
from .packets.session import PacketSessionData
from .packets.final_classification import PacketFinalClassificationData

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_uid   INTEGER PRIMARY KEY,
    track_name    TEXT,
    session_type  TEXT,
    total_laps    INTEGER,
    recorded_at   INTEGER  -- unix timestamp
);

CREATE TABLE IF NOT EXISTS participants (
    session_uid   INTEGER,
    car_index     INTEGER,
    name          TEXT,
    team_id       INTEGER,
    driver_id     INTEGER,
    race_number   INTEGER,
    ai_controlled INTEGER,
    PRIMARY KEY (session_uid, car_index)
);

CREATE TABLE IF NOT EXISTS lap_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uid     INTEGER,
    session_time    REAL,
    car_index       INTEGER,
    car_position    INTEGER,
    current_lap     INTEGER,
    lap_distance    REAL,
    total_distance  REAL,
    current_lap_time_ms INTEGER,
    last_lap_time_ms    INTEGER,
    pit_status      INTEGER,
    num_pit_stops   INTEGER,
    result_status   INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uid   INTEGER,
    session_time  REAL,
    event_code    TEXT,
    event_name    TEXT,
    vehicle_idx   INTEGER,
    extra_json    TEXT
);

CREATE TABLE IF NOT EXISTS final_classification (
    session_uid   INTEGER,
    car_index     INTEGER,
    position      INTEGER,
    num_laps      INTEGER,
    grid_position INTEGER,
    points        INTEGER,
    num_pit_stops INTEGER,
    result_status TEXT,
    best_lap_ms   INTEGER,
    total_race_time REAL,
    penalties_time  INTEGER,
    PRIMARY KEY (session_uid, car_index)
);
"""


class Recorder:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._session_uid: Optional[int] = None
        # throttle lap snapshots: only write every N seconds of session time
        self._last_snapshot_time: float = -1.0
        self._snapshot_interval: float = 0.5  # seconds of game time

    def handle_session(self, pkt: PacketSessionData) -> None:
        uid = pkt.header.session_uid
        if uid == self._session_uid:
            return
        self._session_uid = uid
        self.conn.execute(
            "INSERT OR IGNORE INTO sessions VALUES (?,?,?,?,?)",
            (uid, pkt.track_name, pkt.session_name, pkt.total_laps, int(time.time())),
        )
        self.conn.commit()

    def handle_participants(self, pkt: PacketParticipantsData) -> None:
        uid = pkt.header.session_uid
        rows = [
            (uid, i, p.name, p.team_id, p.driver_id, p.race_number, p.ai_controlled)
            for i, p in enumerate(pkt.participants[:pkt.num_active_cars])
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO participants VALUES (?,?,?,?,?,?,?)", rows
        )
        self.conn.commit()

    def handle_lap_data(self, pkt: PacketLapData) -> None:
        t = pkt.header.session_time
        if t - self._last_snapshot_time < self._snapshot_interval:
            return
        self._last_snapshot_time = t
        uid = pkt.header.session_uid
        rows = [
            (uid, t, i,
             ld.car_position, ld.current_lap_num, ld.lap_distance, ld.total_distance,
             ld.current_lap_time_in_ms, ld.last_lap_time_in_ms,
             ld.pit_status, ld.num_pit_stops, ld.result_status)
            for i, ld in enumerate(pkt.lap_data)
            if ld.result_status in (2, 3)  # active or finished only
        ]
        self.conn.executemany(
            """INSERT INTO lap_snapshots
               (session_uid, session_time, car_index, car_position, current_lap,
                lap_distance, total_distance, current_lap_time_ms, last_lap_time_ms,
                pit_status, num_pit_stops, result_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()

    def handle_event(self, pkt: PacketEventData) -> None:
        import json
        uid = pkt.header.session_uid
        t = pkt.header.session_time
        extra = {}
        if pkt.fastest_lap:
            extra = {"lap_time": pkt.fastest_lap.lap_time}
        elif pkt.penalty:
            p = pkt.penalty
            extra = {"type": p.penalty_type, "infringement": p.infringement_type,
                     "time": p.time, "lap": p.lap_num}
        elif pkt.overtake:
            extra = {"overtaking": pkt.overtake.overtaking_vehicle_idx,
                     "being_overtaken": pkt.overtake.being_overtaken_vehicle_idx}
        elif pkt.flashback:
            fb = pkt.flashback
            extra = {
                "rewind_to": fb.flashback_session_time,
                "frame": fb.flashback_frame_identifier,
            }
            # Delete all snapshots recorded AFTER the rewind target time —
            # those frames never happened in the final timeline.
            self.conn.execute(
                "DELETE FROM lap_snapshots WHERE session_uid=? AND session_time > ?",
                (uid, fb.flashback_session_time),
            )
            # Allow the next arriving lap packet to be written immediately
            self._last_snapshot_time = fb.flashback_session_time - self._snapshot_interval
            deleted_count = self.conn.execute(
                "SELECT changes()"
            ).fetchone()[0]
            print(
                f"[recorder] Flashback detected — rewound to {fb.flashback_session_time:.1f}s, "
                f"deleted {deleted_count} snapshot rows"
            )

        vehicle_idx = (
            pkt.fastest_lap.vehicle_idx if pkt.fastest_lap else
            pkt.retirement_vehicle_idx if pkt.retirement_vehicle_idx is not None else
            pkt.race_winner_vehicle_idx if pkt.race_winner_vehicle_idx is not None else
            None
        )
        self.conn.execute(
            "INSERT INTO events (session_uid, session_time, event_code, event_name, vehicle_idx, extra_json) VALUES (?,?,?,?,?,?)",
            (uid, t, pkt.event_string_code.decode("ascii", errors="replace"),
             pkt.event_name, vehicle_idx, json.dumps(extra) if extra else None),
        )
        self.conn.commit()

    def handle_final_classification(self, pkt: PacketFinalClassificationData) -> None:
        uid = pkt.header.session_uid
        rows = [
            (uid, i, c.position, c.num_laps, c.grid_position, c.points,
             c.num_pit_stops, c.result_name, c.best_lap_time_in_ms,
             c.total_race_time, c.penalties_time)
            for i, c in enumerate(pkt.classification_data)
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO final_classification VALUES
               (?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
