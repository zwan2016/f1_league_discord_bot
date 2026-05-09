import struct
from dataclasses import dataclass

# F1 25 packet header: 29 bytes
HEADER_FORMAT = "<HBBBBBQfIIBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 29


@dataclass
class PacketHeader:
    packet_format: int       # 2025
    game_year: int           # 25
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int
    secondary_player_car_index: int  # 255 if no split-screen

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketHeader":
        fields = struct.unpack_from(HEADER_FORMAT, data)
        return cls(*fields)
