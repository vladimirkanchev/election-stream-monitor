import { useCallback, useEffect, useRef, useState } from "react";

import { localBridge } from "../bridge";
import type { MonitorSource, PlaybackStatus } from "../types";
import { getPlaybackErrorMessage } from "../uiErrors";
import {
  getResolvedPlaybackStatus,
  getStoppedPlaybackStatus,
} from "../viewModels/playbackState";

interface UsePlaybackSourceArgs {
  source: MonitorSource;
  currentItem: string | null;
  playbackRequested: boolean;
}

interface UsePlaybackSourceResult {
  mediaSource: string | null;
  playbackStatus: PlaybackStatus;
  playbackTime: number;
  playbackDuration: number | null;
  isLivePlayback: boolean;
  playbackError: string | null;
  play: (videoElement?: HTMLVideoElement | null) => Promise<void>;
  stop: (videoElement?: HTMLVideoElement | null) => void;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  handlePlaybackReady: (videoElement?: HTMLVideoElement | null) => Promise<void>;
  handlePlaybackTimeChange: (videoElement?: HTMLVideoElement | null) => void;
  handlePlaybackMetadataChange: (videoElement?: HTMLVideoElement | null) => void;
  handlePlaybackError: (message: string) => void;
}

export function usePlaybackSource({
  source,
  currentItem: _currentItem,
  playbackRequested,
}: UsePlaybackSourceArgs): UsePlaybackSourceResult {
  const { kind: sourceKind, path: sourcePath, access: sourceAccess } = source;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [mediaSource, setMediaSource] = useState<string | null>(null);
  const [playbackStatus, setPlaybackStatus] = useState<PlaybackStatus>("idle");
  const [playbackTime, setPlaybackTime] = useState(0);
  const [playbackDuration, setPlaybackDuration] = useState<number | null>(null);
  const [isLivePlayback, setIsLivePlayback] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback((videoElement?: HTMLVideoElement | null) => {
    const element = videoElement ?? videoRef.current;
    if (element) {
      element.pause();
      if (element.currentTime > 0) {
        element.currentTime = 0;
      }
    }
    setPlaybackTime(0);
    setPlaybackDuration(null);
    setIsLivePlayback(sourceAccess === "api_stream");
    setPlaybackStatus((current) => getStoppedPlaybackStatus(current));
  }, [sourceAccess]);

  const play = useCallback(
    async (videoElement?: HTMLVideoElement | null) => {
      if (!playbackRequested) {
        return;
      }

      const element = videoElement ?? videoRef.current;
      if (!element || !mediaSource) {
        return;
      }

      const playbackAttempt = element.play();
      if (playbackAttempt && typeof playbackAttempt.catch === "function") {
        await playbackAttempt.catch(() => {
          // Browsers and Electron environments can block autoplay even when the
          // source is otherwise valid. We keep playback available and let the
          // user resume manually instead of converting that into an error state.
        });
      }
      setPlaybackStatus("playing");
    },
    [mediaSource, playbackRequested],
  );

  const handlePlaybackReady = useCallback(
    async (videoElement?: HTMLVideoElement | null) => {
      handlePlaybackTimeChange(videoElement);
      await play(videoElement);
    },
    [play],
  );

  const handlePlaybackTimeChange = useCallback((videoElement?: HTMLVideoElement | null) => {
    const element = videoElement ?? videoRef.current;
    if (!element) {
      return;
    }
    setPlaybackTime(element.currentTime);
  }, []);

  const handlePlaybackMetadataChange = useCallback(
    (videoElement?: HTMLVideoElement | null) => {
      const element = videoElement ?? videoRef.current;
      if (!element) {
        return;
      }

      const duration = element.duration;
      if (Number.isFinite(duration) && duration > 0) {
        setPlaybackDuration(duration);
        setIsLivePlayback(false);
        return;
      }

      setPlaybackDuration(null);
      setIsLivePlayback(sourceAccess === "api_stream");
    },
    [sourceAccess],
  );

  const handlePlaybackError = useCallback((message: string) => {
    setError(message);
    setPlaybackStatus("error");
  }, []);

  useEffect(() => {
    let isCancelled = false;

    setPlaybackTime(0);
    setPlaybackDuration(null);
    setIsLivePlayback(sourceAccess === "api_stream");
    setError(null);
    if (sourceKind !== "video_segments") {
      setMediaSource(null);
    }
    setPlaybackStatus("loading");

    localBridge
      .resolvePlaybackSource({
        source: {
          kind: sourceKind,
          path: sourcePath,
          access: sourceAccess,
        },
        currentItem: null,
      })
      .then((resolved) => {
        if (isCancelled) {
          return;
        }

        setMediaSource(resolved);
        if (!resolved) {
          if (sourceKind !== "video_segments") {
            handlePlaybackError(getPlaybackErrorMessage("unavailable"));
          }
          return;
        }
        setPlaybackStatus(
          getResolvedPlaybackStatus({
            sourceKind,
            hasMediaSource: Boolean(resolved),
            playbackActive: playbackRequested,
          }),
        );
      })
      .catch(() => {
        if (isCancelled) {
          return;
        }
        if (sourceKind !== "video_segments") {
          handlePlaybackError(getPlaybackErrorMessage("unavailable"));
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [
    handlePlaybackError,
    playbackRequested,
    sourceAccess,
    sourceKind,
    sourcePath,
  ]);

  useEffect(() => {
    if (playbackRequested) {
      return;
    }

    stop();
  }, [playbackRequested, stop]);

  useEffect(() => {
    if (playbackStatus === "error" || playbackStatus === "loading") {
      return;
    }

    if (mediaSource) {
      return;
    }

    setPlaybackStatus("idle");
  }, [mediaSource, playbackStatus]);

  return {
    mediaSource,
    playbackStatus,
    playbackTime,
    playbackDuration,
    isLivePlayback,
    playbackError: error,
    play,
    stop,
    videoRef,
    handlePlaybackReady,
    handlePlaybackTimeChange,
    handlePlaybackMetadataChange,
    handlePlaybackError,
  };
}
