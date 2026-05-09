import struct
from dataclasses import dataclass
from typing import List
from .header import PacketHeader, HEADER_SIZE

# Per-car lap data: 43 bytes each, 22 cars
LAP_FORMAT = "<IIHHfffBBBBBBBBBBBBBBH"
LAP_SIZE = struct.calcsize(LAP_FORMAT)  # 43


@dataclass
class LapData:
    last_lap_time_in_ms: int
    current_lap_time_in_ms: int
    sector1_time_ms_part: int
    sector1_time_minutes_part: int
    sector2_time_ms_part: int
    sector2_time_minutes_part: int
    delta_to_car_in_front_ms_part: int
    delta_to_race_leader_ms_part: int
    lap_distance: float
    total_distance: float
    safety_car_delta: float
    car_position: int           # 1-based race position
    current_lap_num: int
    pit_status: int             # 0=none, 1=pitting, 2=in pit area
    num_pit_stops: int
    sector: int                 # 0, 1, 2
    current_lap_invalid: int    # 0=valid, 1=invalid
    penalties: int              # accumulated time penalties (seconds)
    total_warnings: int
    corner_cutting_warnings: int
    num_unserved_drive_through_pens: int
    num_unserved_stop_go_pens: int
    grid_position: int
    driver_status: int          # 0=garage, 1=flying lap, 2=in lap, 3=out lap, 4=on track
    result_status: int          # 0=invalid, 1=inactive, 2=active, 3=finished, 4=dnf, 5=dsq, 6=not classified, 7=retired
    pit_lane_timer_active: int
    pit_lane_time_in_lane_in_ms: int
    pit_stop_timer_in_ms: int
    pit_stop_should_serve_pen: int
    speed_trap_fastest_speed: float
    speed_trap_num_times: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "LapData":
        # F1 25 LapData is 60 bytes per car
        fmt = "<IIHHHHHHfffBBBBBBBBBBBBBBBHHBfB"
        size = struct.calcsize(fmt)
        fields = struct.unpack_from(fmt, data, offset)
        return cls(*fields)


@dataclass
class PacketLapData:
    header: PacketHeader
    lap_data: List[LapData]     # 22 entries
    time_trial_pb_car_idx: int
    time_trial_rival_car_idx: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketLapData":
        header = PacketHeader.from_bytes(data)
        lap_data = []
        # F1 25 LapData per car: use a manually sized struct
        fmt = "<IIHHHHHHfffBBBBBBBBBBBBBBBHHBfB"
        car_size = struct.calcsize(fmt)
        offset = HEADER_SIZE
        for _ in range(22):
            fields = struct.unpack_from(fmt, data, offset)
            lap_data.append(LapData(*fields))
            offset += car_size
        tt_pb, tt_rival = struct.unpack_from("<BB", data, offset)
        return cls(header=header, lap_data=lap_data,
                   time_trial_pb_car_idx=tt_pb,
                   time_trial_rival_car_idx=tt_rival)
