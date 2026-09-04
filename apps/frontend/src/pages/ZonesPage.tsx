import { useEffect, useState } from "react";
import { Plus, Trash2, Layers } from "lucide-react";
import { api, Device, Zone } from "../lib/api";

export default function ZonesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", master: "", members: [] as string[] });

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 3000); };

  const load = () => {
    api.devices.list().then(setDevices);
    api.zones.list().then(setZones);
  };

  useEffect(load, []);

  const deviceName = (id: string) => devices.find((d) => d.id === id)?.name ?? id;

  const toggleMember = (id: string) => {
    setForm((f) => ({
      ...f,
      members: f.members.includes(id) ? f.members.filter((m) => m !== id) : [...f.members, id],
    }));
  };

  const createZone = async () => {
    if (!form.master) { showToast("Master-Gerät wählen"); return; }
    if (form.members.length === 0) { showToast("Mindestens ein Mitglied wählen"); return; }
    try {
      await api.zones.create(form.name || "Neue Zone", form.master, form.members);
      showToast("Zone erstellt");
      setCreating(false);
      setForm({ name: "", master: "", members: [] });
      load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Fehler");
    }
  };

  const deleteZone = async (id: string) => {
    await api.zones.delete(id).catch((e) => showToast(e.message));
    load();
  };

  return (
    <div className="page">
      {toast && <div className="toast">{toast}</div>}

      <div className="page-header">
        <h1>Multi-Room</h1>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> Zone erstellen
        </button>
      </div>

      <p className="page-desc">Mehrere Lautsprecher zu einer Zone zusammenfassen — synchrone Wiedergabe über alle Räume.</p>

      {creating && (
        <div className="zone-form card">
          <h3>Neue Zone</h3>
          <label>Name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Wohnzimmer + Küche" />
          </label>
          <label>Master-Lautsprecher (steuert die Gruppe)
            <select value={form.master} onChange={(e) => setForm({ ...form, master: e.target.value })}>
              <option value="">— wählen —</option>
              {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <div className="members-label">Mitglieder (Slave-Lautsprecher):</div>
          <div className="members-grid">
            {devices.filter((d) => d.id !== form.master).map((d) => (
              <label key={d.id} className="member-check">
                <input
                  type="checkbox"
                  checked={form.members.includes(d.id)}
                  onChange={() => toggleMember(d.id)}
                />
                {d.name}
              </label>
            ))}
          </div>
          <div className="form-actions">
            <button className="btn-primary" onClick={createZone}><Layers size={14} /> Erstellen</button>
            <button className="btn-secondary" onClick={() => setCreating(false)}>Abbrechen</button>
          </div>
        </div>
      )}

      {zones.length === 0 && !creating && (
        <div className="empty-state">
          <Layers size={32} />
          <p>Noch keine Zonen erstellt.</p>
        </div>
      )}

      <div className="zones-list">
        {zones.map((z) => (
          <div key={z.id} className="zone-card card">
            <div className="zone-header">
              <div>
                <div className="zone-name">{z.name}</div>
                <div className="zone-master">Master: {deviceName(z.master_device_id)}</div>
              </div>
              <button className="danger-btn" onClick={() => deleteZone(z.id)} title="Zone auflösen">
                <Trash2 size={16} />
              </button>
            </div>
            <div className="zone-members">
              {z.member_ids.map((id) => (
                <span key={id} className="member-badge">{deviceName(id)}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
