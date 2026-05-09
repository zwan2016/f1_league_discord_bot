import struct
from dataclasses import dataclass
from typing import Optional
from .header import PacketHeader, HEADER_SIZE

# 4-byte ASCII event string codes
EVENT_CODES = {
    b"SSTA": "Session Started",
    b"SEND": "Session Ended",
    b"FTLP": "Fastest Lap",
    b"RTMT": "Retirement",
    b"DRSE": "DRS Enabled",
    b"DRSD": "DRS Disabled",
    b"TMPT": "Team Mate In Pits",
    b"CHQF": "Chequered Flag",
    b"RCWN": "Race Winner",
    b"PENA": "Penalty Issued",
    b"SPTP": "Speed Trap Triggered",
    b"STLG": "Start Lights",
    b"LGOT": "Lights Out",
    b"DTSV": "Drive Through Served",
    b"SGSV": "Stop Go Served",
    b"FLBK": "Flashback",
    b"BUTN": "Button Status",
    b"RDFL": "Red Flag",
    b"OVTK": "Overtake",
    b"SCAR": "Safety Car",
    b"COLI": "Collision",
}


@dataclass
class FastestLapEvent:
    vehicle_idx: int
    lap_time: float


@dataclass
class PenaltyEvent:
    penalty_type: int
    infringement_type: int
    vehicle_idx: int
    other_vehicle_idx: int
    time: int
    lap_num: int
    places_gained: int


@dataclass
class OvertakeEvent:
    overtaking_vehicle_idx: int
    being_overtaken_vehicle_idx: int


@dataclass
class FlashbackEvent:
    # The session time the game will rewind TO (not the current time)
    flashback_session_time: float
    flashback_frame_identifier: int


@dataclass
class PacketEventData:
    header: PacketHeader
    event_string_code: bytes
    event_name: str
    fastest_lap: Optional[FastestLapEvent] = None
    penalty: Optional[PenaltyEvent] = None
    overtake: Optional[OvertakeEvent] = None
    flashback: Optional[FlashbackEvent] = None
    retirement_vehicle_idx: Optional[int] = None
    race_winner_vehicle_idx: Optional[int] = None

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketEventData":
        header = PacketHeader.from_bytes(data)
        offset = HEADER_SIZE
        code = data[offset:offset + 4]
        offset += 4
        name = EVENT_CODES.get(code, code.decode("ascii", errors="replace"))

        fastest_lap = None
        penalty = None
        overtake = None
        flashback = None
        retirement_idx = None
        winner_idx = None

        if code == b"FTLP":
            idx, lap_time = struct.unpack_from("<Bf", data, offset)
            fastest_lap = FastestLapEvent(vehicle_idx=idx, lap_time=lap_time)
        elif code == b"RTMT":
            (retirement_idx,) = struct.unpack_from("<B", data, offset)
        elif code == b"RCWN":
            (winner_idx,) = struct.unpack_from("<B", data, offset)
        elif code == b"PENA":
            fields = struct.unpack_from("<BBBBBBB", data, offset)
            penalty = PenaltyEvent(*fields)
        elif code == b"OVTK":
            a, b_ = struct.unpack_from("<BB", data, offset)
            overtake = OvertakeEvent(overtaking_vehicle_idx=a, being_overtaken_vehicle_idx=b_)
        elif code == b"FLBK":
            # uint32 frameIdentifier, float sessionTime — the rewind TARGET
            frame_id, session_time = struct.unpack_from("<If", data, offset)
            flashback = FlashbackEvent(
                flashback_session_time=session_time,
                flashback_frame_identifier=frame_id,
            )

        return cls(
            header=header,
            event_string_code=code,
            event_name=name,
            fastest_lap=fastest_lap,
            penalty=penalty,
            overtake=overtake,
            flashback=flashback,
            retirement_vehicle_idx=retirement_idx,
            race_winner_vehicle_idx=winner_idx,
        )
