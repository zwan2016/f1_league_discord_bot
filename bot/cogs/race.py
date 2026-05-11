"""
Race cog — handles .zip file uploads from the recorder,
extracts the SQLite DB, generates the animation GIF, and posts it.
"""
import asyncio
import io
import os
import tempfile
import zipfile
from pathlib import Path

import discord
from discord.ext import commands

from bot.utils.db import get_session_info, get_final_results, get_participants


ALLOWED_EXTENSIONS = {".zip", ".db"}
MAX_UPLOAD_BYTES   = 50 * 1024 * 1024   # 50 MB — reject before download
MAX_UNZIP_BYTES    = 200 * 1024 * 1024  # 200 MB — reject oversized zip contents
SQLITE_MAGIC       = b"SQLite format 3\x00"


def _check_role(message: discord.Message, allowed_roles: set[str]) -> bool:
    """Return True if author has at least one of the allowed roles (or no restriction)."""
    if not allowed_roles:
        return True
    author_roles = {r.name for r in getattr(message.author, "roles", [])}
    return bool(author_roles & allowed_roles)


def _validate_zip(data: bytes) -> str:
    """
    Validate zip contents and return the name of the single .db file inside.
    Raises ValueError with a human-readable reason on any problem.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("File is not a valid zip archive.")

    infos = zf.infolist()

    # No path traversal
    for info in infos:
        if ".." in info.filename or info.filename.startswith("/"):
            raise ValueError("Zip contains suspicious paths.")

    # Only .db files allowed inside
    db_files = [i for i in infos if i.filename.endswith(".db")]
    non_db   = [i for i in infos if not i.filename.endswith(".db")]
    if non_db:
        raise ValueError(f"Zip contains unexpected files: {[i.filename for i in non_db]}")
    if not db_files:
        raise ValueError("No .db file found inside the zip.")
    if len(db_files) > 1:
        raise ValueError("Zip contains more than one .db file.")

    # Uncompressed size check
    total_uncompressed = sum(i.file_size for i in infos)
    if total_uncompressed > MAX_UNZIP_BYTES:
        raise ValueError(
            f"Uncompressed content is too large "
            f"({total_uncompressed // 1024 // 1024} MB > {MAX_UNZIP_BYTES // 1024 // 1024} MB limit)."
        )

    return db_files[0].filename


def _extract_db(attachment_bytes: bytes, dest_dir: str) -> str:
    """Validate, extract, and return path to the .db file."""
    db_name = _validate_zip(attachment_bytes)
    with zipfile.ZipFile(io.BytesIO(attachment_bytes)) as zf:
        zf.extract(db_name, dest_dir)
    db_path = os.path.join(dest_dir, db_name)

    # Validate SQLite magic bytes
    with open(db_path, "rb") as f:
        magic = f.read(len(SQLITE_MAGIC))
    if magic != SQLITE_MAGIC:
        raise ValueError("Extracted file is not a valid SQLite database.")

    return db_path


def _format_ms(ms: int) -> str:
    if ms <= 0:
        return "--:--.---"
    minutes, rem = divmod(ms, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{int(minutes)}:{int(seconds):02d}.{int(millis):03d}"


def _build_results_embed(session: dict, results: list, participants: list) -> discord.Embed:
    track = session["track_name"]
    embed = discord.Embed(
        title=f"🏁 {track} — Race Results",
        color=discord.Color.red(),
    )

    name_map = {p["car_index"]: p["name"] for p in participants}
    lines = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for row in results:
        pos = row["position"]
        name = row["name"]
        status = row["result_status"]
        best = _format_ms(row["best_lap_ms"])
        pits = row["num_pit_stops"]
        icon = medals.get(pos, f"**P{pos}**")
        if status in ("DNF", "Retired", "DSQ", "Not Classified"):
            lines.append(f"{icon} {name} — _{status}_")
        else:
            lines.append(f"{icon} {name} — Best: `{best}` | Pits: {pits}")

    embed.description = "\n".join(lines) if lines else "No classification data."
    return embed


class RaceCog(commands.Cog, name="Race"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processing_lock = asyncio.Lock()
        self._queue_size = 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        race_channel_ids = getattr(self.bot, "race_channel_ids", set())
        if race_channel_ids and message.channel.id not in race_channel_ids:
            return

        if not message.attachments:
            return

        allowed_roles = getattr(self.bot, "allowed_roles", set())
        if not _check_role(message, allowed_roles):
            return  # silently ignore — no error message to avoid spam

        for attachment in message.attachments:
            ext = Path(attachment.filename).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            asyncio.create_task(self._process_recording(message, attachment))
            break  # handle one file per message

    async def _process_recording(
        self, message: discord.Message, attachment: discord.Attachment
    ) -> None:
        self._queue_size += 1
        queue_msg = None
        if self._queue_size > 1:
            queue_msg = await message.reply(
                f"⏳ 排队中，前面还有 {self._queue_size - 1} 个任务...",
                mention_author=False,
            )

        try:
            async with self.processing_lock:
                if queue_msg:
                    await queue_msg.delete()
                await self._do_process(message, attachment)
        finally:
            self._queue_size -= 1

    async def _do_process(
        self, message: discord.Message, attachment: discord.Attachment
    ) -> None:
        if attachment.size > MAX_UPLOAD_BYTES:
            await message.reply(
                f"❌ File too large ({attachment.size // 1024 // 1024} MB). "
                f"Max allowed: {MAX_UPLOAD_BYTES // 1024 // 1024} MB.",
                mention_author=False,
            )
            return

        status_msg = await message.reply(
            "📡 Recording received — extracting data...", mention_author=False
        )
        try:
            data = await attachment.read()
        except discord.HTTPException as e:
            await status_msg.edit(content=f"❌ Failed to download file: {e}")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                if attachment.filename.endswith(".zip"):
                    db_path = _extract_db(data, tmpdir)
                else:
                    db_path = os.path.join(tmpdir, attachment.filename)
                    Path(db_path).write_bytes(data)
                    with open(db_path, "rb") as f:
                        magic = f.read(len(SQLITE_MAGIC))
                    if magic != SQLITE_MAGIC:
                        await status_msg.edit(content="❌ File is not a valid SQLite database.")
                        return
            except ValueError as e:
                await status_msg.edit(content=f"❌ {e}")
                return
            except Exception as e:
                await status_msg.edit(content=f"❌ Could not read recording: {e}")
                return

            await status_msg.edit(content="🔍 Parsing race data...")
            try:
                session = await get_session_info(db_path)
                if not session:
                    await status_msg.edit(content="❌ No session data found in recording.")
                    return
                session_uid = session["session_uid"]
                results = await get_final_results(db_path, session_uid)
                participants = await get_participants(db_path, session_uid)
            except Exception as e:
                await status_msg.edit(content=f"❌ DB read error: {e}")
                return

            embed = _build_results_embed(dict(session), results, participants)

            await status_msg.edit(content="🎨 Generating race animation...")
            try:
                mp4_path = await asyncio.get_event_loop().run_in_executor(
                    None, self._generate_animation, db_path, session_uid, tmpdir
                )
            except Exception as e:
                print(f"[race cog] Animation generation failed: {e}")
                mp4_path = None

            if mp4_path and Path(mp4_path).exists():
                mp4_file = discord.File(mp4_path, filename="race_animation.mp4")
                await status_msg.delete()
                await message.channel.send(embed=embed, file=mp4_file)
            else:
                await status_msg.delete()
                await message.channel.send(embed=embed)

    def _generate_animation(self, db_path: str, session_uid: int, out_dir: str) -> str:
        """Blocking call — runs in executor. Returns path to generated mp4."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            from bot.utils.db import get_session_info, get_lap_snapshots, get_sc_timeline, get_final_results, get_ftlp_timeline
            session_info  = loop.run_until_complete(get_session_info(db_path, session_uid))
            snapshots     = loop.run_until_complete(get_lap_snapshots(db_path, session_uid))
            sc_timeline   = loop.run_until_complete(get_sc_timeline(db_path, session_uid))
            final_results = loop.run_until_complete(get_final_results(db_path, session_uid))
            ftlp_timeline = loop.run_until_complete(get_ftlp_timeline(db_path, session_uid))
        finally:
            loop.close()

        track_id   = session_info["track_id"]   if session_info and "track_id"   in session_info.keys() else -1
        track_name = session_info["track_name"] if session_info and "track_name" in session_info.keys() else ""
        total_laps = session_info["total_laps"] if session_info and "total_laps" in session_info.keys() else 0

        final_positions = {r["car_index"]: r["position"] for r in final_results} if final_results else None
        grid_positions  = {r["car_index"]: r["grid_position"] for r in final_results} if final_results else None

        from visualizer.race_animation import build_mp4
        out_path = os.path.join(out_dir, "race_animation.mp4")
        build_mp4(snapshots, out_path, sc_timeline=sc_timeline,
                  total_laps=total_laps,
                  track_id=track_id, track_name=track_name,
                  final_positions=final_positions,
                  ftlp_timeline=ftlp_timeline,
                  grid_positions=grid_positions)
        return out_path

    @commands.command(name="results")
    async def results_cmd(self, ctx: commands.Context, db_path: str = None):
        """Manually show results from a DB path (admin use)."""
        if not db_path:
            await ctx.send("Usage: `!results <path_to_db>`")
            return
        if not Path(db_path).exists():
            await ctx.send(f"File not found: `{db_path}`")
            return
        session = await get_session_info(db_path)
        if not session:
            await ctx.send("No session found.")
            return
        results = await get_final_results(db_path, session["session_uid"])
        participants = await get_participants(db_path, session["session_uid"])
        embed = _build_results_embed(dict(session), results, participants)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RaceCog(bot))
