import Hls from "hls.js";
import { useEffect, useEffectEvent } from "react";

import { usePlaybackSource } from "../hooks/usePlaybackSource";
import { buildVideoPanelDisplayModel } from "../presenters/videoPanel";
import type { MonitorSource, PlaybackStatus } from "../types";
import { getHlsPlaybackErrorMessage, getPlaybackErrorMessage } from "../uiErrors";

interface VideoPlayerPanelProps {
  /** The resolved monitoring source currently shown in the playback panel. */
  source: MonitorSource;
  /** The active item from session progress, used for segment alignment. */
  currentItem: string | null;
  /** Whether the parent session flow currently wants playback to be active. */
  playbackRequested: boolean;
  onPlaybackStatusChange?: (status: PlaybackStatus) => void;
  onPlaybackMetricsChange?: (metrics: {
    time: number;
    duration: number | null;
    isLive: boolean;
  }) => void;
  onPlaybackItemChange?: (item: string | null) => void;
  onPlaybackSegmentMapChange?: (segmentStarts: Record<string, number>) => void;
}

export function VideoPlayerPanel({
  source,
  currentItem,
  playbackRequested,
  onPlaybackStatusChange,
  onPlaybackMetricsChange,
  onPlaybackItemChange,
  onPlaybackSegmentMapChange,
}: VideoPlayerPanelProps) {
  // Playback state resolution lives in the hook so this component can focus on
  // media attachment, renderer-only HLS behavior, and presentation.
  const {
    mediaSource,
    playbackStatus,
    playbackTime,
    playbackDuration,
    isLivePlayback,
    playbackError,
    play,
    stop,
    videoRef,
    handlePlaybackReady,
    handlePlaybackTimeChange,
    handlePlaybackMetadataChange,
    handlePlaybackError,
  } = usePlaybackSource({
    source,
    currentItem,
    playbackRequested,
  });

  const emitPlaybackStatusChange = useEffectEvent((status: PlaybackStatus) => {
    onPlaybackStatusChange?.(status);
  });

  const emitPlaybackMetricsChange = useEffectEvent((metrics: {
    time: number;
    duration: number | null;
    isLive: boolean;
  }) => {
    onPlaybackMetricsChange?.(metrics);
  });

  const emitPlaybackItemChange = useEffectEvent((item: string | null) => {
    onPlaybackItemChange?.(item);
  });

  const emitPlaybackSegmentMapChange = useEffectEvent((segmentStarts: Record<string, number>) => {
    onPlaybackSegmentMapChange?.(segmentStarts);
  });

  useEffect(() => {
    emitPlaybackStatusChange(playbackStatus);
  }, [playbackStatus]);

  useEffect(() => {
    emitPlaybackMetricsChange({
      time: playbackTime,
      duration: playbackDuration,
      isLive: isLivePlayback,
    });
  }, [isLivePlayback, playbackDuration, playbackTime]);

  useEffect(() => {
    // Segment-specific playback metadata is only meaningful for local HLS
    // playback. Other source kinds reset that alignment state.
    if (source.kind !== "video_segments") {
      emitPlaybackItemChange(null);
      emitPlaybackSegmentMapChange({});
    }
  }, [source.kind]);

  useEffect(() => {
    const videoElement = videoRef.current;
    if (!videoElement || !mediaSource) {
      return undefined;
    }

    // HLS segment playback needs extra wiring so we can keep playback aligned
    // with segment names and start times. Direct file playback can stay simple.
    if (mediaSource.endsWith(".m3u8")) {
      if (Hls.isSupported()) {
        return attachHlsPlayback({
          videoElement,
          mediaSource,
          play,
          onPlaybackItemChange: emitPlaybackItemChange,
          onPlaybackSegmentMapChange: emitPlaybackSegmentMapChange,
          handlePlaybackError,
        });
      }

      if (videoElement.canPlayType("application/vnd.apple.mpegurl")) {
        console.info("[playback] using native HLS playback", mediaSource);
        videoElement.src = mediaSource;
        videoElement.load();
        void play(videoElement);
        return undefined;
      }

      handlePlaybackError(getPlaybackErrorMessage("hlsUnsupported"));
      return undefined;
    }

    loadDirectVideoSource(videoElement, mediaSource, play);
    return undefined;
  }, [
    handlePlaybackError,
    mediaSource,
    play,
    videoRef,
  ]);

  useEffect(() => {
    if (!playbackRequested) {
      stop();
      return;
    }

    void play();
  }, [playbackRequested, play, stop]);

  const panel = buildVideoPanelDisplayModel({
    source,
    currentItem,
    mediaSource,
    playbackStatus,
    playbackTime,
    error: playbackError,
  });

  return (
    <section className="monitor-card video-panel">
      <div className="monitor-card__header">
        <h2>Live View</h2>
        <span>{panel.modeLabel}</span>
      </div>
      <div className="video-panel__meta video-panel__meta--summary">
        <span className={`video-panel__chip video-panel__chip--${panel.statusTone}`}>
          {panel.statusLabel}
        </span>
        <span className="video-panel__chip">{panel.routeLabel}</span>
      </div>
      <div className="video-panel__surface">
        {panel.showPreparingState ? (
          <div className="video-panel__placeholder">
            <strong>Preparing playback</strong>
            <p>{panel.loadingMessage}</p>
          </div>
        ) : mediaSource ? (
          <video
            key={mediaSource}
            ref={videoRef}
            className="video-panel__media"
            controls
            muted
            autoPlay
            playsInline
            preload="auto"
            onError={() =>
              handlePlaybackError(getDirectPlaybackOpenErrorMessage(source, mediaSource))
            }
            onCanPlay={(event) => {
              console.info("[playback] canplay", mediaSource);
              void handlePlaybackReady(event.currentTarget);
            }}
            onLoadedMetadata={(event) => {
              handlePlaybackMetadataChange(event.currentTarget);
              handlePlaybackTimeChange(event.currentTarget);
            }}
            onDurationChange={(event) => handlePlaybackMetadataChange(event.currentTarget)}
            onTimeUpdate={(event) => handlePlaybackTimeChange(event.currentTarget)}
          />
        ) : panel.showPlaybackUnavailable ? (
          <div className="video-panel__placeholder">
            <strong>Playback unavailable</strong>
            <p>{panel.errorMessage}</p>
          </div>
        ) : null}
      </div>
      <div className="video-panel__meta">
        <span className="video-panel__meta-item" title={panel.loadedFromTitle}>
          <strong>Loaded from</strong>
          <span className="video-panel__meta-value">{panel.loadedFromLabel}</span>
        </span>
        <span className="video-panel__meta-item">
          <strong>Playback time</strong>
          <span className="video-panel__meta-value">{panel.playbackTimeLabel}</span>
        </span>
      </div>
      {panel.hintMessage ? (
        <p className="video-panel__hint">{panel.hintMessage}</p>
      ) : panel.errorMessage ? (
        <p className="video-panel__error">{panel.errorMessage}</p>
      ) : null}
    </section>
  );
}

function attachHlsPlayback(args: {
  videoElement: HTMLVideoElement;
  mediaSource: string;
  play: (element?: HTMLVideoElement) => Promise<void>;
  onPlaybackItemChange?: (item: string | null) => void;
  onPlaybackSegmentMapChange?: (segmentStarts: Record<string, number>) => void;
  handlePlaybackError: (message: string) => void;
}): () => void {
  // Hls.js is only attached when the resolved playback source is an HLS
  // playlist. Direct files stay on the browser's native media stack.
  const {
    videoElement,
    mediaSource,
    play,
    onPlaybackItemChange,
    onPlaybackSegmentMapChange,
    handlePlaybackError,
  } = args;

  console.info("[playback] attaching Hls.js", mediaSource);
  const hls = new Hls({
    enableWorker: false,
  });
  hls.loadSource(mediaSource);
  hls.attachMedia(videoElement);
  hls.on(Hls.Events.MANIFEST_PARSED, () => {
    console.info("[playback] HLS manifest parsed", mediaSource);
    void play(videoElement);
  });
  hls.on(Hls.Events.LEVEL_LOADED, (_event, data) => {
    console.info(
      "[playback] HLS level loaded",
      mediaSource,
      data.details?.totalduration,
      data.details?.fragments?.length,
    );
    onPlaybackSegmentMapChange?.(buildSegmentStartMap(data.details?.fragments ?? []));
  });
  hls.on(Hls.Events.FRAG_CHANGED, (_event, data) => {
    onPlaybackItemChange?.(getFragmentName(data.frag));
  });
  hls.on(Hls.Events.ERROR, (_event, data) => {
    console.error(
      "[playback] HLS error",
      JSON.stringify({
        type: data.type,
        details: data.details,
        fatal: data.fatal,
        responseCode: data.response?.code ?? null,
        responseText: data.response?.text ?? null,
      }),
    );
    if (data.fatal) {
      handlePlaybackError(
        getHlsPlaybackErrorMessage({
          details: data.details,
          responseCode: data.response?.code ?? null,
          responseText: data.response?.text ?? null,
        }),
      );
    }
  });
  return () => {
    hls.destroy();
  };
}

function loadDirectVideoSource(
  videoElement: HTMLVideoElement,
  mediaSource: string,
  play: (element?: HTMLVideoElement) => Promise<void>,
): void {
  // Direct local and remote media files share the same happy path: set src,
  // load, and let the normal <video> element lifecycle drive readiness.
  console.info("[playback] loading direct media source", mediaSource);
  videoElement.src = mediaSource;
  videoElement.load();
  void play(videoElement);
}

function getDirectPlaybackOpenErrorMessage(
  source: MonitorSource,
  mediaSource: string,
): string {
  // api_stream direct files are still remote-facing even though they skip HLS,
  // so the user-facing error should not incorrectly call them "local" videos.
  if (source.access === "api_stream" || /^https?:\/\//i.test(mediaSource)) {
    return getPlaybackErrorMessage("remoteVideoOpen");
  }
  return getPlaybackErrorMessage("localVideoOpen");
}

function buildSegmentStartMap(
  fragments: Array<{ relurl?: string; url?: string; start: number }>,
): Record<string, number> {
  return Object.fromEntries(
    fragments
      .map((fragment) => {
        const fragmentName = getFragmentName(fragment);
        if (!fragmentName) {
          return null;
        }
        return [fragmentName, fragment.start] as const;
      })
      .filter((entry): entry is readonly [string, number] => entry !== null),
  );
}

function getFragmentName(fragment?: { relurl?: string; url?: string } | null): string | null {
  return fragment?.relurl ?? fragment?.url?.split("/").pop() ?? null;
}
