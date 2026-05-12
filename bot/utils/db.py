"""Async SQLite helpers used by the bot (read-only queries against recordings)."""
import aiosqlite
from typing import Any, List, Optional


async def fetchall(db_path: str, sql: str, params: tuple = ()) -> List[Any]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchall()


async def fetchone(db_path: str, sql: str, params: tuple = ()) -> Optional[Any]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchone()


async def get_session_info(db_path: str, session_uid: Optional[int] = None):
    """Return the most recent session, or a specific one by UID."""
    if session_uid:
        return await fetchone(db_path, "SELECT * FROM sessions WHERE session_uid=?", (session_uid,))
    return await fetchone(db_path, "SELECT * FROM sessions ORDER BY recorded_at DESC LIMIT 1")


async def get_participants(db_path: str, session_uid: int) -> List[Any]:
    return await fetchall(
        db_path,
        "SELECT * FROM participants WHERE session_uid=? ORDER BY car_index",
        (session_uid,),
    )


async def get_final_results(db_path: str, session_uid: int) -> List[Any]:
    return await fetchall(
        db_path,
        """SELECT fc.*, p.name, p.team_id
           FROM final_classification fc
           JOIN participants p ON fc.session_uid = p.session_uid AND fc.car_index = p.car_index
           WHERE fc.session_uid = ?
           ORDER BY fc.position""",
        (session_uid,),
    )


async def get_lap_snapshots(db_path: str, session_uid: int) -> List[Any]:
    """All lap snapshots ordered by session time — used by the visualizer."""
    return await fetchall(
        db_path,
        """SELECT ls.*, p.name, p.team_id
           FROM lap_snapshots ls
           JOIN participants p ON ls.session_uid = p.session_uid AND ls.car_index = p.car_index
           WHERE ls.session_uid = ?
           ORDER BY ls.session_time, ls.car_index""",
        (session_uid,),
    )


async def get_ftlp_timeline(db_path: str, session_uid: int) -> List[tuple]:
    """Fastest lap events as [(session_time, vehicle_idx)] sorted by time."""
    rows = await fetchall(
        db_path,
        "SELECT session_time, vehicle_idx FROM events WHERE session_uid=? AND event_code='FTLP' ORDER BY session_time",
        (session_uid,),
    )
    return [(r["session_time"], r["vehicle_idx"]) for r in rows]


async def get_sc_timeline(db_path: str, session_uid: int) -> List[tuple]:
    """Safety car status changes as [(session_time, status)] sorted by time."""
    rows = await fetchall(
        db_path,
        "SELECT session_time, status FROM safety_car_timeline WHERE session_uid=? ORDER BY session_time",
        (session_uid,),
    )
    return [(r["session_time"], r["status"]) for r in rows]


async def get_rdfl_timeline(db_path: str, session_uid: int) -> List[tuple]:
    """Red flag periods as [(rdfl_start, rdfl_end)] pairs.
    rdfl_end is the session_time of the next SCAR event after the red flag,
    or None if the race ended under red flag conditions."""
    rdfl_rows = await fetchall(
        db_path,
        "SELECT session_time FROM events WHERE session_uid=? AND event_code='RDFL' ORDER BY session_time",
        (session_uid,),
    )
    scar_rows = await fetchall(
        db_path,
        "SELECT session_time FROM events WHERE session_uid=? AND event_code='SCAR' ORDER BY session_time",
        (session_uid,),
    )
    rdfl_times = [r["session_time"] for r in rdfl_rows]
    scar_times = [r["session_time"] for r in scar_rows]
    result = []
    for rdfl_t in rdfl_times:
        next_scar = next((s for s in scar_times if s > rdfl_t), None)
        result.append((rdfl_t, next_scar))
    return result
