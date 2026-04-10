"""Legacy/dev-only HLS playlist metadata collector.

This module is intentionally kept outside the active local monitoring runtime.
It can still be useful for HLS exploration or future stream-ingest work, but it
should not drive current architecture decisions for the main product path.
"""

import csv
import re
import time
from pathlib import Path

import m3u8
import pandas as pd

import config
from logger import logger
from playlist_utils import (
    get_playlist_full_filename,
    merge_master_and_media,
    parse_master_playlist,
    parse_media_playlist,
)
from time_utils import parse_timestamp

PLAYLIST_COLUMNS = [
    "variant_id",
    "uri",
    "bandwidth_kbps",
    "avg_bandwidth_kbps",
    "resolution",
    "frame_rate",
    "codecs",
    "audio",
    "segment",
    "duration_sec",
    "program_time_utc",
    "inter_arrival_sec",
    "sequence",
    "sequence_gap",
    "target_duration",
    "playlist_version",
    "is_endlist",
    "parsed_at",
    "match_status",
    "source_master_file",
    "source_media_file",
]

DEFAULT_PLAYLIST_PREFIXES: tuple[str, ...] = ()


def extract_index(filename: str) -> int:
    """Extract trailing number (index) from playlist filename."""
    match = re.search(r"(\d+)(?:\.m3u8)?$", filename)
    return int(match.group(1)) if match else -1


def get_base_path() -> str:
    """Get the base path for local playlist files."""
    return str(config.VIDEO_INPUT_FOLDER)


def safe_m3u8_load(path_or_url: str | Path):
    """Load an m3u8 playlist from a file/URL, handle local files properly."""
    path_str = str(path_or_url)
    if Path(path_str).is_file():
        return m3u8.load(open(path_str, "r", encoding="utf-8"))
    return m3u8.load(path_str)


# pylint: disable=too-many-locals
# pylint: disable=too-many-statements
def collect_and_export_playlists(curr_prefix: str) -> None:
    """
    Scan a directory for master+media .m3u8 files, merge metadata.

    Also scan a directory for sanity-check, and export unified CSV.
    """
    base_dir = Path(__file__).parent.parent.resolve() / get_base_path() / curr_prefix
    playlist_files = sorted(base_dir.glob("*.m3u8"))

    if not playlist_files:
        logger.warning("No playlist files found in %s", base_dir)
        return None

    master_rows, media_rows = [], []

    for pl_file in playlist_files:
        try:
            text = pl_file.read_text(encoding="utf-8")

            if "#EXT-X-STREAM-INF" in text:
                # Master playlist
                master_data = parse_master_playlist(str(pl_file))
                for m in master_data:
                    m["source_master_file"] = pl_file.name
                master_rows.extend(master_data)

            elif "#EXTINF" in text:
                # Media playlist
                segs = parse_media_playlist(str(pl_file))
                curr_datetime = time.time()
                for seg in segs:
                    seg["source_media_file"] = pl_file.name
                    seg["parsed_at"] = parse_timestamp(curr_datetime)
                    media_rows.append(seg)
            else:
                logger.warning("Unknown playlist type: %s", pl_file)

        except OSError as err:
            logger.error("Failed to process %s: %s", pl_file, err, exc_info=True)
    # --- Merge + sanity check ---
    merged_rows = merge_master_and_media(master_rows, media_rows)
    if not merged_rows:
        logger.warning("No combined metadata extracted from %s", base_dir)
        return None

    # --- Normalize output to consistent schema ---
    df = pd.DataFrame(merged_rows)
    for col in PLAYLIST_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[PLAYLIST_COLUMNS]

    logger.log(merged_rows)

    return None


def save_playlist_metadata_csv(folder_name: str, all_rows: list[dict]) -> None:
    """Save collected playlist metadata to a CSV file."""
    # Save to CSV
    base_dir = Path(__file__).parent.parent.resolve() / get_base_path() / folder_name
    output_csv = base_dir / get_playlist_full_filename()

    # print("output_cvs", output_csv)
    file_exists = output_csv.exists()
    try:
        with open(output_csv, "a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=PLAYLIST_COLUMNS)
            if not file_exists:
                writer.writeheader()
            for row in all_rows:
                filtered_row = {key: row.get(key, None) for key in PLAYLIST_COLUMNS}
                # print(filtered_row)
                writer.writerow(filtered_row)
        logger.info("Saved %d playlist entries to %s", len(all_rows), output_csv)

    except OSError as err:
        logger.error("Failed to save playlist metadata CSV: %s", err)


# Example usage:
if __name__ == "__main__":
    for prefix in DEFAULT_PLAYLIST_PREFIXES:
        PREFIX_STR = "imgarena_stream" + "/" + prefix
        collect_and_export_playlists(curr_prefix=PREFIX_STR)
    # save_playlist_metadata_csv("imgarena_stream", rows)
