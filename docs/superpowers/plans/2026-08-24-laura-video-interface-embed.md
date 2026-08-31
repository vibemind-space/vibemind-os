# Laura Video Interface Embed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der VibeMind-`video`-Space zeigt den echten Laura-Renderer und verbindet ihn sicher mit der bereits laufenden Laura-API, ohne Lauras Oberfläche in VibeMind nachzubauen.

**Architecture:** Laura erzeugt einen relativen, hostbaren Renderer-Build. VibeMind lädt dieses Artefakt in seinem vorhandenen `BrowserView`, stellt über einen schmalen Preload-/IPC-Adapter exakt Lauras bestehende `window.laura`-Bridge bereit und übernimmt nur Space-Navigation, Dateidialoge und das `laura-media://`-Streaming. Die alte `video-ui` bleibt bis zu den separaten Sora-, Capture/FaceSwap- und Ablöseplänen unangetastet.

**Tech Stack:** Electron 33, React 18, TypeScript 5.6 strict, Vite 5, Vitest, Node `node:test`, Playwright Electron, pnpm/npm, Laura FastAPI auf `127.0.0.1:8765`.

---

## Scope und Repository-Grenzen

Dieser Plan ist absichtlich nur Teil 1 der freigegebenen Spec:

1. echter Laura-Renderer im Video-Space;
2. sichere Host-Bridge und Medienwiedergabe;
3. Entwicklungs- und Paket-Build;
4. automatisierter Offline-Embed-Test plus Live-Gate gegen Laura.

Eigene Folgepläne behandeln:

- Sora-Generator → Laura-Import/Timeline;
- Live Capture + beide FaceSwap-Modi → Laura-Capture-Panel;
- Entfernung von `voice/electron-app/video-ui` nach bestandenem Funktionsgleichstand.

Die Arbeit berührt drei Git-Grenzen. Commits entstehen zuerst im Laura-Submodul, danach im
`voice`-Submodul und zuletzt im übergeordneten `vibemind-os` nur als Gitlink-/Doku-Commit.
Vor jedem Commit wird ausschließlich die jeweilige Dateiliste gestaged. Bestehende fremde
Änderungen in allen drei Checkouts bleiben unberührt.

## Dateistruktur

### Laura-Submodul `spaces/video/laura`

- Modify: `apps/desktop/vite.renderer.config.ts` — relative Asset-URLs für `file://`-Hosts.
- Modify: `apps/desktop/package.json` — deterministischer `build:embed`-Befehl.
- Create: `apps/desktop/src/embed-build.test.ts` — Vertrag für den portablen Build.

### Voice-Submodul `voice`

- Create: `electron-app/laura-embed-config.js` — reine Pfad-, Service- und Workspace-Grenzen.
- Create: `electron-app/laura-embed-config.test.js` — plattformunabhängige Grenztests.
- Create: `electron-app/laura-preload.js` — `window.laura`-Bridge für den eingebetteten Renderer.
- Create: `electron-app/laura-embed-host.js` — IPC, Dialoge und `laura-media://`.
- Create: `electron-app/laura-embed-host.test.js` — verhaltensbasierte Handler-Registrierung.
- Modify: `electron-app/video-manager.js` — lädt Laura statt `video-ui`.
- Create: `electron-app/video-manager.test.js` — BrowserView-Verhalten mit Fakes.
- Modify: `electron-app/main.js` — Scheme/Host-Lifecycle.
- Modify: `electron-app/package.json` — Tests, Laura-Build und Packaging.
- Modify: `electron-app/e2e/space-navigation.spec.ts` — echte Laura-Seite im BrowserView.

### Parent `vibemind-os`

- Modify: `spaces/video/laura` — Gitlink auf Laura-Commit.
- Modify: `voice` — Gitlink auf Voice-Commit.
- Create: `docs/operations/2026-08-24-laura-ui-embed-live-proof.md` — reproduzierbarer Live-Beweis.

---

### Task 1: Laura-Renderer als portables Artefakt bauen

**Files:**
- Modify: `spaces/video/laura/apps/desktop/vite.renderer.config.ts`
- Modify: `spaces/video/laura/apps/desktop/package.json`
- Create: `spaces/video/laura/apps/desktop/src/embed-build.test.ts`

- [ ] **Step 1: Failing Test für relative Renderer-Assets schreiben**

```ts
import { describe, expect, it } from "vitest";
import type { UserConfig } from "vite";

import config from "../vite.renderer.config";

describe("Laura embed renderer build", () => {
  it("uses relative asset URLs so Electron can load it from file://", () => {
    const resolved = config as UserConfig;
    expect(resolved.base).toBe("./");
  });
});
```

- [ ] **Step 2: RED belegen**

Run:

```powershell
pnpm --dir spaces/video/laura/apps/desktop test -- src/embed-build.test.ts
```

Expected: FAIL mit `expected undefined to be './'`.

- [ ] **Step 3: Vite-Basis und expliziten Embed-Build ergänzen**

In `vite.renderer.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5174, strictPort: false },
});
```

In `apps/desktop/package.json` unter `scripts` ergänzen:

```json
"build:embed": "vite build -c vite.renderer.config.ts --outDir dist"
```

- [ ] **Step 4: GREEN, Typen und Artefakt prüfen**

Run:

```powershell
pnpm --dir spaces/video/laura/apps/desktop test -- src/embed-build.test.ts
pnpm --dir spaces/video/laura/apps/desktop typecheck
pnpm --dir spaces/video/laura/apps/desktop build:embed
Select-String -LiteralPath spaces/video/laura/apps/desktop/dist/index.html -Pattern './assets/'
```

Expected: Test PASS, Typecheck erfolgreich, Build erfolgreich und mindestens ein Treffer
für eine relative Asset-URL.

- [ ] **Step 5: Im Laura-Submodul committen**

```powershell
git -C spaces/video/laura add apps/desktop/vite.renderer.config.ts apps/desktop/package.json apps/desktop/src/embed-build.test.ts
git -C spaces/video/laura commit -m "feat(desktop): publish embeddable renderer build"
```

---

### Task 2: Reine Embed-Konfiguration und typkompatible Preload-Bridge

**Files:**
- Create: `voice/electron-app/laura-embed-config.js`
- Create: `voice/electron-app/laura-embed-config.test.js`
- Create: `voice/electron-app/laura-preload.js`
- Modify: `voice/electron-app/package.json`

- [ ] **Step 1: Failing Tests für Pfad, Token und Workspace-Grenze schreiben**

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  isInsideWorkspace,
  readLauraServiceInfo,
  resolveLauraRendererPath,
} = require('./laura-embed-config');

test('renderer resolution prefers packaged resource and then Laura dist', () => {
  const existing = new Set([path.resolve('R:/resources/laura-renderer/index.html')]);
  const result = resolveLauraRendererPath({
    dirname: path.resolve('C:/repo/voice/electron-app'),
    resourcesPath: path.resolve('R:/resources'),
    existsSync: (candidate) => existing.has(path.resolve(candidate)),
  });
  assert.equal(result, path.resolve('R:/resources/laura-renderer/index.html'));
});

test('service info fails closed without LAURA_TOKEN', () => {
  assert.equal(readLauraServiceInfo({ LAURA_URL: 'http://127.0.0.1:8765' }), null);
  assert.deepEqual(
    readLauraServiceInfo({ LAURA_URL: 'http://127.0.0.1:8765', LAURA_TOKEN: 'secret' }),
    { baseUrl: 'http://127.0.0.1:8765', token: 'secret' },
  );
});

test('workspace guard rejects siblings and accepts descendants', () => {
  const root = path.resolve('C:/Laura/workspace');
  assert.equal(isInsideWorkspace(root, path.join(root, 'exports', 'a.mp4'), 'win32'), true);
  assert.equal(isInsideWorkspace(root, path.resolve('C:/Laura/workspace-evil/a.mp4'), 'win32'), false);
  assert.equal(isInsideWorkspace(root, '', 'win32'), false);
});
```

- [ ] **Step 2: RED belegen**

Run:

```powershell
node --test voice/electron-app/laura-embed-config.test.js
```

Expected: FAIL mit `Cannot find module './laura-embed-config'`.

- [ ] **Step 3: Reine Konfiguration implementieren**

```js
const path = require('node:path');

function resolveLauraRendererPath({ dirname, resourcesPath, existsSync }) {
  const packaged = path.join(resourcesPath || '', 'laura-renderer', 'index.html');
  const development = path.resolve(
    dirname,
    '..',
    '..',
    'spaces',
    'video',
    'laura',
    'apps',
    'desktop',
    'dist',
    'index.html',
  );
  if (resourcesPath && existsSync(packaged)) return packaged;
  if (existsSync(development)) return development;
  throw new Error(`Laura renderer missing; run pnpm laura:build (checked ${development})`);
}

function readLauraServiceInfo(env) {
  const token = env.LAURA_TOKEN;
  if (!token) return null;
  return {
    baseUrl: env.LAURA_URL || `http://127.0.0.1:${env.LAURA_PORT || '8765'}`,
    token,
  };
}

function canonical(value, platform) {
  const resolved = path.resolve(value);
  return platform === 'win32' ? resolved.toLowerCase() : resolved;
}

function isInsideWorkspace(root, candidate, platform = process.platform) {
  if (!root || !candidate || !path.isAbsolute(candidate)) return false;
  const canonicalRoot = canonical(root, platform);
  const canonicalCandidate = canonical(candidate, platform);
  const prefix = canonicalRoot.endsWith(path.sep) ? canonicalRoot : canonicalRoot + path.sep;
  return canonicalCandidate === canonicalRoot || canonicalCandidate.startsWith(prefix);
}

module.exports = { isInsideWorkspace, readLauraServiceInfo, resolveLauraRendererPath };
```

- [ ] **Step 4: Laura-kompatible Preload-Bridge erstellen**

```js
const { contextBridge, ipcRenderer, webUtils } = require('electron');

const bridge = {
  getServiceInfo: () => ipcRenderer.invoke('laura:service-info'),
  pickMediaFile: () => ipcRenderer.invoke('laura:pick-file'),
  saveTextFile: (defaultName, content) =>
    ipcRenderer.invoke('laura:save-file', defaultName, content),
  pathForFile: (file) => webUtils.getPathForFile(file),
  pickMediaFiles: () => ipcRenderer.invoke('laura:pick-files'),
  pickFolder: () => ipcRenderer.invoke('laura:pick-folder'),
  listMediaInFolder: (folder) => ipcRenderer.invoke('laura:list-media-in-folder', folder),
  openPath: (filePath) => ipcRenderer.invoke('laura:open-path', filePath),
  revealPath: (filePath) => ipcRenderer.invoke('laura:reveal-path', filePath),
};

contextBridge.exposeInMainWorld('laura', bridge);
```

Die Methodennamen und Rückgabeverträge müssen exakt
`spaces/video/laura/apps/desktop/src/preload.ts` entsprechen. Es wird weder `ipcRenderer`
noch `fs` direkt exponiert.

- [ ] **Step 5: Testscript ergänzen und GREEN belegen**

In `voice/electron-app/package.json`:

```json
"test:unit": "node --test *.test.js",
"laura:build": "pnpm --dir ../../spaces/video/laura/apps/desktop build:embed"
```

Run:

```powershell
npm --prefix voice/electron-app run test:unit
```

Expected: 3 Tests PASS.

- [ ] **Step 6: Im Voice-Submodul committen**

```powershell
git -C voice add electron-app/laura-embed-config.js electron-app/laura-embed-config.test.js electron-app/laura-preload.js electron-app/package.json
git -C voice commit -m "feat(video): add Laura embed contract"
```

---

### Task 3: Laura-IPC und Medienprotokoll im VibeMind-Host

**Files:**
- Create: `voice/electron-app/laura-embed-host.js`
- Create: `voice/electron-app/laura-embed-host.test.js`
- Modify: `voice/electron-app/main.js`

- [ ] **Step 1: Failing Handler-Test schreiben**

```js
const test = require('node:test');
const assert = require('node:assert/strict');

const { createLauraEmbedHost } = require('./laura-embed-host');

test('host registers the complete Laura renderer contract and fails closed without token', () => {
  const handlers = new Map();
  const host = createLauraEmbedHost({
    app: { getPath: () => 'C:/Laura' },
    dialog: {},
    env: { LAURA_WORKSPACE: 'C:/Laura/workspace' },
    ipcMain: { handle: (name, fn) => handlers.set(name, fn), removeHandler: () => undefined },
    logger: { warn: () => undefined },
    net: { fetch: async () => new Response(null, { status: 404 }) },
    protocol: { handle: () => undefined, unhandle: () => undefined },
    shell: {},
  });
  host.install();
  assert.deepEqual(
    [...handlers.keys()].sort(),
    [
      'laura:list-media-in-folder', 'laura:open-path', 'laura:pick-file',
      'laura:pick-files', 'laura:pick-folder', 'laura:reveal-path',
      'laura:save-file', 'laura:service-info',
    ],
  );
  assert.equal(handlers.get('laura:service-info')(), null);
});
```

- [ ] **Step 2: RED belegen**

Run:

```powershell
node --test voice/electron-app/laura-embed-host.test.js
```

Expected: FAIL mit `Cannot find module './laura-embed-host'`.

- [ ] **Step 3: Host mit vollständigem IPC-Vertrag implementieren**

`laura-embed-host.js` enthält:

```js
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { Readable } = require('node:stream');

const { isInsideWorkspace, readLauraServiceInfo } = require('./laura-embed-config');

const MEDIA_EXTS = new Set([
  '.mp4', '.mov', '.mkv', '.m4v', '.avi', '.webm', '.mxf', '.mpg', '.mpeg',
  '.wav', '.aif', '.aiff', '.flac', '.mp3', '.m4a', '.aac',
]);
const CHANNELS = [
  'laura:service-info', 'laura:pick-file', 'laura:save-file', 'laura:pick-files',
  'laura:pick-folder', 'laura:list-media-in-folder', 'laura:open-path', 'laura:reveal-path',
];

function createLauraEmbedHost({ app, dialog, env, ipcMain, logger, net, protocol, shell }) {
  const serviceInfo = readLauraServiceInfo(env);
  const workspace = env.LAURA_WORKSPACE || path.join(app.getPath('userData'), 'laura-workspace');
  const cache = new Map();

  async function resolveMediaPath(assetId, kind) {
    const key = `${assetId}/${kind}`;
    if (cache.has(key)) return cache.get(key);
    if (!serviceInfo) return null;
    const endpoint = assetId === 'export'
      ? `${serviceInfo.baseUrl}/exports/${kind}`
      : `${serviceInfo.baseUrl}/assets/${assetId}`;
    const response = await net.fetch(endpoint, {
      headers: { 'X-Laura-Token': serviceInfo.token },
    });
    if (!response.ok) return null;
    const payload = await response.json();
    const filePath = assetId === 'export'
      ? payload.status === 'ready' ? payload.path : null
      : payload.files?.find((file) => file.kind === kind)?.path;
    if (!filePath || !isInsideWorkspace(workspace, filePath)) return null;
    cache.set(key, filePath);
    return filePath;
  }

  async function serveMedia(request) {
    const [assetId, kind] = new URL(request.url).pathname.split('/').filter(Boolean);
    if (!assetId || !kind) return new Response('bad media url', { status: 400 });
    const filePath = await resolveMediaPath(assetId, kind);
    if (!filePath) return new Response('media not found', { status: 404 });
    let total;
    try { total = (await fsp.stat(filePath)).size; }
    catch { return new Response('media missing on disk', { status: 404 }); }
    const base = { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes' };
    const match = /bytes=(\d+)-(\d*)/.exec(request.headers.get('Range') || '');
    const toBody = (stream) => Readable.toWeb(stream);
    if (!match) {
      return new Response(toBody(fs.createReadStream(filePath)), {
        status: 200,
        headers: { ...base, 'Content-Length': String(total) },
      });
    }
    const start = Number(match[1]);
    const end = match[2] ? Math.min(Number(match[2]), total - 1) : total - 1;
    if (start >= total || start > end) {
      return new Response('range not satisfiable', {
        status: 416,
        headers: { ...base, 'Content-Range': `bytes */${total}` },
      });
    }
    return new Response(toBody(fs.createReadStream(filePath, { start, end })), {
      status: 206,
      headers: {
        ...base,
        'Content-Range': `bytes ${start}-${end}/${total}`,
        'Content-Length': String(end - start + 1),
      },
    });
  }

  function install() {
    ipcMain.handle('laura:service-info', () => serviceInfo);
    ipcMain.handle('laura:pick-file', async () => {
      const result = await dialog.showOpenDialog({ properties: ['openFile'] });
      return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
    });
    ipcMain.handle('laura:save-file', async (_event, defaultName, content) => {
      const result = await dialog.showSaveDialog({ defaultPath: defaultName });
      if (result.canceled || !result.filePath) return null;
      await fsp.writeFile(result.filePath, content, 'utf8');
      return result.filePath;
    });
    ipcMain.handle('laura:pick-files', async () => {
      const result = await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'] });
      return result.canceled ? [] : result.filePaths;
    });
    ipcMain.handle('laura:pick-folder', async () => {
      const result = await dialog.showOpenDialog({ properties: ['openDirectory'] });
      return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
    });
    ipcMain.handle('laura:list-media-in-folder', async (_event, folder) => {
      const entries = await fsp.readdir(folder, { withFileTypes: true });
      return entries
        .filter((entry) => entry.isFile() && MEDIA_EXTS.has(path.extname(entry.name).toLowerCase()))
        .map((entry) => path.join(folder, entry.name));
    });
    ipcMain.handle('laura:open-path', (_event, filePath) => {
      if (!isInsideWorkspace(workspace, filePath)) return 'rejected: path is outside the workspace';
      void shell.openPath(path.resolve(filePath));
      return '';
    });
    ipcMain.handle('laura:reveal-path', (_event, filePath) => {
      if (!isInsideWorkspace(workspace, filePath)) return 'rejected: path is outside the workspace';
      shell.showItemInFolder(path.resolve(filePath));
      return '';
    });
    void protocol.handle('laura-media', serveMedia);
  }

  function dispose() {
    for (const channel of CHANNELS) ipcMain.removeHandler(channel);
    try { protocol.unhandle('laura-media'); }
    catch (error) { logger.warn('[LauraEmbed] protocol cleanup failed', error); }
  }

  return { dispose, install };
}

module.exports = { createLauraEmbedHost };
```

- [ ] **Step 4: Scheme und Lifecycle in `main.js` verdrahten**

Electron-Import um `dialog` ergänzen und vor `app.whenReady()` registrieren:

```js
const { app, BrowserWindow, dialog, ipcMain, Tray, Menu, globalShortcut, shell, protocol, net } = require('electron');
const { createLauraEmbedHost } = require('./laura-embed-host');

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'laura-media',
    privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true },
  },
]);
```

Bei den Manager-Variablen ergänzen:

```js
let lauraEmbedHost = null;
```

Direkt vor `videoManager = new VideoManager(mainWindow);`:

```js
lauraEmbedHost = createLauraEmbedHost({
  app,
  dialog,
  env: process.env,
  ipcMain,
  logger: console,
  net,
  protocol,
  shell,
});
lauraEmbedHost.install();
```

In `will-quit` ergänzen:

```js
if (videoManager) videoManager.destroy();
if (lauraEmbedHost) lauraEmbedHost.dispose();
```

- [ ] **Step 5: GREEN belegen**

Run:

```powershell
npm --prefix voice/electron-app run test:unit
```

Expected: Host-Test und Konfigurationstests PASS; kein Prozess wird gestartet.

- [ ] **Step 6: Committen**

```powershell
git -C voice add electron-app/laura-embed-host.js electron-app/laura-embed-host.test.js electron-app/main.js
git -C voice commit -m "feat(video): host Laura renderer services"
```

---

### Task 4: VideoManager auf den echten Laura-Renderer umstellen

**Files:**
- Modify: `voice/electron-app/video-manager.js`
- Create: `voice/electron-app/video-manager.test.js`

- [ ] **Step 1: Failing BrowserView-Test schreiben**

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const VideoManager = require('./video-manager');

test('video space loads Laura with the Laura preload and preserves BrowserView lifecycle', () => {
  const calls = [];
  class FakeBrowserView {
    constructor(options) {
      this.options = options;
      this.webContents = {
        loadFile: (file) => calls.push(['loadFile', file]),
        on: () => undefined,
        setWindowOpenHandler: () => undefined,
      };
    }
    setBounds(bounds) { calls.push(['bounds', bounds]); }
  }
  const mainWindow = {
    getContentBounds: () => ({ width: 1200, height: 800 }),
    on: () => undefined,
    setBrowserView: (view) => calls.push(['view', view]),
  };
  const renderer = path.resolve('C:/repo/laura/dist/index.html');
  const manager = new VideoManager(mainWindow, {
    BrowserView: FakeBrowserView,
    rendererPath: renderer,
    shell: { openExternal: () => undefined },
  });
  manager.show();
  assert.equal(manager.videoView.options.webPreferences.preload, path.join(__dirname, 'laura-preload.js'));
  assert.deepEqual(calls[0], ['loadFile', renderer]);
  assert.equal(manager.getIsVisible(), true);
  manager.hide();
  assert.equal(manager.getIsVisible(), false);
});
```

- [ ] **Step 2: RED belegen**

Run:

```powershell
node --test voice/electron-app/video-manager.test.js
```

Expected: FAIL, weil der aktuelle Konstruktor keine Dependencies annimmt und weiterhin
`video-ui/dist/index.html` sowie `video-preload.js` verwendet.

- [ ] **Step 3: Manager minimal auf Laura umstellen**

Änderungen in `video-manager.js`:

```js
const path = require('path');
const fs = require('fs');
const { resolveLauraRendererPath } = require('./laura-embed-config');

class VideoManager {
  constructor(mainWindow, dependencies = {}) {
    const electron = dependencies.BrowserView && dependencies.shell ? null : require('electron');
    this.BrowserView = dependencies.BrowserView || electron.BrowserView;
    this.shell = dependencies.shell || electron.shell;
    this.rendererPath = dependencies.rendererPath || resolveLauraRendererPath({
      dirname: __dirname,
      resourcesPath: process.resourcesPath || '',
      existsSync: fs.existsSync,
    });
    this.mainWindow = mainWindow;
    this.videoView = null;
    this.isVisible = false;
    this.topOffset = 32 + 43;
    if (this.mainWindow) {
      this.mainWindow.on('resize', () => {
        if (this.isVisible && this.videoView) this.updateBounds();
      });
    }
  }

  createView() {
    if (this.videoView) return this.videoView;
    this.videoView = new this.BrowserView({
      webPreferences: {
        preload: path.join(__dirname, 'laura-preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true,
      },
    });
    this.videoView.webContents.loadFile(this.rendererPath);
    this.videoView.webContents.setWindowOpenHandler(({ url }) => {
      void this.shell.openExternal(url);
      return { action: 'deny' };
    });
    this.videoView.webContents.on('will-navigate', (event) => event.preventDefault());
    return this.videoView;
  }
}
```

Die vorhandenen Methoden `show`, `hide`, `toggle`, `updateBounds`, `getIsVisible` und
`destroy` bleiben unverändert. `_resolveRendererPath()` und alle Verweise auf
`video-preload.js` werden entfernt. Kein Fallback auf die alte UI: fehlt der Laura-Build,
bricht der Manager mit der klaren Build-Anweisung aus Task 2 ab.

- [ ] **Step 4: GREEN belegen**

Run:

```powershell
npm --prefix voice/electron-app run test:unit
```

Expected: alle Unit-Tests PASS; der Test beobachtet `loadFile` auf Lauras `index.html`.

- [ ] **Step 5: Committen**

```powershell
git -C voice add electron-app/video-manager.js electron-app/video-manager.test.js
git -C voice commit -m "feat(video): render Laura in the video space"
```

---

### Task 5: Build, Packaging und Electron-E2E

**Files:**
- Modify: `voice/electron-app/package.json`
- Modify: `voice/electron-app/e2e/space-navigation.spec.ts`

- [ ] **Step 1: Failing E2E für den echten Renderer schreiben**

In `space-navigation.spec.ts` ergänzen:

```ts
test('video space embeds the Laura renderer and bridge', async ({ electronApp, mainPage }) => {
  await mainPage.evaluate(() => window.vibemind.showVideo());
  const embedded = await electronApp.evaluate(async ({ BrowserWindow }) => {
    const window = BrowserWindow.getAllWindows()[0];
    const view = window.getBrowserView();
    if (!view) return null;
    return view.webContents.executeJavaScript(`({
      title: document.querySelector('h1')?.textContent ?? '',
      hasLauraBridge: typeof window.laura?.getServiceInfo === 'function',
      hasLegacyBridge: typeof window.vibemindVideo !== 'undefined'
    })`);
  });
  expect(embedded).toEqual({ title: 'Laura', hasLauraBridge: true, hasLegacyBridge: false });
});
```

Ergänze in `voice/electron-app/preload.js` keinen neuen API-Namen: `showVideo()` existiert
bereits. Der Test steuert denselben Nutzerpfad wie der Video-Tab.

- [ ] **Step 2: RED gegen den aktuellen Build belegen**

Run:

```powershell
npm --prefix voice/electron-app run video:build
npm --prefix voice/electron-app run test:e2e -- --grep "video space embeds"
```

Expected: FAIL, weil noch die alte `vibemindVideo`-Oberfläche geladen wird.

- [ ] **Step 3: Build und Paketressource auf Laura umstellen**

In `package.json`:

```json
"scripts": {
  "laura:build": "pnpm --dir ../../spaces/video/laura/apps/desktop build:embed",
  "video:build": "npm run laura:build",
  "test:unit": "node --test *.test.js"
}
```

Unter `build.extraResources` ergänzen:

```json
{
  "from": "../../spaces/video/laura/apps/desktop/dist",
  "to": "laura-renderer",
  "filter": ["**/*"]
}
```

Der bestehende `video-ui`-Quellordner und seine Abhängigkeiten werden in diesem Plan noch
nicht gelöscht; nur der aktive Build-/Ladepfad wechselt.

- [ ] **Step 4: Gesamtes automatisiertes Gate ausführen**

Run:

```powershell
npm --prefix voice/electron-app run video:build
npm --prefix voice/electron-app run test:unit
npm --prefix voice/electron-app run test:e2e -- --grep "video space embeds"
pnpm --dir spaces/video/laura/apps/desktop typecheck
pnpm --dir spaces/video/laura/apps/desktop test
```

Expected: Build erfolgreich; Unit- und E2E-Test PASS; Laura-Typecheck und vollständige
Laura-Desktop-Suite PASS.

- [ ] **Step 5: Paketinhalt prüfen**

Run:

```powershell
npm --prefix voice/electron-app run build:win -- --dir
Get-ChildItem -LiteralPath voice/electron-app/dist/win-unpacked/resources/laura-renderer
```

Expected: `index.html` und `assets/` vorhanden. Das Paket darf weder Token noch `.env`
enthalten.

- [ ] **Step 6: Committen**

```powershell
git -C voice add electron-app/package.json electron-app/e2e/space-navigation.spec.ts
git -C voice commit -m "build(video): package Laura renderer"
```

---

### Task 6: Live-Gate, Gitlinks und Abschluss

**Files:**
- Create: `docs/operations/2026-08-24-laura-ui-embed-live-proof.md`
- Modify: `spaces/video/laura` (Gitlink)
- Modify: `voice` (Gitlink)

- [ ] **Step 1: Fremdstatus und exakte Submodul-Commits protokollieren**

Run:

```powershell
git status --short --branch
git -C spaces/video/laura status --short --branch
git -C voice status --short --branch
git -C spaces/video/laura rev-parse HEAD
git -C voice rev-parse HEAD
```

Expected: nur die geplanten eigenen Commits plus bereits vor Beginn dokumentierte fremde
Änderungen. Bei neuen unbekannten Änderungen stoppen; nichts stagen oder bereinigen.

- [ ] **Step 2: Laura und VibeMind mit gemeinsamem Token starten**

In zwei PowerShell-Fenstern, ohne Tokenwert in Logs oder Doku zu schreiben:

```powershell
$env:LAURA_TOKEN = (Get-Content C:\Users\User\Desktop\Laura\.env | Where-Object { $_ -like 'LAURA_TOKEN=*' } | Select-Object -First 1).Substring(12)
$env:LAURA_WORKSPACE = 'E:\Laura\workspace'
pnpm --dir spaces/video/laura/apps/desktop build:embed
uv run --directory spaces/video/laura/services/local-api laura-api
```

```powershell
$env:LAURA_TOKEN = (Get-Content C:\Users\User\Desktop\Laura\.env | Where-Object { $_ -like 'LAURA_TOKEN=*' } | Select-Object -First 1).Substring(12)
$env:LAURA_WORKSPACE = 'E:\Laura\workspace'
npm --prefix voice/electron-app start
```

Wenn Laura bereits fremd gestartet läuft, nicht neu starten oder stoppen. Stattdessen nur
den vorhandenen Token/Workspace für VibeMind setzen und diesen Umstand im Beleg notieren.

- [ ] **Step 3: Positives UI-Gate belegen**

Manuell im VibeMind-Fenster:

1. Video-Tab öffnen.
2. Prüfen, dass Header, NavRail, Chat, Projektwahl, Timeline und JobCenter aus Laura sichtbar sind.
3. Ein bestehendes Projekt auswählen.
4. Ein Proxy im Laura-Player abspielen und seeken.
5. Einen Dateidialog öffnen und abbrechen.
6. In einen anderen Space und zurück wechseln; Projektzustand und BrowserView bleiben erhalten.

Expected: keine alte `VideoProduction`-Ansicht, kein `401`, kein weißer Renderer, Video-Range-
Requests liefern `200/206`, und das Hauptfenster bleibt bedienbar.

- [ ] **Step 4: Negative Gegenprobe belegen**

VibeMind einmal ohne `LAURA_TOKEN` starten, Laura selbst nicht verändern:

```powershell
Remove-Item Env:LAURA_TOKEN -ErrorAction SilentlyContinue
npm --prefix voice/electron-app start
```

Expected: Laura-Renderer lädt, zeigt klar `Service offline`, Projekt-/Mediendaten erscheinen
nicht. Es gibt weder stillen Token-Fallback noch Verbindung zu einem fremden Backend.

- [ ] **Step 5: Evidenzdokument schreiben**

`docs/operations/2026-08-24-laura-ui-embed-live-proof.md` wird per `apply_patch` mit den
in Step 1 tatsächlich ermittelten drei SHAs und dem realen ISO-8601-Zeitpunkt angelegt.
Es enthält die Überschriften `Versionen`, `Positives Gate`, `Negative Gegenprobe` und
`Nicht-Claims`. Unter dem positiven Gate stehen die beobachteten Resultate für Header,
NavRail, Chat, Projektwahl, Timeline, JobCenter, Projektwahl, Proxy-Playback/Seek,
Dateidialog, Space-Wechsel, authentifizierten API-Zugriff und den beobachteten HTTP-Status
des `laura-media://`-Range-Requests. Unter der Gegenprobe stehen der Start ohne
`LAURA_TOKEN`, die sichtbare Meldung `Service offline` und die Bestätigung, dass keine
Projekte oder Assets angezeigt wurden. Die Nicht-Claims lauten wörtlich:

- Sora ist durch dieses Gate nicht in Laura integriert.
- Capture und FaceSwap sind durch dieses Gate nicht in Laura integriert.
- Die alte Video-UI ist noch nicht entfernt.

Keine Screenshots mit Token, `.env`-Inhalte oder vollständige lokale Medienpfade einchecken.

- [ ] **Step 6: Parent-Gitlinks und Evidenz committen**

```powershell
git add spaces/video/laura voice docs/operations/2026-08-24-laura-ui-embed-live-proof.md
git diff --cached --submodule=log
git commit -m "feat(video): embed Laura interface in VibeMind"
```

- [ ] **Step 7: Abschlussverifikation**

Run:

```powershell
git status --short --branch
git diff HEAD^ --check
git submodule status spaces/video/laura voice
npm --prefix voice/electron-app run test:unit
npm --prefix voice/electron-app run test:e2e -- --grep "video space embeds"
pnpm --dir spaces/video/laura/apps/desktop typecheck
```

Expected: alle Gates PASS; Status enthält ausschließlich die schon vor dieser Arbeit
dokumentierten fremden Änderungen. Keine Aussage zu Sora/Capture/FaceSwap über den expliziten
Nicht-Claim hinaus.

---

## Self-Review gegen die Design-Spec

- Laura ist die einzige aktive Video-Oberfläche: Tasks 4–5.
- Echte Laura-Bridge statt Komponenten-Kopie: Tasks 2–4.
- Local API, Dateidialoge und Medienstream bleiben funktionsfähig: Tasks 2–3 und Live-Gate.
- Fail-closed Token-Verhalten: Tasks 2–3 und negative Gegenprobe.
- Alte UI bleibt bis zum Funktionsgleichstand erhalten: Scope, Task 5 und Nicht-Claims.
- Sora, Lipsync, Capture/FaceSwap werden nicht fälschlich als geliefert behauptet: Scope und Evidenz.
- Entwicklungs- und Paketpfad sind abgedeckt: Tasks 1 und 5.
- Fremde Änderungen und Submodulgrenzen bleiben geschützt: Scope und Task 6.
