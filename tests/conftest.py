"""Test configuration for local src-based imports and media fixtures."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_MEDIA_DIR = TESTS_DIR / "fixtures" / "media"


def _run_ffmpeg(args: list[str]) -> None:
    """Run ffmpeg/ffprobe command and fail loudly on unexpected errors."""
    completed = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(args)}\n{completed.stderr}"
        )


@pytest.fixture(scope="session")
def ffmpeg_available() -> None:
    """Skip tests that require ffmpeg when the binary is unavailable."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe are required for real-media integration tests")


@pytest.fixture
def media_factory(ffmpeg_available, tmp_path: Path):
    """Build tiny real media assets for detector and session integration tests."""
    _ = ffmpeg_available

    def create_black_mp4(
        name: str = "black.mp4",
        duration_sec: float = 3.2,
        size: str = "320x180",
    ) -> Path:
        output_path = tmp_path / name
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={size}:d={duration_sec}:r=25",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )
        return output_path

    def create_pattern_mp4(
        name: str = "pattern.mp4",
        duration_sec: float = 4.0,
        blurry: bool = False,
        size: str = "320x180",
    ) -> Path:
        output_path = tmp_path / name
        video_filter = f"testsrc2=size={size}:rate=25:duration={duration_sec}"
        filter_args = []
        if blurry:
            filter_args = ["-vf", "boxblur=10:1"]
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                video_filter,
                *filter_args,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )
        return output_path

    def create_hls_black_stream(
        folder_name: str = "segments",
        duration_sec: float = 4.0,
        segment_time_sec: float = 1.0,
        size: str = "320x180",
    ) -> Path:
        output_dir = tmp_path / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        playlist_path = output_dir / "index.m3u8"
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={size}:d={duration_sec}:r=25",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-force_key_frames",
                "expr:gte(t,n_forced*1)",
                "-f",
                "hls",
                "-hls_time",
                str(segment_time_sec),
                "-hls_playlist_type",
                "vod",
                "-hls_flags",
                "independent_segments",
                "-hls_segment_filename",
                str(output_dir / "segment_%04d.ts"),
                str(playlist_path),
            ]
        )
        return output_dir

    def create_hls_pattern_stream(
        folder_name: str = "pattern_segments",
        duration_sec: float = 6.0,
        segment_time_sec: float = 1.0,
        size: str = "320x180",
        blurry: bool = False,
    ) -> Path:
        output_dir = tmp_path / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        playlist_path = output_dir / "index.m3u8"
        filter_args: list[str] = []
        if blurry:
            filter_args = ["-vf", "boxblur=10:1"]
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={size}:rate=25:duration={duration_sec}",
                *filter_args,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-force_key_frames",
                "expr:gte(t,n_forced*1)",
                "-f",
                "hls",
                "-hls_time",
                str(segment_time_sec),
                "-hls_playlist_type",
                "vod",
                "-hls_flags",
                "independent_segments",
                "-hls_segment_filename",
                str(output_dir / "segment_%04d.ts"),
                str(playlist_path),
            ]
        )
        return output_dir

    return {
        "black_mp4": create_black_mp4,
        "pattern_mp4": create_pattern_mp4,
        "hls_black_stream": create_hls_black_stream,
        "hls_pattern_stream": create_hls_pattern_stream,
    }


@pytest.fixture
def media_fixture_dir() -> Path:
    """Return the permanent checked-in media fixture directory."""
    return FIXTURE_MEDIA_DIR
