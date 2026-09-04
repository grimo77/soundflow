import { useEffect, useState, useRef } from "react";
import { Music2, Search, Play, LogOut, CheckCircle } from "lucide-react";
import { api, Device } from "../lib/api";

interface SpotifyStatus {
  connected: boolean;
  display_name?: string;
  email?: string;
  product?: string;
}

interface SpotifyTrack {
  id: string;
  name: string;
  uri: string;
  artists: { name: string }[];
  album: { name: string; images: { url: string }[] };
  duration_ms: number;
}

function msToTime(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function SpotifyPage() {
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [sourceAccount, setSourceAccount] = useState("");
  const [query, setQuery] = useState("");
  const [tracks, setTracks] = useState<SpotifyTrack[]>([]);
  const [searching, setSearching] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 3000); };

  const loadStatus = () =>
    fetch("/api/spotify/status").then((r) => r.json()).then(setStatus).catch(() => {});

  useEffect(() => {
    loadStatus();
    api.devices.list().then((d) => {
      setDevices(d);
      if (d.length) setSelectedDevice(d[0].id);
    });
    // Check if returning from Spotify OAuth
    if (new URLSearchParams(location.search).get("spotify") === "connected") {
      showToast("✅ Spotify verbunden!");
      window.history.replaceState({}, "", "/spotify");
    }
  }, []);

  useEffect(() => {
    if (!query.trim() || !status?.connected) { setTracks([]); return; }
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await fetch(`/api/spotify/search?q=${encodeURIComponent(query)}&type=track&limit=30`);
        const data = await r.json();
        setTracks(data?.tracks?.items ?? []);
      } catch { showToast("Suche fehlgeschlagen"); }
      finally { setSearching(false); }
    }, 400);
  }, [query, status?.connected]);

  const play = async (track: SpotifyTrack) => {
    if (!selectedDevice) { showToast("Kein Gerät ausgewählt"); return; }
    try {
      const r = await fetch("/api/spotify/play", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: selectedDevice, spotify_uri: track.uri, source_account: sourceAccount }),
      });
      if (!r.ok) throw new Error((await r.json()).detail);
      showToast(`▶ ${track.name}`);
    } catch (e: unknown) {
      showToast(`Fehler: ${e instanceof Error ? e.message : "Unbekannt"}`);
    }
  };

  const disconnect = async () => {
    await fetch("/api/spotify/disconnect", { method: "DELETE" });
    setStatus({ connected: false });
    setTracks([]);
    showToast("Spotify getrennt");
  };

  return (
    <div className="page">
      {toast && <div className="toast">{toast}</div>}

      <div className="page-header">
        <h1><Music2 size={20} style={{ display: "inline", verticalAlign: "middle", marginRight: 8 }} />Spotify</h1>
        {status?.connected && (
          <select className="device-select" value={selectedDevice} onChange={(e) => setSelectedDevice(e.target.value)}>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        )}
      </div>

      {/* Not connected */}
      {status && !status.connected && (
        <div className="spotify-connect card">
          <div className="spotify-logo">🎵</div>
          <h3>Spotify verbinden</h3>
          <p>Verbinde deinen Spotify-Account, um direkt auf deinen SoundTouch-Lautsprechern zu suchen und abzuspielen.</p>
          <div className="info-box">
            ℹ Für den OAuth-Flow benötigst du eine <strong>Spotify Developer App</strong> mit Client ID und Secret
            in <code>STOC_SPOTIFY_CLIENT_ID</code> und <code>STOC_SPOTIFY_CLIENT_SECRET</code>.
            Alternativ: Spotify-Presets direkt über die Preset-Seite per URI eintragen.
          </div>
          <a href="/api/spotify/auth" className="btn-primary" style={{ textDecoration: "none", display: "inline-flex", gap: 6 }}>
            Mit Spotify verbinden
          </a>
        </div>
      )}

      {/* Connected */}
      {status?.connected && (
        <>
          <div className="spotify-status card">
            <CheckCircle size={18} style={{ color: "var(--accent)" }} />
            <div>
              <div className="spotify-user">{status.display_name}</div>
              <div className="spotify-email">{status.email} · {status.product}</div>
            </div>
            <button className="btn-secondary" onClick={disconnect} style={{ marginLeft: "auto" }}>
              <LogOut size={14} /> Trennen
            </button>
          </div>

          {/* Source account for device */}
          <div className="source-account-row">
            <label style={{ flexDirection: "row", alignItems: "center", gap: 8, textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>Spotify-E-Mail am Gerät:</span>
              <input
                value={sourceAccount}
                onChange={(e) => setSourceAccount(e.target.value)}
                placeholder="name@example.com"
                style={{ flex: 1 }}
              />
            </label>
          </div>

          <div className="search-bar" style={{ marginTop: 16 }}>
            <Search size={16} />
            <input
              className="search-input"
              placeholder="Titel, Artist oder Album suchen..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {searching && <span className="loading-dot" />}
          </div>

          <div className="station-list" style={{ marginTop: 12 }}>
            {tracks.length === 0 && !searching && query && (
              <div className="empty-state">Keine Titel gefunden.</div>
            )}
            {tracks.map((t) => {
              const img = t.album.images?.[2]?.url || t.album.images?.[0]?.url;
              return (
                <div key={t.id} className="station-row">
                  <div className="station-icon">
                    {img ? <img src={img} alt="" /> : <span>🎵</span>}
                  </div>
                  <div className="station-info">
                    <div className="station-name">{t.name}</div>
                    <div className="station-meta">
                      <span>{t.artists.map((a) => a.name).join(", ")}</span>
                      <span>{t.album.name}</span>
                      <span>{msToTime(t.duration_ms)}</span>
                    </div>
                  </div>
                  <button className="play-row-btn" onClick={() => play(t)}><Play size={16} /></button>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
