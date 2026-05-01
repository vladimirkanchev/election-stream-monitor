"""Developer utility to generate `.ts` segments from a local video file."""

import argparse
import subprocess  # nosec B404
from pathlib import Path

import config
from logger import get_logger

logger = get_logger(__name__)

DEFAULT_SEGMENT_PREFIX = "segments"


def split_video_to_ts(
    input_file: Path,
    output_dir: Path,
    segment_time: int = 1,
) -> None:
    """Split one local video file into HLS `.ts` segments and a playlist.

    The generated output is intended for local playback and monitoring tests,
    so the playlist is written as a finished VOD-style media playlist with
    independent segments and a stable segment numbering scheme.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    playlist_path = output_dir / "index.m3u8"
    segment_pattern = output_dir / "segment_%04d.ts"
    force_key_frames_expr = f"expr:gte(t,n_forced*{segment_time})"

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_file),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-flags",
        "+cgop",
        "-sc_threshold",
        "0",
        "-force_key_frames",
        force_key_frames_expr,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "hls",
        "-hls_playlist_type",
        "vod",
        "-hls_time",
        str(segment_time),
        "-hls_list_size",
        "0",
        "-start_number",
        "0",
        "-hls_flags",
        "independent_segments",
        "-hls_segment_filename",
        str(segment_pattern),
        str(playlist_path),
    ]

    logger.info("Generating HLS segments from %s into %s", input_file, output_dir)
    subprocess.run(cmd, check=True, shell=False)  # nosec B603
    logger.info("Created playlist %s", playlist_path)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser for the utility."""
    parser = argparse.ArgumentParser(
        description="Generate local HLS .ts segments from a video file."
    )
    parser.add_argument("input_file", type=Path, help="Path to the source video file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=config.VIDEO_INPUT_FOLDER / DEFAULT_SEGMENT_PREFIX,
        help="Directory where generated .ts segments"
        + " and index.m3u8 will be written.",
    )
    parser.add_argument(
        "--segment-time",
        type=int,
        default=1,
        help="Target segment duration in seconds.",
    )
    return parser


def main() -> None:
    """Run the segment-generation utility from the command line."""
    parser = build_parser()
    args = parser.parse_args()

    split_video_to_ts(
        input_file=args.input_file,
        output_dir=args.output_dir,
        segment_time=args.segment_time,
    )


if __name__ == "__main__":
    main()
