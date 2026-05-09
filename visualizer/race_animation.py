"""
Generates the animated GIF from lap snapshot data.

Visual design:
- Horizontal track, cars travel left → right
- X axis: non-linear — leader moves steadily right, others pulled left
  by log-scaled gap to leader (small gaps amplified, huge gaps compressed)
- Y axis: race position rows, P1 always on top, rows swap on overtake
- Each car leaves a trailing history line (diagonal, not vertical)
- Pit stop icon shown when pit_status > 0
- +1 LAP overlay at reduced opacity for lapped cars
- Cars represented by coloured rectangles (SVG icons TBD)
"""
import math
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation, PillowWriter


# Team colour palette (team_id → hex)
TEAM_COLOURS: Dict[int, str] = {
    0:  "#00D2BE",  # Mercedes
    1:  "#FF8000",  # McLaren
    2:  "#DC0000",  # Ferrari
    3:  "#3671C6",  # Red Bull
    4:  "#006F62",  # Aston Martin
    5:  "#0093CC",  # Alpine
    6:  "#005AFF",  # Williams
    7:  "#52E252",  # Kick Sauber
    8:  "#B6BABD",  # Haas
    9:  "#3E0097",  # RB
    41: "#FFFFFF",  # My Team
}
DEFAULT_COLOUR = "#AAAAAA"

# Animation constants
TRACK_X_MIN = 0.05
TRACK_X_MAX = 0.95
CAR_WIDTH = 0.06
CAR_HEIGHT = 0.018
TRAIL_LENGTH = 12       # frames of history to draw
FPS = 10
FRAME_STEP = 3          # use every Nth snapshot to keep GIF small

# Gap → X position: leader is at TRACK_X_MAX, others pulled left
# gap in seconds; 0 = side-by-side
GAP_SCALE = 30.0        # seconds gap that maps to full track width
LOG_BASE = math.e


def _gap_to_x(gap_seconds: float) -> float:
    """Map a time gap to an X position [TRACK_X_MIN, TRACK_X_MAX]."""
    if gap_seconds <= 0:
        return TRACK_X_MAX
    # log scale: 1s gap ≈ small pull, 60s+ gap ≈ pushed to left edge
    log_gap = math.log1p(gap_seconds) / math.log1p(GAP_SCALE)
    x = TRACK_X_MAX - (TRACK_X_MAX - TRACK_X_MIN) * min(log_gap, 1.0)
    return x


def _car_colour(team_id: int) -> str:
    return TEAM_COLOURS.get(team_id, DEFAULT_COLOUR)


def _build_frame_data(snapshots: List[Any]) -> List[Dict[str, Any]]:
    """
    Group snapshots by session_time frame, compute positions and gaps.
    Returns list of frames; each frame is a dict of car_index → car state.
    """
    from collections import defaultdict
    by_time: Dict[float, Dict[int, Any]] = defaultdict(dict)
    for row in snapshots:
        t = row["session_time"]
        ci = row["car_index"]
        by_time[t][ci] = row

    frames = []
    for t in sorted(by_time.keys()):
        cars = by_time[t]
        # Find leader by highest total_distance
        if not cars:
            continue
        leader = max(cars.values(), key=lambda r: r["total_distance"])
        leader_dist = leader["total_distance"]

        frame: Dict[int, Dict] = {}
        for ci, row in cars.items():
            gap = max(0.0, leader_dist - row["total_distance"]) / max(leader_dist, 1) * GAP_SCALE
            frame[ci] = {
                "name": row["name"],
                "team_id": row["team_id"],
                "position": row["car_position"],
                "lap": row["current_lap"],
                "pit": row["pit_status"] > 0,
                "lapped": row["current_lap"] < leader["current_lap"] - 1,
                "gap": gap,
                "x": _gap_to_x(gap),
            }
        frames.append({"time": t, "cars": frame})

    return frames


def build_gif(snapshots: List[Any], out_path: str) -> None:
    if not snapshots:
        raise ValueError("No snapshots to animate")

    frames = _build_frame_data(snapshots)
    frames = frames[::FRAME_STEP]  # thin out for file size

    if not frames:
        raise ValueError("No frames after thinning")

    num_cars = max(len(f["cars"]) for f in frames)
    fig_height = max(4.0, num_cars * 0.55 + 1.0)
    fig, ax = plt.subplots(figsize=(14, fig_height), facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, num_cars - 0.5)
    ax.axis("off")

    # position row index: key = car_index, value = y row (0 = top = P1)
    # recomputed each frame based on current race position
    trails: Dict[int, List[Tuple[float, float]]] = {}  # car_index → [(x, y), ...]

    patches: Dict[int, mpatches.FancyBboxPatch] = {}
    name_texts: Dict[int, plt.Text] = {}
    trail_lines: Dict[int, plt.Line2D] = {}

    title_text = ax.text(
        0.5, num_cars - 0.1, "", ha="center", va="bottom",
        color="white", fontsize=11, fontweight="bold",
        transform=ax.transData,
    )

    def _y_for_position(pos: int) -> float:
        # P1 at top row (num_cars - 1), P20 at row 0
        return num_cars - pos

    def init():
        return []

    def animate(frame_idx: int):
        frame = frames[frame_idx]
        cars = frame["cars"]

        # Clear previous patches / texts
        for patch in patches.values():
            patch.remove()
        for txt in name_texts.values():
            txt.remove()
        for line in trail_lines.values():
            line.remove()
        patches.clear()
        name_texts.clear()
        trail_lines.clear()

        for ci, state in cars.items():
            pos = state["position"]
            x = state["x"]
            y = _y_for_position(pos)
            colour = _car_colour(state["team_id"])
            alpha = 0.35 if state["lapped"] else 1.0

            # Trail
            if ci not in trails:
                trails[ci] = []
            trails[ci].append((x, y))
            if len(trails[ci]) > TRAIL_LENGTH:
                trails[ci] = trails[ci][-TRAIL_LENGTH:]

            if len(trails[ci]) >= 2:
                xs = [p[0] for p in trails[ci]]
                ys = [p[1] for p in trails[ci]]
                (line,) = ax.plot(xs, ys, color=colour, alpha=0.3 * alpha,
                                  linewidth=1.5, solid_capstyle="round")
                trail_lines[ci] = line

            # Car rectangle
            rect = mpatches.FancyBboxPatch(
                (x - CAR_WIDTH / 2, y - CAR_HEIGHT / 2),
                CAR_WIDTH, CAR_HEIGHT,
                boxstyle="round,pad=0.002",
                linewidth=0,
                facecolor=colour,
                alpha=alpha,
                zorder=3,
            )
            ax.add_patch(rect)
            patches[ci] = rect

            # Name label
            label = state["name"]
            if state["pit"]:
                label += " 🔧"
            elif state["lapped"]:
                label += " +1L"
            txt = ax.text(
                x - CAR_WIDTH / 2 - 0.01, y, label,
                ha="right", va="center", color="white",
                fontsize=6.5, alpha=alpha, zorder=4,
            )
            name_texts[ci] = txt

        t = frame["time"]
        minutes, secs = divmod(int(t), 60)
        title_text.set_text(f"Race — {minutes}:{secs:02d}")

        return list(patches.values()) + list(name_texts.values()) + list(trail_lines.values())

    anim = FuncAnimation(
        fig, animate, init_func=init,
        frames=len(frames), interval=1000 // FPS,
        blit=False,
    )

    writer = PillowWriter(fps=FPS)
    anim.save(out_path, writer=writer, dpi=120)
    plt.close(fig)
    print(f"[visualizer] GIF saved: {out_path}")
