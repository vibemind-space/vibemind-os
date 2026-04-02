/**
 * TRAE Visual Workflow System - Frontend Type Definitions
 * 
 * Comprehensive type definitions for the TRAE backend integration
 * Author: TRAE Development Team
 * Version: 2.0.0
 */

// ============================================================================
// CORE NODE SYSTEM TYPES
// ============================================================================

export interface Position {
  x: number;
  y: number;
}

export interface Dimensions {
  width: number;
  height: number;
}

export interface NodePort {
  id: string;
  name: string;
  type: DataType;
  required?: boolean;
  description?: string;
}

export interface InputPort extends NodePort {
  defaultValue?: any;
  allowMultiple?: boolean;
}

export interface OutputPort extends NodePort {
  value?: any;
}

export enum DataType {
  STRING = 'string',
  NUMBER = 'number',
  BOOLEAN = 'boolean',
  OBJECT = 'object',
  ARRAY = 'array',
  IMAGE = 'image',
  FILE = 'file',
  ANY = 'any'
}

export enum NodeType {
  TRIGGER = 'trigger',
  ACTION = 'action',
  CONDITION = 'condition',
  TRANSFORM = 'transform',
  OUTPUT = 'output'
}

export enum NodeCategory {
  TRIGGERS = 'triggers',
  ACTIONS = 'actions',
  LOGIC = 'logic',
  DATA = 'data',
  DESKTOP = 'desktop',
  AUTOMATION = 'automation',
  CONFIG = 'config'
}

export enum NodeStatus {
  IDLE = 'idle',
  RUNNING = 'running',
  SUCCESS = 'success',
  ERROR = 'error',
  PAUSED = 'paused'
}

export interface NodeData {
  id: string;
  type: string;
  label: string;
  description: string;
  icon: string;
  category: NodeCategory;
  color: string;
  status: NodeStatus;
  inputs: InputPort[];
  outputs: OutputPort[];
  config: Record<string, any>;
  position: { x: number; y: number };
  metadata: {
    created_at: string;
    updated_at?: string;
    template_version: string;
    execution_count?: number;
    last_execution?: string;
    error_count?: number;
    last_error?: string;
  };
  // Runtime execution data
  execution?: {
    start_time?: string;
    end_time?: string;
    duration_ms?: number;
    progress?: number;
    error?: string;
    result?: any;
  };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
  type?: string;
  animated?: boolean;
  style?: Record<string, any>;
}

export interface WorkflowGraph {
  id: string;
  name: string;
  description?: string;
  nodes: NodeData[];
  edges: WorkflowEdge[];
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

// ============================================================================
// EXECUTION SYSTEM TYPES
// ============================================================================

export interface ExecutionContext {
  workflow_id: string;
  execution_id: string;
  node_id: string;
  inputs: Record<string, any>;
  config: Record<string, any>;
  metadata?: Record<string, any>;
}

export interface ExecutionResult {
  success: boolean;
  outputs: Record<string, any>;
  error?: string;
  metadata?: Record<string, any>;
  execution_time?: number;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  start_time: string;
  end_time?: string;
  node_results: Record<string, ExecutionResult>;
  error?: string;
  metadata?: Record<string, any>;
}

// ============================================================================
// DESKTOP INTEGRATION TYPES
// ============================================================================

export interface DesktopRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ScreenshotOptions {
  region?: DesktopRegion;
  format?: 'png' | 'jpeg' | 'webp';
  quality?: number;
  scale?: number;
}

export interface ClickOptions {
  x: number;
  y: number;
  button?: 'left' | 'right' | 'middle';
  clicks?: number;
  delay?: number;
  validate?: boolean;
}

export interface LiveDesktopConfig {
  fps?: number;
  quality?: number;
  region?: DesktopRegion;
  scale_factor?: number;
  enable_click?: boolean;
  enable_keyboard?: boolean;
  enable_scroll?: boolean;
  click_feedback?: boolean;
  show_cursor?: boolean;
  show_click_indicators?: boolean;
  overlay_enabled?: boolean;
}

// ============================================================================
// OCR SYSTEM TYPES
// ============================================================================

export interface OCRConfig {
  engine?: 'tesseract' | 'easyocr';
  language?: string;
  psm?: number;
  oem?: number;
  confidence_threshold?: number;
  preprocessing?: {
    grayscale?: boolean;
    contrast?: number;
    noise_reduction?: boolean;
    deskew?: boolean;
    scale_factor?: number;
  };
  postprocessing?: {
    trim_whitespace?: boolean;
    remove_line_breaks?: boolean;
    spell_check?: boolean;
    regex_filter?: string;
  };
}

export interface OCRResult {
  text: string;
  confidence: number;
  bounding_boxes?: Array<{
    text: string;
    confidence: number;
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
  raw_data?: any;
  processing_time?: number;
}

// ============================================================================
// FILE SYSTEM TYPES
// ============================================================================

export interface FileWatchConfig {
  path: string;
  recursive?: boolean;
  events?: ('created' | 'modified' | 'deleted' | 'moved')[];
  patterns?: string[];
  ignore_patterns?: string[];
  debounce_ms?: number;
}

export interface FileSystemEvent {
  event_type: 'created' | 'modified' | 'deleted' | 'moved';
  file_path: string;
  is_directory: boolean;
  timestamp: string;
  old_path?: string; // For move events
  metadata?: Record<string, any>;
}

// ============================================================================
// WEBSOCKET TYPES
// ============================================================================

export interface WebSocketMessage {
  type: string;
  data: any;
  timestamp?: string;
  id?: string;
}

export interface WebSocketConfig {
  url: string;
  reconnect?: boolean;
  reconnect_interval?: number;
  max_reconnect_attempts?: number;
  ping_interval?: number;
}

// ============================================================================
// API RESPONSE TYPES
// ============================================================================

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  timestamp?: string;
}

export interface PaginatedResponse<T = any> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// ============================================================================
// SERVICE HEALTH TYPES
// ============================================================================

export interface ServiceHealth {
  service: string;
  status: 'healthy' | 'unhealthy' | 'degraded';
  uptime: number;
  last_check: string;
  details?: Record<string, any>;
}

export interface SystemHealth {
  overall_status: 'healthy' | 'unhealthy' | 'degraded';
  services: ServiceHealth[];
  timestamp: string;
}

// ============================================================================
// UI STATE TYPES
// ============================================================================

export interface UIState {
  selectedNodes: string[];
  selectedEdges: string[];
  viewport: {
    x: number;
    y: number;
    zoom: number;
  };
  sidebarOpen: boolean;
  propertiesOpen: boolean;
  executionPanelOpen: boolean;
}

export interface NotificationState {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
  timestamp: string;
}

// ============================================================================
// HOOK TYPES
// ============================================================================

export interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  sendMessage: (message: WebSocketMessage) => void;
  connect: () => void;
  disconnect: () => void;
  error: string | null;
}

export interface UseApiReturn<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

// ============================================================================
// COMPONENT PROPS TYPES
// ============================================================================

export interface NodeComponentProps {
  data: NodeData;
  selected: boolean;
  onUpdate: (data: Partial<NodeData>) => void;
  onDelete: () => void;
}

export interface CanvasProps {
  workflow: WorkflowGraph;
  onWorkflowChange: (workflow: WorkflowGraph) => void;
  readonly?: boolean;
}

export interface PropertyPanelProps {
  selectedNode: NodeData | null;
  onNodeUpdate: (nodeId: string, updates: Partial<NodeData>) => void;
}

// ============================================================================
// ERROR TYPES
// ============================================================================

export interface TraeError {
  code: string;
  message: string;
  details?: Record<string, any>;
  timestamp: string;
  stack?: string;
}

export class TraeApiError extends Error {
  code: string;
  details?: Record<string, any>;
  
  constructor(code: string, message: string, details?: Record<string, any>) {
    super(message);
    this.name = 'TraeApiError';
    this.code = code;
    this.details = details;
  }
}

// ============================================================================
// UTILITY TYPES
// ============================================================================

export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

export type RequiredFields<T, K extends keyof T> = T & Required<Pick<T, K>>;

export type OptionalFields<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;