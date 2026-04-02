# AutoGen gRPC Security PoC

## Was ist das?

Proof-of-Concept der zeigt, dass Microsoft AutoGen's verteilte gRPC Runtime
**keine Authentifizierung, kein TLS und keine Autorisierung** hat.

Ein Angreifer im selben Netzwerk kann:
- Alle Agent-Nachrichten mitlesen (Eavesdropping)
- Nachrichten faelschen und Security-Guards umgehen (Message Forgery)
- Beliebigen Code auf fremden Containern ausfuehren (Code Injection)

Alles laeuft in Docker-Containern auf deinem eigenen PC. Nichts geht nach aussen.

---

## Voraussetzungen

- **Docker Desktop** (mit `docker compose`)
- **OpenAI API Key** (fuer die GPT-4o Agents)

### OpenAI Key einrichten

Erstelle eine Datei `.env` im Hauptordner (neben diesem README):

```
OPENAI_API_KEY=sk-proj-dein-key-hier
```

Key bekommst du unter: https://platform.openai.com/api-keys

---

## PoC 1: Datenbank-Angriff (`poc_distributed/`)

**Was passiert:**
- Ein legitimes Team hat 3 GPT-4o Agents: QueryAgent (SQL generieren),
  GuardAgent (SQL pruefen), DbExecutor (SQL ausfuehren)
- Der Guard blockt DELETE-Queries korrekt
- Ein Angreifer umgeht den Guard komplett und loescht 4 von 5 Usern

**Starten:**

```bash
cd poc_distributed
docker compose build
docker compose up
```

**Laufzeit:** ca. 90 Sekunden, beendet sich automatisch.

**Was du siehst:**
1. Legitime Queries laufen (Salaries, API Keys) - Guard approved
2. DELETE wird vom GPT-4o Guard geblockt
3. Angreifer sendet DELETE direkt an Executor - Guard umgangen
4. `!!! DATABASE WAS COMPROMISED !!!` - 4 von 5 Usern geloescht

**Aufraeumen:** `docker compose down`

---

## PoC 2: Code-Injection (`poc_codegen/`)

**Was passiert:**
- Ein legitimes Team hat 3 GPT-4o Agents: CodeGen (Code generieren),
  Reviewer (Code pruefen), Executor (Code ausfuehren)
- Der Reviewer blockt gefaehrlichen Code (Dateizugriff, os.system, etc.)
- Ein Angreifer injiziert 3 Payloads direkt am Reviewer vorbei

**Starten:**

```bash
cd poc_codegen
docker compose build
docker compose up
```

**Laufzeit:** ca. 90 Sekunden, beendet sich automatisch.

**Was du siehst:**
1. Fibonacci + Sort werden generiert und ausgefuehrt - Reviewer approved
2. `/etc/passwd` lesen wird vom GPT-4o Reviewer geblockt
3. Angreifer injiziert 3 Payloads direkt an den Executor:
   - Payload 1: Environment Variables gestohlen (inkl. OPENAI_API_KEY!)
   - Payload 2: Dateisystem gelesen (/etc/passwd, /app/)
   - Payload 3: Persistence-Marker geschrieben (/tmp/pwned.txt)
4. `!!! ATTACK DETECTED !!!` - Marker-Datei auf dem legit Container gefunden

**Aufraeumen:** `docker compose down`

---

## Architektur

```
Docker Network (intern, isoliert)
+------------------------------------------+
|                                          |
|  Container 1: HOST                       |
|  - gRPC Coordinator (Port 50051)         |
|  - Kein TLS, keine Auth                  |
|                                          |
|  Container 2: LEGITIMATE WORKER          |
|  - GPT-4o Agents (Query/Guard/Executor)  |
|  - Verarbeitet Anfragen mit Schutz       |
|                                          |
|  Container 3: MALICIOUS WORKER           |
|  - Verbindet sich zum SELBEN Host        |
|  - Kein Passwort noetig!                 |
|  - Liest mit, faelscht Nachrichten       |
|                                          |
+------------------------------------------+
```

---

## Root Cause

AutoGen v0.7.5 `autogen-ext[grpc]`:

| Datei | Problem |
|-------|---------|
| `_worker_runtime_host.py:24` | `add_insecure_port()` - kein TLS |
| `_worker_runtime.py:144` | `insecure_channel()` - kein TLS |
| `_worker_runtime_host_servicer.py:287` | `RegisterAgent` - kein Auth-Check |
| `_worker_runtime_host_servicer.py:308` | `AddSubscription` - keine ACLs |

Bekanntes offenes Issue: https://github.com/microsoft/autogen/issues/4103

---

## Hinweise

- Alles laeuft lokal in Docker. Keine externen Systeme werden angegriffen.
- Der OpenAI Key wird nur fuer die GPT-4o Aufrufe verwendet.
- Die "gestohlenen" API Keys und Daten in der Demo sind Fake-Testdaten.
- Dies ist fuer Responsible Disclosure / Security Research.
