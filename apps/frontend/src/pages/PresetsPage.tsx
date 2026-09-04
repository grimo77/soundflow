import { useEffect, useState } from "react";
import { Play, Edit2, Save, X } from "lucide-react";
import { api, Device, Preset } from "../lib/api";

const SOURCES = ["TUNEIN", "SPOTIFY", "INTERNET_RADIO", "LOCAL_INTERNET_RADIO"];

function PresetSlot({ preset, slot, deviceId, onSaved, onPlay }: {
  preset: Preset | null;
  slot: number;
  deviceId: string;
  onSaved: () => void;
  onPlay: (slot: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    name: preset?.name ?? "",
    source: preset?.source ?? "TUNEIN",
    location: preset?.location ?? "",
    source_account: preset?.source_account ?? "",
    icon_url: preset?.icon_url ?? "",
  });

  useEffect(() => {
    setForm({
      name: preset?.name ?? "",
      source: preset?.source ?? "TUNEIN",
      location: preset?.location ?? "",
      source_account: preset?.source_account ?? "",
      icon_url: preset?.icon_url ?? "",
    });
  }, [preset]);

  const save = async () => {
    await api.presets.set(deviceId, slot, form);
    setEditing(false);
    onSaved();
  };

  return (
    <div className="preset-card">
      <div className="preset-header">
        <div className="preset-slot-badge">{slot}</div>
        {!editing && (
          <div className="preset-actions">
            {preset?.location && (
              <button onClick={() => onPlay(slot)} title="Abspielen"><Play size={15} /></button>
            )}
            <button onClick={() => setEditing(true)} title="Bearbeiten"><Edit2 size={15} /></button>
          </div>
        )}
      </div>

      {!editing ? (
        <div className="preset-info">
          {preset?.icon_url && (
            <img className="preset-icon" src={preset.icon_url} alt="" onError={(e) => (e.currentTarget.style.display = "none")} />
          )}
          <div className="preset-name">{preset?.name || <span className="empty-preset">Leer</span>}</div>
          {preset?.source && <div className="preset-source">{preset.source}</div>}
        </div>
      ) : (
        <div className="preset-form">
          <label>Name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Mein Sender" />
          </label>
          <label>Quelle
            <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
              {SOURCES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label>URL / Location
            <input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="https://..." />
          </label>
          {form.source === "SPOTIFY" && (
            <label>Spotify Account
              <input value={form.source_account} onChange={(e) => setForm({ ...form, source_account: e.target.value })} />
            </label>
          )}
          <label>Icon URL (optional)
            <input value={form.icon_url} onChange={(e) => setForm({ ...form, icon_url: e.target.value })} />
          </label>
          <div className="form-actions">
            <button className="btn-primary" onClick={save}><Save size={14} /> Speichern</button>
            <button className="btn-secondary" onClick={() => setEditing(false)}><X size={14} /> Abbrechen</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PresetsPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>("");
  const [presets, setPresets] = useState<Preset[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    api.devices.list().then((d) => {
      setDevices(d);
      if (d.length > 0) setSelectedDevice(d[0].id);
    });
  }, []);

  useEffect(() => {
    if (!selectedDevice) return;
    api.presets.list(selectedDevice).then(setPresets).catch(() => setPresets([]));
  }, [selectedDevice]);

  const play = async (slot: number) => {
    await api.presets.select(selectedDevice, slot).catch((e) => showToast(e.message));
    showToast(`▶ Preset ${slot} wird abgespielt`);
  };

  const slots = [1, 2, 3, 4, 5, 6].map((s) => ({
    slot: s,
    preset: presets.find((p) => p.slot === s) ?? null,
  }));

  return (
    <div className="page">
      {toast && <div className="toast">{toast}</div>}

      <div className="page-header">
        <h1>Presets</h1>
        <select className="device-select" value={selectedDevice} onChange={(e) => setSelectedDevice(e.target.value)}>
          {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>

      <p className="page-desc">Die 6 physischen Preset-Tasten deines Lautsprechers — hier konfigurieren und direkt starten.</p>

      <div className="presets-grid">
        {slots.map(({ slot, preset }) => (
          <PresetSlot
            key={slot}
            slot={slot}
            preset={preset}
            deviceId={selectedDevice}
            onSaved={() => api.presets.list(selectedDevice).then(setPresets)}
            onPlay={play}
          />
        ))}
      </div>
    </div>
  );
}
