/**
 * Desktop Stream Service
 * Manages desktop streaming operations and WebSocket commands
 */

import { sendWebSocketMessage } from '@/config/websocketConfig';

export interface StreamCommand {
  type: string;
  desktopClientId?: string;
  monitorId?: string;
  config?: any;
  timestamp: string;
}

export class DesktopStreamService {
  /**
   * Start desktop stream for a specific client and monitor
   */
  static startStream(
    websocket: WebSocket,
    desktopClientId: string,
    monitorId: string = 'monitor_0',
    config?: any
  ): boolean {
    const command: StreamCommand = {
      type: 'start_desktop_stream',
      desktopClientId,
      monitorId,
      config: config || {
        fps: 15,
        quality: 85,
        scale: 1.0,
        format: 'jpeg',
      },
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Stop desktop stream
   */
  static stopStream(
    websocket: WebSocket,
    desktopClientId: string,
    monitorId?: string
  ): boolean {
    const command: StreamCommand = {
      type: 'stop_desktop_stream',
      desktopClientId,
      monitorId,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Request list of available desktop clients
   */
  static getDesktopClients(websocket: WebSocket): boolean {
    const command = {
      type: 'get_desktop_clients',
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Request screenshot from desktop client
   */
  static requestScreenshot(
    websocket: WebSocket,
    desktopClientId: string,
    monitorId?: string
  ): boolean {
    const command: StreamCommand = {
      type: 'request_screenshot',
      desktopClientId,
      monitorId,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Update stream configuration
   */
  static updateStreamConfig(
    websocket: WebSocket,
    desktopClientId: string,
    config: any
  ): boolean {
    const command = {
      type: 'update_stream_config',
      desktopClientId,
      config,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Send ping to check connection
   */
  static sendPing(websocket: WebSocket): boolean {
    const command = {
      type: 'ping',
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Start OCR extraction for specific regions
   */
  static startOCRExtraction(
    websocket: WebSocket,
    desktopClientId: string,
    regions: any[]
  ): boolean {
    const command = {
      type: 'start_ocr_extraction',
      desktopClientId,
      regions,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Stop OCR extraction
   */
  static stopOCRExtraction(
    websocket: WebSocket,
    desktopClientId: string
  ): boolean {
    const command = {
      type: 'stop_ocr_extraction',
      desktopClientId,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Send mouse click command
   */
  static sendMouseClick(
    websocket: WebSocket,
    desktopClientId: string,
    x: number,
    y: number,
    button: 'left' | 'right' | 'middle' = 'left'
  ): boolean {
    const command = {
      type: 'mouse_click',
      desktopClientId,
      x,
      y,
      button,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }

  /**
   * Send keyboard input
   */
  static sendKeyboardInput(
    websocket: WebSocket,
    desktopClientId: string,
    text: string
  ): boolean {
    const command = {
      type: 'keyboard_input',
      desktopClientId,
      text,
      timestamp: new Date().toISOString(),
    };

    return sendWebSocketMessage(websocket, command);
  }
}
