import struct
from dataclasses import dataclass, field
from typing import List
from .header import PacketHeader, HEADER_SIZE


@dataclass
class ParticipantData:
    ai_controlled: int
    driver_id: int      # 255 = human
    network_id: int
    team_id: int
    my_team: int
    race_number: int
    nationality: int
    name: str           # 48 bytes UTF-8
    your_telemetry: int
    show_online_names: int
    tech_level: int
    platform: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "ParticipantData":
        fmt = "<BBBBBBH48sBBHB"
        size = struct.calcsize(fmt)
        fields = struct.unpack_from(fmt, data, offset)
        name = fields[7].split(b"\x00")[0].decode("utf-8", errors="replace")
        return cls(
            ai_controlled=fields[0],
            driver_id=fields[1],
            network_id=fields[2],
            team_id=fields[3],
            my_team=fields[4],
            race_number=fields[5],
            nationality=fields[6],
            name=name,
            your_telemetry=fields[8],
            show_online_names=fields[9],
            tech_level=fields[10],
            platform=fields[11],
        )

    @classmethod
    def size(cls) -> int:
        return struct.calcsize("<BBBBBBH48sBBHB")


@dataclass
class PacketParticipantsData:
    header: PacketHeader
    num_active_cars: int
    participants: List[ParticipantData]

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketParticipantsData":
        header = PacketHeader.from_bytes(data)
        offset = HEADER_SIZE
        (num_active,) = struct.unpack_from("<B", data, offset)
        offset += 1
        car_size = ParticipantData.size()
        participants = []
        for _ in range(22):
            participants.append(ParticipantData.from_bytes(data, offset))
            offset += car_size
        return cls(header=header, num_active_cars=num_active, participants=participants)
