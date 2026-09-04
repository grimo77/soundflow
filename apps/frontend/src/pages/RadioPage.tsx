import { useEffect, useState, useRef } from "react";
import { Search, Play, Star } from "lucide-react";
import { api, Device, RadioStation } from "../lib/api";

export default function RadioPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>("");
  const [query, setQuery] = useState("");
  const [stations, setStations] = useState<RadioStation[]>([]);
  const [topStations, setTopStations] = useState<RadioStation[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const searchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.devices.list().then((d) => {
      setDevices(d);
      if (d.length > 0) setSelectedDevice(d[0].id);
    });
    api.radio.top().then(setTopStations).catch(() => {});
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    if (!query.trim()) { setStations([]); return; }
    if (searchRef.current) clearTimeout(searchRef.current);
    searchRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.radio.search(query);
        setStations(res);
      } catch {
        showToast("Suche fehlgeschlagen");
      } finally {
        setLoading(false);
      }
    }, 400);
  }, [query]);

  const play = async (station: RadioStation) => {
    if (!selectedDevice) { showToast("Kein Gerät ausgewählt"); return; }
    try {
      await api.devices.playUrl(selectedDevice, station.url, station.name);
      showToast(`▶ ${station.name} wird abgespielt`);
    } catch (e: unknown) {
      showToast(`Fehler: ${e instanceof Error ? e.message : "Unbekannt"}`);
    }
  };

  const displayStations = query.trim() ? stations : topStations;

  return (
    <div className="page">
      {toast && <div className="toast">{toast}</div>}

      <div className="page-header">
        <h1>Internet Radio</h1>
        <select
          className="device-select"
          value={selectedDevice}
          onChange={(e) => setSelectedDevice(e.target.value)}
        >
          {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>

      <div className="search-bar">
        <Search size={16} />
        <input
          type="text"
          placeholder="Sender suchen..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="search-input"
        />
        {loading && <span className="loading-dot" />}
      </div>

      <div className="section-label">
        {query.trim() ? `Ergebnisse für "${query}"` : <><Star size={14} /> Top Sender</>}
      </div>

      <div className="station-list">
        {displayStations.length === 0 && !loading && (
          <div className="empty-state">
            {query.trim() ? "Keine Sender gefunden." : "Top-Sender werden geladen..."}
          </div>
        )}
        {displayStations.map((s) => (
          <div key={s.id} className="station-row">
            <div className="station-icon">
              {s.favicon
                ? <img src={s.favicon} alt="" onError={(e) => (e.currentTarget.style.display = "none")} />
                : <span>📻</span>}
            </div>
            <div className="station-info">
              <div className="station-name">{s.name}</div>
              <div className="station-meta">
                {s.country && <span>{s.country}</span>}
                {s.bitrate > 0 && <span>{s.bitrate} kbps</span>}
                {s.codec && <span>{s.codec}</span>}
              </div>
            </div>
            <button className="play-row-btn" onClick={() => play(s)} title="Abspielen">
              <Play size={16} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
