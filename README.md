# 🔊 SoundTouch Open Cloud

**Lokaler, open-source Cloud-Ersatz für Bose® SoundTouch® Lautsprecher.**  
*Local, open-source cloud replacement for Bose® SoundTouch® speakers.*

Ein Docker-Container, eine Web-App, volle lokale Kontrolle — ohne Bose Cloud, ohne proprietäre App.

> **Hinweis:** Dieses Projekt ist nicht mit Bose® Corporation verbunden. Bose® und SoundTouch® sind eingetragene Markenzeichen der Bose® Corporation.

---

## ✨ Features

| Feature | Beschreibung |
|---------|-------------|
| 🖥️ **Dashboard** | Alle Lautsprecher auf einen Blick — Now Playing, Lautstärke, Play/Pause |
| 📻 **Internet Radio** | RadioBrowser-Suche + TuneIn-Kompatibilität für bestehende Presets |
| 🎵 **Spotify** | Über den im Gerät hinterlegten Spotify-Account |
| 🔖 **Presets** | 6 physische Tasten per Web konfigurieren und starten |
| 🏠 **Multi-Room** | Mehrere Lautsprecher zu Zonen zusammenfassen |
| 🔧 **Setup-Wizard** | Neue/zurückgesetzte Geräte einrichten, umbenennen |
| 🔄 **Auto-Discovery** | Lautsprecher werden automatisch per SSDP/UPnP gefunden |
| 🆕 **Update-Banner** | Automatische Benachrichtigung bei neuen Releases |

---

## 🚀 Schnellstart / Quick Start

### Option 1 — Docker Run

```bash
docker run -d \
  --name soundflow \
  --network host \
  -v soundtouch-data:/data \
  ghcr.io/grimo77/soundflow:stable
```

Browser öffnen: **http://localhost:7777**

### Option 2 — Docker Compose (empfohlen)

```bash
# docker-compose.yml herunterladen
curl -O https://raw.githubusercontent.com/grimo77/SoundFlow/main/deployment/docker-compose.yml

# Starten
docker compose up -d

# Logs anzeigen
docker compose logs -f
```

Browser öffnen: **http://localhost:7777**

### Option 3 — Lokal entwickeln

```bash
git clone https://github.com/grimo77/SoundFlow
cd SoundFlow

# Backend
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e "."
uvicorn soundtouch.main:app --reload --port 7777

# Frontend (neues Terminal)
cd apps/frontend
npm install
npm run dev
```

---

## ⚙️ Konfiguration / Configuration

Alle Einstellungen werden über Umgebungsvariablen (Prefix `STOC_`) oder eine `/data/.env` Datei gesetzt.

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `STOC_PORT` | `7777` | Web-UI & API Port — ändern falls belegt |
| `STOC_DISCOVERY_ENABLED` | `true` | SSDP/UPnP Auto-Discovery |
| `STOC_DISCOVERY_TIMEOUT` | `5` | Scan-Timeout in Sekunden |
| `STOC_MANUAL_DEVICE_IPS` | `""` | Kommagetrennte Fallback-IPs |
| `STOC_GITHUB_REPO` | *(dein Repo)* | Für Update-Prüfung |

`.env.template` als Vorlage kopieren:

```bash
cp .env.template /data/.env
```

---

## 🏗️ Architektur

```
Browser (Port 7777)
        ↓
FastAPI Backend (Python 3.12)
   ├── REST API  /api/...
   ├── Static Frontend (React + TypeScript)
   └── SQLite  /data/stoc.db
        ↓
Bose SoundTouch Geräte
   └── HTTP XML API (Port 8090) + WebSocket (Port 8080)
        ↓
Externe Dienste
   ├── RadioBrowser API
   ├── TuneIn Resolver
   └── Spotify (über Gerät-Account)
```

**Stack:** Python 3.12, FastAPI, React 18, TypeScript, Vite, SQLite, Docker

---

## 🛠️ Troubleshooting

| Problem | Lösung |
|---------|--------|
| Keine Geräte gefunden | `network_mode: host` sicherstellen; manuelle IPs via `STOC_MANUAL_DEVICE_IPS` |
| Port 7777 belegt | `STOC_PORT=8080` setzen |
| Container startet nicht | `docker compose logs soundflow` |
| Health Check | `curl http://localhost:7777/health` |

---

## 📦 Unterstützte Geräte / Supported Devices

- SoundTouch 10, 20, 30, 300
- SoundTouch Portable
- Weitere Modelle: Community-Reports willkommen

---

## 🤝 Beitragen / Contributing

Pull Requests sind willkommen! Bitte lies [CONTRIBUTING.md](CONTRIBUTING.md) für Guidelines.

---

## 📄 Lizenz / License

[Apache License 2.0](LICENSE)

---

## ⚠️ Haftungsausschluss / Disclaimer

Diese Software verändert die Konfiguration deiner Bose® Geräte. Die Autoren übernehmen keine Haftung für Schäden oder Fehlfunktionen. Nutzung auf eigene Gefahr.

*This software modifies your Bose® device configuration. The authors accept no liability for damage or malfunction. Use at your own risk.*
