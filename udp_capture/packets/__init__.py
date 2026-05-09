from .header import PacketHeader
from .lap_data import PacketLapData
from .participants import PacketParticipantsData
from .event import PacketEventData
from .session import PacketSessionData
from .final_classification import PacketFinalClassificationData

PACKET_MAP = {
    2: PacketLapData,
    3: PacketEventData,
    4: PacketParticipantsData,
    1: PacketSessionData,
    8: PacketFinalClassificationData,
}
