/**
 * Virtual Desktop Manager Service
 * Manages virtual desktops, applications, and automation pipelines
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import { 
  VirtualDesktop, 
  VirtualDesktopCommand, 
  VirtualDesktopEvent, 
  VirtualDesktopManager as IVirtualDesktopManager,
  VirtualDesktopStatus,
  ApplicationStatus,
  VirtualDesktopApplication
} from '@/types/virtualDesktop';

export class VirtualDesktopManager implements IVirtualDesktopManager {
  private desktops: Map<string, VirtualDesktop> = new Map();
  private eventListeners: ((event: VirtualDesktopEvent) => void)[] = [];
  private websocket: WebSocket | null = null;

  constructor(websocket?: WebSocket) {
    this.websocket = websocket || null;
    this.initializeEventHandlers();
  }

  // ============================================================================
  // DESKTOP LIFECYCLE MANAGEMENT
  // ============================================================================

  async listDesktops(): Promise<VirtualDesktop[]> {
    return Array.from(this.desktops.values());
  }

  async createDesktop(config: Partial<VirtualDesktop>): Promise<VirtualDesktop> {
    const desktopId = config.id || this.generateDesktopId();
    
    const desktop: VirtualDesktop = {
      id: desktopId,
      name: config.name || `Virtual Desktop ${desktopId.slice(-4)}`,
      resolution: config.resolution || { width: 1920, height: 1080 },
      status: 'creating',
      applications: [],
      streamConfig: {
        quality: 80,
        frameRate: 30,
        format: 'jpeg',
        audioEnabled: false,
        compression: 'medium',
        bitrate: 2000,
        ...config.streamConfig
      },
      automationConfig: {
        ocrEnabled: false,
        ocrRegions: [],
        eventAutomationEnabled: false,
        automationScripts: [],
        ...config.automationConfig
      },
      createdAt: new Date(),
      lastActivity: new Date(),
      resourceUsage: {
        cpuUsage: 0,
        memoryUsage: 0,
        networkUsage: 0,
        diskUsage: 0
      }
    };

    // Store desktop
    this.desktops.set(desktopId, desktop);

    // Send creation command to backend
    await this.sendCommand({
      type: 'create_desktop',
      desktopId,
      parameters: {
        resolution: desktop.resolution,
        streamConfig: desktop.streamConfig
      },
      timestamp: new Date()
    });

    // Update status
    desktop.status = 'active';
    
    // Emit event
    this.emitEvent({
      type: 'desktop_created',
      desktopId,
      data: { desktop },
      timestamp: new Date()
    });

    return desktop;
  }

  async destroyDesktop(desktopId: string): Promise<void> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    // Stop all applications
    for (const app of desktop.applications) {
      if (app.status === 'running') {
        await this.closeApplication(desktopId, app.id);
      }
    }

    // Stop streaming if active
    if (desktop.status === 'streaming') {
      await this.stopStream(desktopId);
    }

    // Send destruction command
    await this.sendCommand({
      type: 'destroy_desktop',
      desktopId,
      parameters: {},
      timestamp: new Date()
    });

    // Remove from memory
    this.desktops.delete(desktopId);

    // Emit event
    this.emitEvent({
      type: 'desktop_destroyed',
      desktopId,
      data: {},
      timestamp: new Date()
    });
  }

  async getDesktop(desktopId: string): Promise<VirtualDesktop | null> {
    return this.desktops.get(desktopId) || null;
  }

  async updateDesktop(desktopId: string, updates: Partial<VirtualDesktop>): Promise<VirtualDesktop> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    // Apply updates
    Object.assign(desktop, updates);
    desktop.lastActivity = new Date();

    // Send update command if needed
    if (updates.streamConfig || updates.automationConfig) {
      await this.sendCommand({
        type: 'update_config',
        desktopId,
        parameters: {
          streamConfig: desktop.streamConfig,
          automationConfig: desktop.automationConfig
        },
        timestamp: new Date()
      });
    }

    return desktop;
  }

  // ============================================================================
  // STREAMING MANAGEMENT
  // ============================================================================

  async startStream(desktopId: string): Promise<void> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    if (desktop.status === 'streaming') {
      return; // Already streaming
    }

    await this.sendCommand({
      type: 'start_stream',
      desktopId,
      parameters: {
        streamConfig: desktop.streamConfig
      },
      timestamp: new Date()
    });

    desktop.status = 'streaming';
    desktop.lastActivity = new Date();

    this.emitEvent({
      type: 'stream_started',
      desktopId,
      data: { streamConfig: desktop.streamConfig },
      timestamp: new Date()
    });
  }

  async stopStream(desktopId: string): Promise<void> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    if (desktop.status !== 'streaming') {
      return; // Not streaming
    }

    await this.sendCommand({
      type: 'stop_stream',
      desktopId,
      parameters: {},
      timestamp: new Date()
    });

    desktop.status = 'active';
    desktop.lastActivity = new Date();

    this.emitEvent({
      type: 'stream_stopped',
      desktopId,
      data: {},
      timestamp: new Date()
    });
  }

  // ============================================================================
  // APPLICATION MANAGEMENT
  // ============================================================================

  async launchApplication(
    desktopId: string, 
    executablePath: string, 
    options: {
      name?: string;
      launchParams?: string[];
      environment?: Record<string, string>;
      windowBounds?: { x: number; y: number; width: number; height: number };
    } = {}
  ): Promise<VirtualDesktopApplication> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    const appId = this.generateApplicationId();
    const application: VirtualDesktopApplication = {
      id: appId,
      name: options.name || this.extractApplicationName(executablePath),
      executablePath,
      status: 'launching',
      launchParams: options.launchParams,
      environment: options.environment,
      windowBounds: options.windowBounds
    };

    // Add to desktop
    desktop.applications.push(application);

    // Send launch command
    await this.sendCommand({
      type: 'launch_application',
      desktopId,
      parameters: {
        applicationId: appId,
        executablePath,
        launchParams: options.launchParams,
        environment: options.environment,
        windowBounds: options.windowBounds
      },
      timestamp: new Date()
    });

    // Update status (will be updated by backend response)
    application.status = 'running';
    desktop.lastActivity = new Date();

    this.emitEvent({
      type: 'application_launched',
      desktopId,
      data: { application },
      timestamp: new Date()
    });

    return application;
  }

  async closeApplication(desktopId: string, applicationId: string): Promise<void> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    const appIndex = desktop.applications.findIndex(app => app.id === applicationId);
    if (appIndex === -1) {
      throw new Error(`Application ${applicationId} not found`);
    }

    const application = desktop.applications[appIndex];

    // Send close command
    await this.sendCommand({
      type: 'close_application',
      desktopId,
      parameters: {
        applicationId,
        processId: application.processId
      },
      timestamp: new Date()
    });

    // Remove from desktop
    desktop.applications.splice(appIndex, 1);
    desktop.lastActivity = new Date();

    this.emitEvent({
      type: 'application_closed',
      desktopId,
      data: { applicationId },
      timestamp: new Date()
    });
  }

  // ============================================================================
  // AUTOMATION MANAGEMENT
  // ============================================================================

  async startAutomation(desktopId: string): Promise<void> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    await this.sendCommand({
      type: 'start_automation',
      desktopId,
      parameters: {
        automationConfig: desktop.automationConfig
      },
      timestamp: new Date()
    });

    desktop.lastActivity = new Date();
  }

  async stopAutomation(desktopId: string): Promise<void> {
    const desktop = this.desktops.get(desktopId);
    if (!desktop) {
      throw new Error(`Desktop ${desktopId} not found`);
    }

    await this.sendCommand({
      type: 'stop_automation',
      desktopId,
      parameters: {},
      timestamp: new Date()
    });

    desktop.lastActivity = new Date();
  }

  // ============================================================================
  // COMMAND EXECUTION
  // ============================================================================

  async executeCommand(command: VirtualDesktopCommand): Promise<void> {
    await this.sendCommand(command);
  }

  async sendInput(
    desktopId: string, 
    inputType: 'mouse' | 'keyboard', 
    inputData: Record<string, any>
  ): Promise<void> {
    await this.sendCommand({
      type: 'send_input',
      desktopId,
      parameters: {
        inputType,
        inputData
      },
      timestamp: new Date()
    });
  }

  async takeScreenshot(desktopId: string): Promise<string> {
    // Send screenshot command and wait for response
    await this.sendCommand({
      type: 'take_screenshot',
      desktopId,
      parameters: {},
      timestamp: new Date()
    });

    // In a real implementation, this would wait for the screenshot response
    // For now, return a placeholder
    return 'data:image/jpeg;base64,placeholder';
  }

  // ============================================================================
  // EVENT HANDLING
  // ============================================================================

  subscribeToEvents(callback: (event: VirtualDesktopEvent) => void): () => void {
    this.eventListeners.push(callback);
    
    // Return unsubscribe function
    return () => {
      const index = this.eventListeners.indexOf(callback);
      if (index > -1) {
        this.eventListeners.splice(index, 1);
      }
    };
  }

  private emitEvent(event: VirtualDesktopEvent): void {
    this.eventListeners.forEach(listener => {
      try {
        listener(event);
      } catch (error) {
        console.error('Error in event listener:', error);
      }
    });
  }

  // ============================================================================
  // PRIVATE METHODS
  // ============================================================================

  private initializeEventHandlers(): void {
    if (this.websocket) {
      this.websocket.addEventListener('message', (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleWebSocketMessage(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      });
    }
  }

  private handleWebSocketMessage(message: any): void {
    switch (message.type) {
      case 'virtual_desktop_event':
        this.emitEvent(message.event);
        break;
      case 'desktop_status_update':
        this.updateDesktopStatus(message.desktopId, message.status);
        break;
      case 'application_status_update':
        this.updateApplicationStatus(message.desktopId, message.applicationId, message.status);
        break;
      case 'resource_usage_update':
        this.updateResourceUsage(message.desktopId, message.resourceUsage);
        break;
    }
  }

  private updateDesktopStatus(desktopId: string, status: VirtualDesktopStatus): void {
    const desktop = this.desktops.get(desktopId);
    if (desktop) {
      desktop.status = status;
      desktop.lastActivity = new Date();
    }
  }

  private updateApplicationStatus(
    desktopId: string, 
    applicationId: string, 
    status: ApplicationStatus
  ): void {
    const desktop = this.desktops.get(desktopId);
    if (desktop) {
      const application = desktop.applications.find(app => app.id === applicationId);
      if (application) {
        application.status = status;
        desktop.lastActivity = new Date();
      }
    }
  }

  private updateResourceUsage(desktopId: string, resourceUsage: any): void {
    const desktop = this.desktops.get(desktopId);
    if (desktop) {
      desktop.resourceUsage = { ...desktop.resourceUsage, ...resourceUsage };
      desktop.lastActivity = new Date();
    }
  }

  private async sendCommand(command: VirtualDesktopCommand): Promise<void> {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify({
        type: 'virtual_desktop_command',
        command
      }));
    } else {
      console.warn('WebSocket not connected, command not sent:', command);
    }
  }

  private generateDesktopId(): string {
    // Use a more robust ID generation to prevent duplicates
    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 9);
    const counter = this.desktops.size + 1;
    return `vd_${timestamp}_${counter}_${random}`;
  }

  private generateApplicationId(): string {
    // Use a more robust ID generation to prevent duplicates
    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 9);
    const counter = Math.floor(Math.random() * 1000);
    return `app_${timestamp}_${counter}_${random}`;
  }

  private extractApplicationName(executablePath: string): string {
    const parts = executablePath.split(/[/\\]/);
    const filename = parts[parts.length - 1];
    return filename.replace(/\.[^/.]+$/, ''); // Remove extension
  }
}

// Singleton instance
let virtualDesktopManagerInstance: VirtualDesktopManager | null = null;

export function getVirtualDesktopManager(websocket?: WebSocket): VirtualDesktopManager {
  if (!virtualDesktopManagerInstance) {
    virtualDesktopManagerInstance = new VirtualDesktopManager(websocket);
  }
  return virtualDesktopManagerInstance;
}

export function setVirtualDesktopManagerWebSocket(websocket: WebSocket): void {
  if (virtualDesktopManagerInstance) {
    (virtualDesktopManagerInstance as any).websocket = websocket;
    (virtualDesktopManagerInstance as any).initializeEventHandlers();
  }
}