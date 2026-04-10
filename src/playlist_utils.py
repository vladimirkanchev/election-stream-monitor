"""Legacy/dev-only helpers for HLS master and media playlists.

These utilities are not part of the active local monitoring flow. They remain
in the repository for optional HLS exploration and possible future API-stream
work.
"""

from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import m3u8
from logger import logger
from time_utils import parse_timestamp

logger = logger.getChild("playlist_utils")


def safe_m3u8_load(path_or_url: str | Path):
    """Load an m3u8 playlist from a file/URL, handle local files properly."""
    path_str = str(path_or_url)
    if Path(path_str).is_file():
        return m3u8.load(open(path_str, "r", encoding="utf-8"))
    return m3u8.load(path_str)


def parse_media_playlist(path_or_url: str | Path) -> list[dict]:
    """Parse a HLS media playlist (.m3u8) and extract per-segment metadata."""
    try:
        path_obj = Path(path_or_url)
        if path_obj.exists():
            # Local file — read its content and set base_uri for relative URLs
            text = path_obj.read_text(encoding="utf-8")
            base_uri = path_obj.parent.as_uri()
            playlist = m3u8.loads(text, uri=base_uri)
        else:
            # Remote URL (HTTP/HTTPS)
            playlist = m3u8.load(str(path_or_url))
    except (OSError, ValueError) as err:
        logger.error("Failed to parse media playlist: %s", err)
        return []

    segments_info = []
    prev_time = None
    prev_seq = None

    for i, seg in enumerate(playlist.segments):
        seg_info = {
            "index": i,
            "segment": Path(seg.uri).name,
            "uri": seg.absolute_uri or seg.uri,
            "duration_sec": round(seg.duration, 3),
            "program_time_utc": parse_timestamp(
                seg.program_date_time if seg.program_date_time else None
            ),
            "sequence": getattr(seg, "media_sequence", None),
        }

        # Compute inter-arrival time
        if prev_time and seg.program_date_time:
            delta = (seg.program_date_time - prev_time).total_seconds()
            seg_info["inter_arrival_sec"] = round(delta, 3)
        else:
            seg_info["inter_arrival_sec"] = None
        prev_time = seg.program_date_time

        # Detect sequence gaps
        if prev_seq is not None and seg_info["sequence"] is not None:
            seg_info["sequence_gap"] = seg_info["sequence"] - prev_seq - 1
        else:
            seg_info["sequence_gap"] = 0
        prev_seq = seg_info["sequence"]

        # Add overall playlist parameters
        seg_info["target_duration"] = getattr(playlist, "target_duration", None)
        seg_info["playlist_version"] = getattr(playlist, "version", None)
        seg_info["is_endlist"] = getattr(playlist, "is_endlist", False)
        segments_info.append(seg_info)

    logger.info(
        "Parsed %d segments from media playlist: %s", len(segments_info), path_or_url
    )
    return segments_info


def parse_master_playlist(
    path_or_url: str | Path, base_uri: str | None = None
) -> list[dict]:
    """Parse an HLS master playlist to extract available variants."""
    try:
        path_obj = Path(path_or_url)
        if path_obj.exists():
            # Local file — read its content and set base_uri for relative URLs
            text = path_obj.read_text(encoding="utf-8")
            base_uri = path_obj.parent.as_uri()
            playlist = m3u8.loads(text, uri=base_uri)
        else:
            # Remote URL (HTTP/HTTPS)
            playlist = m3u8.load(str(path_or_url))
    except (OSError, ValueError) as err:
        logger.error("Failed to parse media playlist: %s", err)
        return _parse_master_playlist_fallback(
            text if "text" in locals() else "", base_uri
        )

    variants = []
    for pl in getattr(playlist, "playlists", []):
        info = {
            "uri": urljoin(base_uri + "/", pl.uri),
            "bandwidth_kbps": int(getattr(pl.stream_info, "bandwidth", 0)) / 1000,
            "avg_bandwidth_kbps": int(getattr(pl.stream_info, "average_bandwidth", 0))
            / 1000,
            "resolution": getattr(pl.stream_info, "resolution", None),
            "frame_rate": getattr(pl.stream_info, "frame_rate", None),
            "codecs": getattr(pl.stream_info, "codecs", None),
            "audio": getattr(pl.stream_info, "audio", None),
        }
        variants.append(info)

    logger.info(
        "Parsed %d variants from master playlist: %s", len(variants), path_or_url
    )
    return variants


def _parse_master_playlist_fallback(text: str, base_url: str = "") -> list[dict]:
    """Fallback for tokenized or malformed master playlists."""
    variants = []
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = {
                kv.split("=")[0].strip(): kv.split("=")[1].strip()
                for kv in line.split(":")[1].split(",")
                if "=" in kv
            }
            uri = lines[i + 1].strip() if i + 1 < len(lines) else None
            if uri and not uri.startswith("http"):
                uri = urljoin(base_url + "/", uri)
            variants.append(
                {
                    "uri": uri,
                    "bandwidth_kbps": int(attrs.get("BANDWIDTH", "0")) / 1000,
                    "avg_bandwidth_kbps": int(attrs.get("AVERAGE-BANDWIDTH", "0"))
                    / 1000,
                    "resolution": attrs.get("RESOLUTION"),
                    "frame_rate": float(attrs.get("FRAME-RATE", "0")),
                    "codecs": attrs.get("CODECS"),
                }
            )
    logger.info("Fallback parser extracted %d variants", len(variants))
    return variants


def merge_master_and_media(
    master_list: list[dict], media_list: list[dict]
) -> list[dict]:
    """Attach master variant info to each media segment by filename prefix."""
    merged = []
    unmatched_media = []

    if not master_list or not media_list:
        logger.warning("Master or media playlist list is empty.")
        return merged

    for media in media_list:
        media_uri = media.get("uri", "")
        # Try to match variant by URI prefix (playlist_360p25)
        matching_master = next(
            (m for m in master_list if Path(m["uri"]).stem in media_uri), None
        )

        # Fallback: match by resolution if prefix fails
        if not matching_master and "resolution" in media:
            matching_master = next(
                (
                    m
                    for m in master_list
                    if m.get("resolution") == media.get("resolution")
                ),
                None,
            )

        # Build merged row
        if matching_master:
            row = {**matching_master, **media}
            row["variant_id"] = Path(matching_master["uri"]).stem
            row["match_status"] = "matched"
        else:
            row = {**media, "variant_id": "unknown", "match_status": "unmatched"}
            unmatched_media.append(media_uri)

        merged.append(row)

    # --- Post-merge sanity check ---
    total_segments = len(media_list)
    matched = len([r for r in merged if r["match_status"] == "matched"])
    unmatched = len(unmatched_media)

    logger.info(
        "Sanity Check: total=%d, matched=%d (%.1f%%), unmatched=%d",
        total_segments,
        matched,
        (matched / total_segments * 100) if total_segments else 0,
        unmatched,
    )

    if unmatched > 0:
        logger.warning(
            "Unmatched media segments (no corresponding variant): %s",
            ", ".join(unmatched_media[:5]) + ("..." if unmatched > 5 else ""),
        )

    logger.info("Merged %d total entries (master+media).", len(merged))
    return merged


def get_playlist_full_filename() -> Path:
    """Save all detector alerts to CSV when application exits."""
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    interm_path = Path(__file__).parent.parent.resolve()
    interm_path = interm_path / "data" / "metrics"
    interm_path.mkdir(parents=True, exist_ok=True)
    filename = f"playlist_{timestamp}_metrics.csv"
    filepath = interm_path / filename

    return filepath
