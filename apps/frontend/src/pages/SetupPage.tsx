import { useEffect, useState } from "react";
import { Wifi, RefreshCw, CheckCircle } from "lucide-react";
import { api, Device } from "../lib/api";

type Step = "select" | "name" | "done";

export default function SetupPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selected, setSelected] = useState<Device | null>(null);
  const [step, setStep] = useState<Step>("select");
  const [newName, setNewName] = useState("");
  const [scanning, setScanning] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 4000); };

  useEffect(() => { api.devices.list().then(setDevices); }, []);

  const scan = async () => {
    setScanning(true);
    await api.devices.scan().catch(() => {});
    const d = await api.devices.list().catch(() => []);
    setDevices(d);
    setScanning(false);
    showToast(`${d.length} Gerät(e) gefunden`);
  };

  const selectDevice = (d: Device) => {
    setSelected(d);
    setNewName(d.name);
    setStep("name");
  };

  const saveName = async () => {
    if (!selected) return;
    await api.devices.setName(selected.id, newName).catch((e) => showToast(e.message));
    setStep("done");
  };

  const reset = () => { setStep("select"); setSelected(null); setNewName(""); };

  return (
    <div className="page">
      {toast && <div className="toast">{toast}</div>}

      <div className="page-header">
        <h1>Einrichtung</h1>
      </div>

      <p className="page-desc">
        Gerät umbenennen oder einen neu zurückgesetzten Lautsprecher einrichten.
        Der Cloud-Redirect wird automatisch gesetzt.
      </p>

      {step === "select" && (
        <>
          <div className="setup-section">
            <h3><Wifi size={16} /> Geräte im Netzwerk</h3>
            <button className="btn-secondary" onClick={scan} disabled={scanning}>
              <RefreshCw size={14} className={scanning ? "spin" : ""} />
              {scanning ? "Suche läuft..." : "Netzwerk scannen"}
            </button>
          </div>

          {devices.length === 0 && (
            <div className="empty-state">
              <p>Keine Lautsprecher gefunden. Stelle sicher, dass die Geräte eingeschaltet und im selben Netzwerk sind.</p>
            </div>
          )}

          <div className="device-list">
            {devices.map((d) => (
              <div key={d.id} className="device-list-row" onClick={() => selectDevice(d)}>
                <div>
                  <div className="device-name">{d.name}</div>
                  <div className="device-meta-row">
                    <span>{d.model}</span>
                    <span>{d.ip}</span>
                    <span>FW {d.firmware}</span>
                  </div>
                </div>
                <span className="arrow">›</span>
              </div>
            ))}
          </div>
        </>
      )}

      {step === "name" && selected && (
        <div className="setup-wizard card">
          <h3>Gerät konfigurieren: {selected.model}</h3>
          <p>IP: {selected.ip} · MAC: {selected.mac}</p>

          <label>Gerätename
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="z. B. Wohnzimmer"
            />
          </label>

          <div className="info-box">
            ℹ Der Cloud-Redirect wird bei jedem Start automatisch gesetzt. Für Werksreset-Geräte: schalte das Gerät ein und starte danach einen Netzwerkscan.
          </div>

          <div className="form-actions">
            <button className="btn-primary" onClick={saveName}><CheckCircle size={14} /> Speichern</button>
            <button className="btn-secondary" onClick={reset}>Zurück</button>
          </div>
        </div>
      )}

      {step === "done" && (
        <div className="setup-done card">
          <CheckCircle size={40} className="success-icon" />
          <h3>Fertig!</h3>
          <p>„{newName}" wurde erfolgreich eingerichtet.</p>
          <button className="btn-primary" onClick={reset}>Weiteres Gerät einrichten</button>
        </div>
      )}
    </div>
  );
}
