import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Volume2, Play, Pause, SkipBack, SkipForward, Power, Mic2 } from "lucide-react";
import { api, Device, NowPlaying, Volume } from "../lib/api";
import { useWebSocket } from "../hooks/useWebSocket";

interface DeviceState {
  device: Device;
  nowPlaying: NowPlaying | null;
  volume: Volume | null;
  loading: boolean;
  error: string | null;
}

function VolumeSlider({ deviceId, volume, onChanged }: {
  deviceId: string;
  volume: Volume | null;
  onChanged: () => void;
}) {
  const [val, setVal] = useState(volume?.actual ?? 30);
  useEffect(() => { if (volume) setVal(volume.actual); }, [volume]);

  const commit = async (v: number) => {
    await api.devices.setVolume(deviceId, v).catch(() => {});
    onChanged();
  };

  return (
    <div className="volume-row">
      <Volume2 size={14} />
      <input
        type="range" min={0} max={100} value={val}
        onChange={(e) => setVal(+e.target.value)}
        onMouseUp={(e) => commit(+(e.target as HTMLInputElement).value)}
        onTouchEnd={(e) => commit(+(e.target as HTMLInputElement).value)}
        className="volume-slider"
      />
      <span className="volume-label">{val}</span>
    </div>
  );
}

function isPlaying(np: NowPlaying | null) {
  return np?.play_status === "PLAY_STATE";
}

function DeviceCard({ state, onRefresh }: { state: DeviceState; onRefresh: () => void }) {
  const { device, nowPlaying, volume } = state;

  const key = async (action: string) => {
    await api.devices.key(device.id, action).catch(() => {});
    setTimeout(onRefresh, 400);
  };

  const playing = isPlaying(nowPlaying);
  const standby = nowPlaying?.source === "STANDBY";

  return (
    <div className={`device-card ${standby ? "standby" : ""}`}>
      <div className="device-header">
        <div className="device-meta">
          <span className="device-name">{device.name}</span>
          <span className="device-model">{device.model}</span>
        </div>
        <button
          className={`power-btn ${standby ? "" : "on"}`}
          onClick={() => key(standby ? "power_on" : "power_off")}
          title={standby ? "Einschalten" : "Ausschalten"}
        >
          <Power size={16} />
        </button>
      </div>

      {!standby && nowPlaying && (
        <>
          <div className="now-playing">
            {nowPlaying.art && (
              <img className="cover-art" src={nowPlaying.art} alt="Cover" onError={(e) => (e.currentTarget.style.display = "none")} />
            )}
            {!nowPlaying.art && (
              <div className="cover-placeholder"><Mic2 size={28} /></div>
            )}
            <div className="track-info">
              <div className="track-name">{nowPlaying.track || "—"}</div>
              {nowPlaying.artist && <div className="track-artist">{nowPlaying.artist}</div>}
              <div className="track-source">{nowPlaying.source}</div>
            </div>
          </div>

          <div className="controls">
            <button onClick={() => key("prev")} title="Zurück"><SkipBack size={18} /></button>
            <button className="play-btn" onClick={() => key("play_pause")} title={playing ? "Pause" : "Play"}>
              {playing ? <Pause size={20} /> : <Play size={20} />}
            </button>
            <button onClick={() => key("next")} title="Weiter"><SkipForward size={18} /></button>
          </div>

          <VolumeSlider deviceId={device.id} volume={volume} onChanged={onRefresh} />
        </>
      )}

      {standby && <div className="standby-label">Standby</div>}

      {state.error && <div className="error-msg">⚠ {state.error}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [states, setStates] = useState<DeviceState[]>([]);
  const [scanning, setScanning] = useState(false);

  const loadAll = useCallback(async () => {
    const devices = await api.devices.list().catch(() => [] as Device[]);
    const initial: DeviceState[] = devices.map((d) => ({
      device: d, nowPlaying: null, volume: null, loading: true, error: null,
    }));
    setStates(initial);

    await Promise.all(
      devices.map(async (d, i) => {
        try {
          const [np, vol] = await Promise.all([
            api.devices.nowPlaying(d.id),
            api.devices.volume(d.id),
          ]);
          setStates((prev) => prev.map((s, si) =>
            si === i ? { ...s, nowPlaying: np, volume: vol, loading: false } : s
          ));
        } catch (e: unknown) {
          setStates((prev) => prev.map((s, si) =>
            si === i ? { ...s, loading: false, error: e instanceof Error ? e.message : "Fehler" } : s
          ));
        }
      })
    );
  }, []);

  useEffect(() => {
    loadAll();
    // Fallback poll every 10 s (WebSocket handles real-time updates)
    const id = setInterval(loadAll, 10000);
    return () => clearInterval(id);
  }, [loadAll]);

  // Real-time updates via WebSocket
  useWebSocket((msg) => {
    if (msg.type === "state") {
      setStates((prev) =>
        prev.map((s) =>
          s.device.id === msg.device_id
            ? {
                ...s,
                nowPlaying: msg.now_playing as NowPlaying,
                volume: msg.volume as Volume,
                loading: false,
                error: null,
              }
            : s
        )
      );
    } else if (msg.type === "offline") {
      setStates((prev) =>
        prev.map((s) =>
          s.device.id === msg.device_id
            ? { ...s, error: "Gerät nicht erreichbar" }
            : s
        )
      );
    }
  });

  const scan = async () => {
    setScanning(true);
    await api.devices.scan().catch(() => {});
    await loadAll();
    setScanning(false);
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <button className="btn-secondary" onClick={scan} disabled={scanning}>
          <RefreshCw size={14} className={scanning ? "spin" : ""} />
          {scanning ? "Suche..." : "Geräte suchen"}
        </button>
      </div>

      {states.length === 0 && (
        <div className="empty-state">
          <p>Keine Lautsprecher gefunden.</p>
          <p>Stelle sicher, dass deine Bose SoundTouch Geräte im selben Netzwerk sind, und klicke auf „Geräte suchen".</p>
        </div>
      )}

      <div className="device-grid">
        {states.map((s) => (
          <DeviceCard key={s.device.id} state={s} onRefresh={loadAll} />
        ))}
      </div>
    </div>
  );
}
