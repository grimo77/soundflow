const BASE = "/api";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Device {
  id: string;
  name: string;
  ip: string;
  mac: string;
  model: string;
  firmware: string;
  last_seen: number;
}

export interface NowPlaying {
  source: string;
  track: string;
  artist: string;
  album: string;
  art: string;
  play_status: string; // PLAY_STATE | PAUSE_STATE | STOP_STATE
}

export interface Volume {
  actual: number;
  target: number;
  muted: boolean;
}

export interface Preset {
  slot: number;
  name: string;
  source: string;
  source_account: string;
  location: string;
  icon_url: string;
}

export interface RadioStation {
  id: string;
  name: string;
  url: string;
  country: string;
  favicon: string;
  votes: number;
  bitrate: number;
  codec: string;
  tags?: string;
  language?: string;
}

export interface Zone {
  id: string;
  name: string;
  master_device_id: string;
  member_ids: string[];
}

// ── Devices ────────────────────────────────────────────────────────────────

export const api = {
  devices: {
    list: () => req<Device[]>("/devices"),
    nowPlaying: (id: string) => req<NowPlaying>(`/devices/${id}/now_playing`),
    volume: (id: string) => req<Volume>(`/devices/${id}/volume`),
    setVolume: (id: string, level: number) =>
      req(`/devices/${id}/volume`, { method: "POST", body: JSON.stringify({ level }) }),
    key: (id: string, action: string) =>
      req(`/devices/${id}/key`, { method: "POST", body: JSON.stringify({ action }) }),
    playUrl: (id: string, url: string, name?: string) =>
      req(`/devices/${id}/play_url`, { method: "POST", body: JSON.stringify({ url, name }) }),
    setName: (id: string, name: string) =>
      req(`/devices/${id}/setup/name`, { method: "POST", body: JSON.stringify({ name }) }),
    scan: () => req("/devices/scan", { method: "POST" }),
  },
  presets: {
    list: (deviceId: string) => req<Preset[]>(`/presets/${deviceId}`),
    select: (deviceId: string, slot: number) =>
      req(`/presets/${deviceId}/${slot}/select`, { method: "POST" }),
    set: (deviceId: string, slot: number, data: Omit<Preset, "slot">) =>
      req(`/presets/${deviceId}/${slot}`, { method: "PUT", body: JSON.stringify(data) }),
  },
  radio: {
    search: (q: string, country?: string) =>
      req<RadioStation[]>(`/radio/search?q=${encodeURIComponent(q)}${country ? `&country=${country}` : ""}`),
    top: () => req<RadioStation[]>("/radio/top"),
    resolveTuneIn: (guideId: string) =>
      req<{ url: string }>(`/radio/tunein/resolve?guide_id=${guideId}`),
  },
  zones: {
    list: () => req<Zone[]>("/zones"),
    create: (name: string, master_device_id: string, member_device_ids: string[]) =>
      req<Zone>("/zones", { method: "POST", body: JSON.stringify({ name, master_device_id, member_device_ids }) }),
    delete: (id: string) => req(`/zones/${id}`, { method: "DELETE" }),
  },
  system: {
    version: () => req<{ version: string }>("/system/version"),
    updateCheck: () => req<{ current: string; latest: string | null; has_update: boolean; url: string }>("/system/update_check"),
  },
};
