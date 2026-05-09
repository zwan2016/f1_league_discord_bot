import struct
from dataclasses import dataclass
from typing import List
from .header import PacketHeader, HEADER_SIZE


@dataclass
class FinalClassificationData:
    position: int
    num_laps: int
    grid_position: int
    points: int
    num_pit_stops: int
    result_status: int          # 2=active/finished, 3=finished, 4=DNF, 5=DSQ, 6=not classified, 7=retired
    best_lap_time_in_ms: int
    total_race_time: float      # seconds, without penalties
    penalties_time: int         # total penalties in seconds
    num_penalties: int
    num_tyre_stints: int
    tyre_stints_actual: List[int]    # 8 entries
    tyre_stints_visual: List[int]    # 8 entries
    tyre_stints_end_laps: List[int]  # 8 entries

    RESULT_STATUS_NAMES = {
        0: "Invalid", 1: "Inactive", 2: "Active", 3: "Finished",
        4: "DNF", 5: "DSQ", 6: "Not Classified", 7: "Retired",
    }

    @property
    def result_name(self) -> str:
        return self.RESULT_STATUS_NAMES.get(self.result_status, "Unknown")

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "FinalClassificationData":
        fmt = "<BBBBBBIfBBB8B8B8B"
        size = struct.calcsize(fmt)
        fields = struct.unpack_from(fmt, data, offset)
        return cls(
            position=fields[0],
            num_laps=fields[1],
            grid_position=fields[2],
            points=fields[3],
            num_pit_stops=fields[4],
            result_status=fields[5],
            best_lap_time_in_ms=fields[6],
            total_race_time=fields[7],
            penalties_time=fields[8],
            num_penalties=fields[9],
            num_tyre_stints=fields[10],
            tyre_stints_actual=list(fields[11:19]),
            tyre_stints_visual=list(fields[19:27]),
            tyre_stints_end_laps=list(fields[27:35]),
        )

    @classmethod
    def size(cls) -> int:
        return struct.calcsize("<BBBBBBIfBBB8B8B8B")


@dataclass
class PacketFinalClassificationData:
    header: PacketHeader
    num_cars: int
    classification_data: List[FinalClassificationData]

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketFinalClassificationData":
        header = PacketHeader.from_bytes(data)
        offset = HEADER_SIZE
        (num_cars,) = struct.unpack_from("<B", data, offset)
        offset += 1
        car_size = FinalClassificationData.size()
        classifications = []
        for _ in range(num_cars):
            classifications.append(FinalClassificationData.from_bytes(data, offset))
            offset += car_size
        return cls(header=header, num_cars=num_cars, classification_data=classifications)
