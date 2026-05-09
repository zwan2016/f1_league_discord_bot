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
