/**
 * Virtual Desktop Types
 * Defines types for virtual desktop management, streaming, and automation
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

export interface VirtualDesktop {
  /** Unique identifier for the virtual desktop */
  id: string;
  /** Human-readable name */
  name: string;
  /** Desktop resolution */
  resolution: {
    width: number;
    height: number;
  };
  /** Current status */
  status: VirtualDesktopStatus;
  /** Associated applications */
  applications: VirtualDesktopApplication[];
  /** Stream configuration */
  streamConfig: VirtualDesktopStreamConfig;
  /** Automation settings */
  automationConfig: VirtualDesktopAutomationConfig;
  /** Creation timestamp */
  createdAt: Date;
  /** Last activity timestamp */
  lastActivity: Date;
  /** Resource usage statistics */
  resourceUsage: VirtualDesktopResourceUsage;
}

export interface VirtualDesktopApplication {
  /** Application identifier */
  id: string;
  /** Application name */
  name: string;
  /** Executable path */
  executablePath: string;
  /** Process ID (when running) */
  processId?: number;
  /** Application status */
  status: ApplicationStatus;
  /** Window position and size */
  windowBounds?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  /** Launch parameters */
  launchParams?: string[];
  /** Environment variables */
  environment?: Record<string, string>;
}

export interface VirtualDesktopStreamConfig {
  /** Stream quality (1-100) */
  quality: number;
  /** Frame rate (1-60 FPS) */
  frameRate: number;
  /** Stream format */
  format: 'jpeg' | 'png' | 'webp';
  /** Enable audio capture */
  audioEnabled: boolean;
  /** Stream compression */
  compression: 'none' | 'low' | 'medium' | 'high';
  /** Target bitrate (kbps) */
  bitrate?: number;
}

export interface VirtualDesktopAutomationConfig {
  /** Enable OCR processing */
  ocrEnabled: boolean;
  /** OCR regions */
  ocrRegions: OCRRegion[];
  /** Enable event automation */
  eventAutomationEnabled: boolean;
  /** Automation scripts */
  automationScripts: AutomationScript[];
  /** AI agent configuration */
  aiAgentConfig?: AIAgentConfig;
}

export interface OCRRegion {
  /** Region identifier */
  id: string;
  /** Region name */
  name: string;
  /** Region coordinates */
  bounds: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  /** OCR language */
  language: string;
  /** Processing interval (ms) */
  interval: number;
  /** Enable text change detection */
  detectChanges: boolean;
  /** Last detected text */
  lastText?: string;
}

export interface AutomationScript {
  /** Script identifier */
  id: string;
  /** Script name */
  name: string;
  /** Script type */
  type: 'javascript' | 'python' | 'powershell';
  /** Script content */
  content: string;
  /** Trigger conditions */
  triggers: AutomationTrigger[];
  /** Execution parameters */
  parameters?: Record<string, any>;
  /** Enable script */
  enabled: boolean;
}

export interface AutomationTrigger {
  /** Trigger type */
  type: 'ocr_text_change' | 'image_match' | 'time_interval' | 'manual';
  /** Trigger configuration */
  config: Record<string, any>;
  /** Trigger condition */
  condition?: string;
}

export interface AIAgentConfig {
  /** Agent type */
  type: 'gpt4_vision' | 'claude_vision' | 'custom';
  /** API configuration */
  apiConfig: {
    endpoint: string;
    apiKey: string;
    model?: string;
  };
  /** Agent instructions */
  instructions: string;
  /** Processing interval (ms) */
  interval: number;
  /** Enable agent */
  enabled: boolean;
}

export interface VirtualDesktopResourceUsage {
  /** CPU usage percentage */
  cpuUsage: number;
  /** Memory usage (MB) */
  memoryUsage: number;
  /** GPU usage percentage */
  gpuUsage?: number;
  /** Network bandwidth (kbps) */
  networkUsage: number;
  /** Disk I/O (MB/s) */
  diskUsage: number;
}

export type VirtualDesktopStatus = 
  | 'creating'
  | 'active'
  | 'streaming'
  | 'paused'
  | 'stopping'
  | 'stopped'
  | 'error';

export type ApplicationStatus = 
  | 'launching'
  | 'running'
  | 'paused'
  | 'stopped'
  | 'crashed'
  | 'not_responding';

export interface VirtualDesktopCommand {
  /** Command type */
  type: VirtualDesktopCommandType;
  /** Target desktop ID */
  desktopId: string;
  /** Command parameters */
  parameters?: Record<string, any>;
  /** Command timestamp */
  timestamp: Date;
}

export type VirtualDesktopCommandType =
  | 'create_desktop'
  | 'destroy_desktop'
  | 'start_stream'
  | 'stop_stream'
  | 'launch_application'
  | 'close_application'
  | 'send_input'
  | 'take_screenshot'
  | 'start_automation'
  | 'stop_automation'
  | 'update_config';

export interface VirtualDesktopEvent {
  /** Event type */
  type: VirtualDesktopEventType;
  /** Source desktop ID */
  desktopId: string;
  /** Event data */
  data: Record<string, any>;
  /** Event timestamp */
  timestamp: Date;
}

export type VirtualDesktopEventType =
  | 'desktop_created'
  | 'desktop_destroyed'
  | 'stream_started'
  | 'stream_stopped'
  | 'application_launched'
  | 'application_closed'
  | 'ocr_text_detected'
  | 'automation_triggered'
  | 'error_occurred';

export interface VirtualDesktopManager {
  /** List all virtual desktops */
  listDesktops(): Promise<VirtualDesktop[]>;
  /** Create new virtual desktop */
  createDesktop(config: Partial<VirtualDesktop>): Promise<VirtualDesktop>;
  /** Destroy virtual desktop */
  destroyDesktop(desktopId: string): Promise<void>;
  /** Get desktop by ID */
  getDesktop(desktopId: string): Promise<VirtualDesktop | null>;
  /** Update desktop configuration */
  updateDesktop(desktopId: string, updates: Partial<VirtualDesktop>): Promise<VirtualDesktop>;
  /** Execute command on desktop */
  executeCommand(command: VirtualDesktopCommand): Promise<void>;
  /** Subscribe to desktop events */
  subscribeToEvents(callback: (event: VirtualDesktopEvent) => void): () => void;
}