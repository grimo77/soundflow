import { useState, useEffect, useCallback } from "react";
import { api, NowPlaying, Volume } from "../lib/api";

export function useDeviceState(deviceId: string | null, intervalMs = 3000) {
  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [volume, setVolume] = useState<Volume | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!deviceId) return;
    try {
      const [np, vol] = await Promise.all([
        api.devices.nowPlaying(deviceId),
        api.devices.volume(deviceId),
      ]);
      setNowPlaying(np);
      setVolume(vol);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection error");
    }
  }, [deviceId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { nowPlaying, volume, error, refresh };
}
