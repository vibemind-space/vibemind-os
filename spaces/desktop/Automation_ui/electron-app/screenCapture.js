/**
 * Native Electron Screen Capture Module
 * Verwendet desktopCapturer für direkte Bildschirmaufnahme
 */

const { desktopCapturer, screen, ipcMain } = require('electron');

class ScreenCapture {
  constructor() {
    this.isCapturing = false;
    this.captureInterval = null;
    this.frameCallbacks = new Set();
    this.fps = 15; // Frames pro Sekunde
    this.quality = 80; // JPEG Qualität (0-100)
    this.displays = [];
  }

  /**
   * Initialisiert IPC Handler für Renderer-Kommunikation
   */
  setupIPC() {
    ipcMain.handle('screen-capture:get-displays', async () => {
      return this.getDisplays();
    });

    ipcMain.handle('screen-capture:start', async (event, options = {}) => {
      return this.startCapture(options);
    });

    ipcMain.handle('screen-capture:stop', async () => {
      return this.stopCapture();
    });

    ipcMain.handle('screen-capture:get-status', async () => {
      return {
        isCapturing: this.isCapturing,
        fps: this.fps,
        quality: this.quality,
        displays: this.displays
      };
    });

    ipcMain.handle('screen-capture:set-options', async (event, options) => {
      if (options.fps) this.fps = Math.min(60, Math.max(1, options.fps));
      if (options.quality) this.quality = Math.min(100, Math.max(10, options.quality));
      return { fps: this.fps, quality: this.quality };
    });

    console.log('[ScreenCapture] IPC handlers registered');
  }

  /**
   * Holt alle verfügbaren Displays
   */
  async getDisplays() {
    try {
      const sources = await desktopCapturer.getSources({
        types: ['screen'],
        thumbnailSize: { width: 320, height: 180 }
      });

      const electronDisplays = screen.getAllDisplays();

      this.displays = sources.map((source, index) => {
        const display = electronDisplays[index] || {};
        return {
          id: source.id,
          name: source.name,
          index: index,
          width: display.size?.width || 1920,
          height: display.size?.height || 1080,
          thumbnail: source.thumbnail?.toDataURL() || null
        };
      });

      return this.displays;
    } catch (error) {
      console.error('[ScreenCapture] Error getting displays:', error);
      return [];
    }
  }

  /**
   * Startet die Bildschirmaufnahme
   */
  async startCapture(options = {}) {
    if (this.isCapturing) {
      console.log('[ScreenCapture] Already capturing');
      return { success: true, message: 'Already capturing' };
    }

    if (options.fps) this.fps = options.fps;
    if (options.quality) this.quality = options.quality;

    try {
      // Hole aktuelle Displays
      await this.getDisplays();

      if (this.displays.length === 0) {
        throw new Error('No displays found');
      }

      this.isCapturing = true;
      const intervalMs = Math.floor(1000 / this.fps);

      console.log(`[ScreenCapture] Starting capture: ${this.fps} FPS, ${this.quality}% quality`);

      // Capture-Loop
      this.captureInterval = setInterval(async () => {
        await this.captureAllDisplays();
      }, intervalMs);

      // Ersten Frame sofort senden
      await this.captureAllDisplays();

      return { success: true, displays: this.displays };
    } catch (error) {
      console.error('[ScreenCapture] Start error:', error);
      this.isCapturing = false;
      return { success: false, error: error.message };
    }
  }

  /**
   * Stoppt die Bildschirmaufnahme
   */
  stopCapture() {
    if (this.captureInterval) {
      clearInterval(this.captureInterval);
      this.captureInterval = null;
    }
    this.isCapturing = false;
    console.log('[ScreenCapture] Capture stopped');
    return { success: true };
  }

  /**
   * Nimmt alle Displays auf und sendet Frames
   */
  async captureAllDisplays() {
    if (!this.isCapturing) return;

    try {
      const sources = await desktopCapturer.getSources({
        types: ['screen'],
        thumbnailSize: { width: 1920, height: 1080 }
      });

      const timestamp = Date.now();

      for (let i = 0; i < sources.length; i++) {
        const source = sources[i];
        const display = this.displays[i] || { id: source.id, name: source.name, index: i };

        // Thumbnail zu Base64 konvertieren
        const frameData = source.thumbnail?.toDataURL('image/jpeg', this.quality / 100);

        if (frameData) {
          const frame = {
            displayId: display.id,
            displayIndex: i,
            displayName: display.name,
            width: source.thumbnail?.getSize()?.width || 1920,
            height: source.thumbnail?.getSize()?.height || 1080,
            timestamp: timestamp,
            data: frameData
          };

          // An alle Callbacks senden
          this.notifyFrameCallbacks(frame);
        }
      }
    } catch (error) {
      console.error('[ScreenCapture] Capture error:', error);
    }
  }

  /**
   * Registriert einen Callback für Frame-Events
   */
  onFrame(callback) {
    this.frameCallbacks.add(callback);
    return () => this.frameCallbacks.delete(callback);
  }

  /**
   * Benachrichtigt alle Frame-Callbacks
   */
  notifyFrameCallbacks(frame) {
    for (const callback of this.frameCallbacks) {
      try {
        callback(frame);
      } catch (error) {
        console.error('[ScreenCapture] Callback error:', error);
      }
    }
  }

  /**
   * Sendet Frame an ein spezifisches BrowserWindow
   */
  sendFrameToWindow(window, frame) {
    if (window && !window.isDestroyed()) {
      window.webContents.send('screen-capture:frame', frame);
    }
  }
}

// Singleton-Instanz
const screenCapture = new ScreenCapture();

module.exports = { screenCapture, ScreenCapture };
