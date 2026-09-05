import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { LayoutDashboard, Radio, Settings, Grid3X3, Layers, Music2, X } from "lucide-react";

import Dashboard from "./pages/Dashboard";
import RadioPage from "./pages/RadioPage";
import PresetsPage from "./pages/PresetsPage";
import ZonesPage from "./pages/ZonesPage";
import SetupPage from "./pages/SetupPage";
import SpotifyPage from "./pages/SpotifyPage";
import { api } from "./lib/api";

function UpdateBanner() {
  const [info, setInfo] = useState<{ has_update: boolean; latest: string; url: string } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    api.system.updateCheck().then((d) => {
      if (d.has_update) setInfo(d as typeof info);
    }).catch(() => {});
  }, []);

  if (!info || dismissed) return null;
  return (
    <div className="update-banner">
      <span>🎉 Version {info.latest} verfügbar —</span>
      <a href={info.url} target="_blank" rel="noreferrer">Changelog ansehen</a>
      <button onClick={() => setDismissed(true)} aria-label="Schließen"><X size={14} /></button>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <UpdateBanner />
        <nav className="sidebar">
          <div className="logo">
            <span className="logo-icon">🔊</span>
            <span className="logo-text">SoundFlow<br /><small>Bose Local Cloud</small></span>
          </div>
          <NavLink to="/" end><LayoutDashboard size={18} /> Dashboard</NavLink>
          <NavLink to="/radio"><Radio size={18} /> Radio</NavLink>
          <NavLink to="/presets"><Grid3X3 size={18} /> Presets</NavLink>
          <NavLink to="/zones"><Layers size={18} /> Multi-Room</NavLink>
          <NavLink to="/spotify"><Music2 size={18} /> Spotify</NavLink>
          <NavLink to="/setup"><Settings size={18} /> Einrichtung</NavLink>
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/radio" element={<RadioPage />} />
            <Route path="/presets" element={<PresetsPage />} />
            <Route path="/zones" element={<ZonesPage />} />
            <Route path="/spotify" element={<SpotifyPage />} />
            <Route path="/setup" element={<SetupPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
