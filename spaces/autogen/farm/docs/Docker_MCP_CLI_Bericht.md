# Docker MCP CLI - Umfassender Bericht

## Was ist Docker MCP?

Docker MCP (Model Context Protocol) ist ein CLI-Plugin und Gateway-System, das MCP-Server in isolierten Docker-Containern ausfuehrt. Es dient als zentrale Schnittstelle zwischen AI-Agents (wie Claude, Cursor, VS Code Copilot) und externen Tools/Services. Das Gateway aggregiert mehrere MCP-Server hinter einer einzigen, sicheren Schnittstelle und uebernimmt Routing, Authentifizierung und Zugriffskontrolle.

**Konfigurationsdateien** befinden sich unter `~/.docker/mcp/`:

| Datei | Zweck |
|---|---|
| `docker-mcp.yaml` | Server-Katalog (verfuegbare Server mit Images, Commands, Env-Vars) |
| `registry.yaml` | Aktivierte Server (Whitelist) |
| `config.yaml` | Server-spezifische Konfiguration |
| `tools.yaml` | Tool-Filterung und -Auswahl pro Server |

---

## 1. SECRET - Geheimnisse verwalten

### Zweck
Verwaltet API-Keys, Passwoerter und Credentials sicher ueber Docker Desktops Secret Store. Haelt Geheimnisse aus Umgebungsvariablen und Klartext-Konfigurationen heraus.

### Befehle

| Befehl | Beschreibung |
|---|---|
| `docker mcp secret ls` | Listet alle gespeicherten Secret-Namen auf |
| `docker mcp secret set <name>` | Speichert ein Secret im Docker Desktop Secret Store |
| `docker mcp secret rm <name>` | Loescht ein Secret aus dem Store |
| `docker mcp secret export <server1> <server2>` | Exportiert die Secrets, die bestimmte Server benoetigen |

### Anwendungsbeispiele

```bash
# API-Key fuer einen MCP-Server setzen
docker mcp secret set GITHUB_TOKEN

# Secret per STDIN setzen (z.B. aus einer Datei)
cat token.txt | docker mcp secret set MY_API_KEY

# Alle gespeicherten Secrets auflisten
docker mcp secret ls

# Secrets fuer bestimmte Server exportieren
docker mcp secret export github-official slack
```

### Sicherheitshinweis
Secrets werden im Docker Desktop Secret Store gespeichert und bei Bedarf sicher in die Container-Runtime injiziert. Das Gateway kann mit `--block-secrets` gestartet werden, um zu verhindern, dass Secrets in ein- oder ausgehenden Payloads an Tools weitergegeben werden.

---

## 2. SERVER - MCP-Server verwalten

### Zweck
Kontrolliert, welche MCP-Server aktiviert oder deaktiviert sind. Aktivierte Server stehen den verbundenen AI-Clients ueber das Gateway zur Verfuegung.

### Befehle

| Befehl | Beschreibung |
|---|---|
| `docker mcp server ls` | Listet aktivierte und verfuegbare Server auf |
| `docker mcp server enable <name> [name...]` | Aktiviert einen oder mehrere Server |
| `docker mcp server disable <name> [name...]` | Deaktiviert einen oder mehrere Server |
| `docker mcp server inspect <name>` | Zeigt detaillierte Informationen zu einem Server |
| `docker mcp server reset` | Setzt alle Server zurueck (deaktiviert alle) |

### Anwendungsbeispiele

```bash
# Verfuegbare und aktivierte Server anzeigen
docker mcp server ls

# GitHub MCP-Server aktivieren
docker mcp server enable github-official

# Mehrere Server gleichzeitig aktivieren
docker mcp server enable github-official duckduckgo slack

# Details zu einem Server anzeigen (Image, Env-Vars, Tools)
docker mcp server inspect github-official

# Einen Server deaktivieren
docker mcp server disable duckduckgo

# Alle Server zuruecksetzen
docker mcp server reset
```

### Workflow
Typischer Ablauf: Katalog durchsuchen -> Server aktivieren -> Gateway starten

---

## 3. FEATURE - Experimentelle Features verwalten

### Zweck
Aktiviert oder deaktiviert experimentelle Funktionen, die das Verhalten des Gateways erweitern. Diese Features sind noch nicht stabil und koennen sich aendern.

### Bekannte Features

| Feature | Beschreibung |
|---|---|
| `oauth-interceptor` | OAuth-Interceptor fuer automatische Token-Verwaltung |
| `mcp-oauth-dcr` | Dynamic Client Registration fuer OAuth |
| `dynamic-tools` | Dynamische Tool-Erkennung zur Laufzeit |
| `profiles` | Gateway-Profile fuer verschiedene Konfigurationen |

### Befehle

```bash
# Feature aktivieren
docker mcp feature enable profiles

# Feature deaktivieren
docker mcp feature disable dynamic-tools

# Aktive Features auflisten
docker mcp feature ls
```

### Hinweis
Einige Gateway-Flags (z.B. `--profile`) erfordern, dass das entsprechende Feature vorher aktiviert wurde.

---

## 4. CONFIG - Konfiguration verwalten

### Zweck
Verwaltet server-spezifische Laufzeit-Konfigurationen. Damit koennen individuelle Einstellungen pro Server vorgenommen werden (z.B. Umgebungsvariablen, spezielle Parameter).

### Befehle

| Befehl | Beschreibung |
|---|---|
| `docker mcp config read` | Zeigt die aktuelle Konfiguration an |
| `docker mcp config write '<yaml>'` | Schreibt eine neue Konfiguration |
| `docker mcp config reset` | Setzt die Konfiguration auf Standardwerte zurueck |

### Anwendungsbeispiele

```bash
# Aktuelle Konfiguration lesen
docker mcp config read

# Konfiguration als YAML schreiben
docker mcp config write '
servers:
  github-official:
    env:
      GITHUB_OWNER: "mein-org"
'

# Konfiguration zuruecksetzen
docker mcp config reset
```

### Konfigurationsdatei
Die Konfiguration wird in `~/.docker/mcp/config.yaml` gespeichert und enthaelt Key-Value-Paare pro Server.

---

## 5. TOOLS - MCP-Tools verwalten

### Zweck
Ermoeglicht die Erkennung, Inspektion und direkte Ausfuehrung von MCP-Tools, die von aktiven Servern bereitgestellt werden. Tools sind die einzelnen Funktionen/Faehigkeiten, die ein MCP-Server anbietet (z.B. "search_repositories", "create_issue").

### Befehle

| Befehl | Beschreibung |
|---|---|
| `docker mcp tools ls` | Listet alle verfuegbaren Tools auf |
| `docker mcp tools ls --format=json` | Listet Tools im JSON-Format |
| `docker mcp tools count` | Zaehlt die verfuegbaren Tools |
| `docker mcp tools inspect <tool-name>` | Zeigt Schema, Parameter und Beispiele eines Tools |
| `docker mcp tools call <tool-name> [args]` | Ruft ein Tool direkt auf (Gateway muss laufen) |

### Anwendungsbeispiele

```bash
# Alle verfuegbaren Tools auflisten
docker mcp tools ls

# Anzahl der Tools zaehlen
docker mcp tools count

# Ein bestimmtes Tool inspizieren (zeigt Input-Schema)
docker mcp tools inspect github-official:search_repositories

# Ein Tool direkt aufrufen
docker mcp tools call github-official:create_issue '{"repo":"myrepo","title":"Bug"}'

# Tools als JSON exportieren
docker mcp tools ls --format=json
```

### Tool-Filterung
Beim Gateway-Start koennen Tools gefiltert werden:
```bash
docker mcp gateway run --tools "github-official:*" --tools "slack:send_message"
```

---

## 6. GATEWAY - MCP-Server-Gateway verwalten

### Zweck
Das Gateway ist das Herzstuck des Systems. Es aggregiert alle aktivierten MCP-Server hinter einer einzigen Schnittstelle und stellt sie den AI-Clients zur Verfuegung. Jeder MCP-Server laeuft in einem eigenen isolierten Docker-Container.

### Hauptbefehl

```bash
docker mcp gateway run [flags]
```

### Wichtige Flags

#### Konfiguration
| Flag | Beschreibung | Standard |
|---|---|---|
| `--catalog <path>` | Pfad zum Server-Katalog | `docker-mcp.yaml` |
| `--config <path>` | Pfad zur Konfiguration | `config.yaml` |
| `--registry <path>` | Pfad zur Registry | `registry.yaml` |
| `--servers <list>` | Bestimmte Server aktivieren | - |
| `--enable-all-servers` | Alle Server aktivieren | - |

#### Transport & Netzwerk
| Flag | Beschreibung | Standard |
|---|---|---|
| `--transport <type>` | Transportprotokoll: `stdio`, `sse`, `streaming` | `stdio` |
| `--port <port>` | TCP-Port (nur bei sse/streaming) | - |

#### Ressourcen-Limits
| Flag | Beschreibung | Standard |
|---|---|---|
| `--cpus <n>` | CPUs pro Server-Container | `1` |
| `--memory <size>` | Speicher pro Server-Container | `2Gb` |

#### Sicherheit
| Flag | Beschreibung | Standard |
|---|---|---|
| `--block-secrets` | Scannt Payloads auf Secrets | `true` |
| `--block-network` | Blockiert Netzwerkzugriff fuer Tools | - |
| `--verify-signatures` | Verifiziert Container-Image-Signaturen | - |
| `--secrets <source>` | Secret-Quelle | `docker-desktop` |

#### Entwicklung & Debug
| Flag | Beschreibung | Standard |
|---|---|---|
| `--dry-run` | Startet Gateway ohne Verbindungen | - |
| `--watch` | Auto-Reload bei Konfigaenderungen | `true` |
| `--verbose` | Ausfuehrliche Ausgabe | - |
| `--log-calls` | Protokolliert Tool-Aufrufe | `true` |
| `--keep` | Behaelt gestoppte Container | - |

### Anwendungsbeispiele

```bash
# Gateway im Standard-Modus starten (stdio)
docker mcp gateway run

# Gateway mit SSE-Transport auf Port 8808
docker mcp gateway run --port 8808 --transport sse

# Gateway mit Streaming-Transport
docker mcp gateway run --port 8080 --transport streaming

# Nur bestimmte Server und Tools starten
docker mcp gateway run --servers github-official,slack --tools "github-official:*" --tools "slack:send_message"

# Gateway mit erhoehter Sicherheit
docker mcp gateway run --block-secrets --block-network --verify-signatures

# Trockenlauf zum Testen der Konfiguration
docker mcp gateway run --dry-run --verbose

# Gateway mit mehr Ressourcen
docker mcp gateway run --cpus 2 --memory 4Gb
```

### Transport-Typen

| Typ | Beschreibung | Anwendungsfall |
|---|---|---|
| `stdio` | Standard-Ein/Ausgabe | Lokale Nutzung, einzelner Client |
| `sse` | Server-Sent Events | Multi-Client, Web-basiert |
| `streaming` | Bidirektionales Streaming | Multi-Client, Produktionsumgebung |

---

## Zusaetzliche Befehle (Kurzuebersicht)

### CATALOG - Server-Kataloge verwalten
```bash
docker mcp catalog ls              # Verfuegbare Kataloge auflisten
docker mcp catalog show docker-mcp # Alle Server in einem Katalog anzeigen
docker mcp catalog init            # Standard-Katalog initialisieren
docker mcp catalog import <url>    # Server-Definitionen importieren
```

### CLIENT - AI-Clients verbinden
```bash
docker mcp client connect claude-code --global  # Claude Code verbinden
docker mcp client connect vscode                 # VS Code verbinden
docker mcp client ls                             # Verbundene Clients auflisten
docker mcp client uninstall <client>             # Client-Konfiguration entfernen
```

### POLICY - Zugriffsrichtlinien
```bash
docker mcp policy --help  # Richtlinien fuer Secret-Zugriff verwalten
```

### VERSION
```bash
docker mcp version  # Versionsinformationen anzeigen
```

---

## Typischer Workflow

```
1. Katalog durchsuchen     ->  docker mcp catalog show docker-mcp
2. Server aktivieren       ->  docker mcp server enable github-official
3. Secrets setzen          ->  docker mcp secret set GITHUB_TOKEN
4. Client verbinden        ->  docker mcp client connect claude-code
5. Gateway starten         ->  docker mcp gateway run
6. Tools pruefen           ->  docker mcp tools ls
7. Tools nutzen            ->  (ueber den verbundenen AI-Agent)
```

---

## Quellen

- [Docker MCP Gateway - GitHub](https://github.com/docker/mcp-gateway)
- [Docker MCP CLI Referenz](https://docs.docker.com/reference/cli/docker/mcp/)
- [MCP Gateway Dokumentation](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
- [MCP Toolkit Dokumentation](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/)
- [Docker MCP Gateway Blog](https://www.docker.com/blog/docker-mcp-gateway-secure-infrastructure-for-agentic-ai/)
- [DeepWiki CLI Overview](https://deepwiki.com/docker/mcp-gateway/2.3-cli-command-overview)
