import struct
from dataclasses import dataclass
from .header import PacketHeader, HEADER_SIZE

TRACK_NAMES = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Shanghai", 3: "Sakhir (Bahrain)",
    4: "Catalunya", 5: "Monaco", 6: "Montreal", 7: "Silverstone",
    8: "Hockenheim", 9: "Hungaroring", 10: "Spa", 11: "Monza",
    12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Texas",
    16: "Brazil", 17: "Austria", 18: "Sochi", 19: "Mexico",
    20: "Baku (Azerbaijan)", 21: "Sakhir Short", 22: "Silverstone Short",
    23: "Texas Short", 24: "Suzuka Short", 25: "Hanoi", 26: "Zandvoort",
    27: "Imola", 28: "Portimão", 29: "Jeddah", 30: "Miami",
    31: "Las Vegas", 32: "Losail",
}

SESSION_TYPES = {
    0: "Unknown", 1: "P1", 2: "P2", 3: "P3", 4: "Short P",
    5: "Q1", 6: "Q2", 7: "Q3", 8: "Short Q", 9: "OSQ",
    10: "R", 11: "R2", 12: "R3", 13: "Time Trial",
}


@dataclass
class PacketSessionData:
    header: PacketHeader
    weather: int
    track_temperature: int
    air_temperature: int
    total_laps: int
    track_length: int
    session_type: int
    track_id: int
    formula: int
    session_time_left: int
    session_duration: int
    pit_speed_limit: int
    game_paused: int
    is_spectating: int
    spectator_car_index: int
    sli_pro_native_support: int
    num_marshal_zones: int
    # marshal zones omitted for brevity (21 * 5 bytes)
    safety_car_status: int
    network_game: int
    num_weather_forecast_samples: int

    @property
    def track_name(self) -> str:
        return TRACK_NAMES.get(self.track_id, f"Track {self.track_id}")

    @property
    def session_name(self) -> str:
        return SESSION_TYPES.get(self.session_type, f"Type {self.session_type}")

    @classmethod
    def from_bytes(cls, data: bytes) -> "PacketSessionData":
        header = PacketHeader.from_bytes(data)
        offset = HEADER_SIZE
        fmt = "<BBbBHBbHHBBBBBBB"
        fields = struct.unpack_from(fmt, data, offset)
        offset += struct.calcsize(fmt)
        # skip 21 marshal zones (5 bytes each)
        offset += 21 * 5
        safety_car, network, num_wx = struct.unpack_from("<BBB", data, offset)
        return cls(
            header=header,
            weather=fields[0],
            track_temperature=fields[1],
            air_temperature=fields[2],
            total_laps=fields[3],
            track_length=fields[4],
            session_type=fields[5],
            track_id=fields[6],
            formula=fields[7],
            session_time_left=fields[8],
            session_duration=fields[9],
            pit_speed_limit=fields[10],
            game_paused=fields[11],
            is_spectating=fields[12],
            spectator_car_index=fields[13],
            sli_pro_native_support=fields[14],
            num_marshal_zones=fields[15],
            safety_car_status=safety_car,
            network_game=network,
            num_weather_forecast_samples=num_wx,
        )
