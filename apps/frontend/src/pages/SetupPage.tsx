import { useEffect, useState } from "react";
import { Wifi, RefreshCw, CheckCircle, Server, Music2, Tag, ChevronRight, ChevronLeft, AlertCircle } from "lucide-react";
import { api, Device } from "../lib/api";

type WizardStep = "select" | "redirect" | "name" | "spotify" | "done";

interface LocalInfo {
  ip: string;
  port: number;
  url: string;
  cloud_host: string;
}

interface CloudStatus {
  current: string;
  local: string;
  is_redirected: boolean;
}

function StepIndicator({ current }: { current: WizardStep }) {
  const steps: { key: WizardStep; label: string }[] = [
    { key: "select", label: "Gerät" },
    { key: "redirect", label: "Cloud" },
    { key: "name", label: "Name" },
    { key: "spotify", label: "Spotify" },
    { key: "done", label: "Fertig" },
  ];
  const idx = steps.findIndex((s) => s.key === current);
  return (
    <div className="step-indicator">
      {steps.map((s, i) => (
        <div key={s.key} className={`step-dot ${i < idx ? "done" : i === idx ? "active" : ""}`}>
          <div className="dot">{i < idx ? <CheckCircle size={12} /> : i + 1}</div>
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function SetupPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selected, setSelected] = useState<Device | null>(null);
  const [step, setStep] = useState<WizardStep>("select");
  const [scanning, setScanning] = useState(false);
  const [localInfo, setLocalInfo] = useState<LocalInfo | null>(null);
  const [cloudStatus, setCloudStatus] = useState<CloudStatus | null>(null);
  const [redirecting, setRedirecting] = useState(false);
  const [newName, setNewName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [spotifyEmail, setSpotifyEmail] = useState("");
  const [savingSpotify, setSavingSpotify] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 4000); };

  useEffect(() => {
    api.devices.list().then(setDevices);
    fetch("/api/setup/local_ip").then(r => r.json()).then(setLocalInfo).catch(() => {});
  }, []);

  const scan = async () => {
    setScanning(true);
    await api.devices.scan().catch(() => {});
    const d = await api.devices.list().catch(() => [] as Device[]);
    setDevices(d);
    setScanning(false);
  };

  const selectDevice = async (d: Device) => {
    setSelected(d);
    setNewName(d.name);
    // Load cloud status and spotify account
    try {
      const cs = await fetch(`/api/setup/cloud_server/${d.id}`).then(r => r.json());
      setCloudStatus(cs);
    } catch { setCloudStatus(null); }
    try {
      const sa = await fetch(`/api/setup/spotify_account/${d.id}`).then(r => r.json());
      setSpotifyEmail(sa.email || "");
    } catch { setSpotifyEmail(""); }
    setStep("redirect");
  };

  const doRedirect = async () => {
    if (!selected) return;
    setRedirecting(true);
    try {
      const r = await fetch("/api/setup/redirect_cloud", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: selected.id }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail);
      setCloudStatus({ current: data.host, local: data.host, is_redirected: true });
      showToast("✅ Cloud-Redirect gesetzt!");
    } catch (e: unknown) {
      showToast(`Fehler: ${e instanceof Error ? e.message : "Unbekannt"}`);
    }
    setRedirecting(false);
  };

  const saveName = async () => {
    if (!selected || !newName.trim()) return;
    setSavingName(true);
    try {
      await fetch("/api/setup/set_name", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: selected.id, name: newName }),
      });
      showToast("✅ Name gespeichert!");
      setSelected({ ...selected, name: newName });
    } catch (e: unknown) {
      showToast(`Fehler: ${e instanceof Error ? e.message : "Unbekannt"}`);
    }
    setSavingName(false);
  };

  const saveSpotify = async () => {
    if (!selected || !spotifyEmail.trim()) { setStep("done"); return; }
    setSavingSpotify(true);
    try {
      const r = await fetch("/api/setup/spotify_account", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: selected.id, email: spotifyEmail }),
      });
      if (!r.ok) throw new Error((await r.json()).detail);
      showToast("✅ Spotify-Account gespeichert!");
    } catch (e: unknown) {
      showToast(`Fehler: ${e instanceof Error ? e.message : "Unbekannt"}`);
    }
    setSavingSpotify(false);
    setStep("done");
  };

  const reset = () => {
    setStep("select");
    setSelected(null);
    setCloudStatus(null);
    setNewName("");
    setSpotifyEmail("");
  };

  return (
    <div className="page">
      {toast && <div className="toast">{toast}</div>}
      <div className="page-header"><h1>Einrichtung</h1></div>

      {step !== "select" && <StepIndicator current={step} />}

      {/* ── Step 1: Gerät wählen ── */}
      {step === "select" && (
        <>
          <p className="page-desc">Wähle einen Lautsprecher zum Einrichten. Der Wizard setzt den Cloud-Redirect, den Namen und Spotify automatisch — kein Pi-hole oder DNS nötig.</p>
          <div className="setup-section">
            <h3><Wifi size={16} /> Geräte im Netzwerk</h3>
            <button className="btn-secondary" onClick={scan} disabled={scanning}>
              <RefreshCw size={14} className={scanning ? "spin" : ""} />
              {scanning ? "Suche..." : "Scannen"}
            </button>
          </div>
          {devices.length === 0 && (
            <div className="empty-state"><p>Keine Lautsprecher gefunden. Gerät einschalten und scannen.</p></div>
          )}
          <div className="device-list">
            {devices.map((d) => (
              <div key={d.id} className="device-list-row" onClick={() => selectDevice(d)}>
                <div>
                  <div className="device-name">{d.name}</div>
                  <div className="device-meta-row">
                    <span>{d.model}</span><span>{d.ip}</span><span>FW {d.firmware}</span>
                  </div>
                </div>
                <ChevronRight size={18} style={{ color: "var(--text-dim)" }} />
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── Step 2: Cloud-Redirect ── */}
      {step === "redirect" && selected && (
        <div className="wizard-card card">
          <div className="wizard-icon"><Server size={28} style={{ color: "var(--accent)" }} /></div>
          <h3>Cloud-Redirect setzen</h3>
          <p className="page-desc">
            SoundFlow setzt den Cloud-Server im Lautsprecher auf diese lokale Adresse.<br />
            Kein Pi-hole, kein DNS-Eintrag nötig.
          </p>

          {localInfo && (
            <div className="info-box">
              <strong>Lokale SoundFlow-Adresse:</strong><br />
              <code style={{ fontSize: 13 }}>{localInfo.cloud_host}</code>
            </div>
          )}

          {cloudStatus && (
            <div className={`status-box ${cloudStatus.is_redirected ? "success" : "warn"}`}>
              {cloudStatus.is_redirected
                ? <><CheckCircle size={14} /> Bereits auf SoundFlow umgeleitet</>
                : <><AlertCircle size={14} /> Aktuell: <code>{cloudStatus.current || "cloudws.bose.io"}</code></>
              }
            </div>
          )}

          <div className="form-actions" style={{ marginTop: 16 }}>
            {!cloudStatus?.is_redirected && (
              <button className="btn-primary" onClick={doRedirect} disabled={redirecting}>
                {redirecting ? <RefreshCw size={14} className="spin" /> : <Server size={14} />}
                {redirecting ? "Wird gesetzt..." : "Redirect setzen"}
              </button>
            )}
            <button className="btn-secondary" onClick={() => setStep("name")}>
              {cloudStatus?.is_redirected ? "Weiter" : "Überspringen"} <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Name ── */}
      {step === "name" && selected && (
        <div className="wizard-card card">
          <div className="wizard-icon"><Tag size={28} style={{ color: "var(--accent)" }} /></div>
          <h3>Gerätename</h3>
          <p className="page-desc">Gib dem Lautsprecher einen Namen — z.B. den Raum in dem er steht.</p>
          <label>Name
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="z.B. Wohnzimmer" />
          </label>
          <div className="form-actions" style={{ marginTop: 16 }}>
            <button className="btn-secondary" onClick={() => setStep("redirect")}><ChevronLeft size={14} /> Zurück</button>
            <button className="btn-primary" onClick={async () => { await saveName(); setStep("spotify"); }} disabled={savingName}>
              {savingName ? <RefreshCw size={14} className="spin" /> : <CheckCircle size={14} />}
              Speichern & Weiter
            </button>
          </div>
        </div>
      )}

      {/* ── Step 4: Spotify ── */}
      {step === "spotify" && selected && (
        <div className="wizard-card card">
          <div className="wizard-icon"><Music2 size={28} style={{ color: "#1db954" }} /></div>
          <h3>Spotify verbinden</h3>
          <p className="page-desc">
            Trage die Spotify-E-Mail-Adresse ein, mit der du dich in der Bose-App angemeldet hast.<br />
            SoundFlow speichert sie für diesen Lautsprecher.
          </p>
          <label>Spotify-E-Mail
            <input
              type="email"
              value={spotifyEmail}
              onChange={(e) => setSpotifyEmail(e.target.value)}
              placeholder="name@example.com"
            />
          </label>
          <div className="info-box" style={{ marginTop: 12 }}>
            ℹ Der Lautsprecher muss einmal mit der Bose-App mit Spotify verbunden worden sein, damit die Zugangsdaten im Gerät gespeichert sind. Diese E-Mail wird dann zur Wiedergabe verwendet.
          </div>
          <div className="form-actions" style={{ marginTop: 16 }}>
            <button className="btn-secondary" onClick={() => setStep("name")}><ChevronLeft size={14} /> Zurück</button>
            <button className="btn-primary" onClick={saveSpotify} disabled={savingSpotify}>
              {savingSpotify ? <RefreshCw size={14} className="spin" /> : <CheckCircle size={14} />}
              {spotifyEmail.trim() ? "Speichern & Fertig" : "Überspringen"}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 5: Done ── */}
      {step === "done" && selected && (
        <div className="setup-done card">
          <CheckCircle size={44} className="success-icon" />
          <h3>„{selected.name}" ist bereit!</h3>
          <div className="done-summary">
            <div className="done-row">
              <Server size={14} />
              <span>Cloud-Redirect: <strong>{cloudStatus?.is_redirected ? "Aktiv" : "Übersprungen"}</strong></span>
            </div>
            <div className="done-row">
              <Tag size={14} />
              <span>Name: <strong>{selected.name}</strong></span>
            </div>
            <div className="done-row">
              <Music2 size={14} />
              <span>Spotify: <strong>{spotifyEmail || "Nicht konfiguriert"}</strong></span>
            </div>
          </div>
          <div className="form-actions" style={{ justifyContent: "center" }}>
            <button className="btn-primary" onClick={reset}>Weiteres Gerät einrichten</button>
          </div>
        </div>
      )}
    </div>
  );
}
