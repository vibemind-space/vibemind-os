/**
 * Detection box from the visual analysis pipeline
 */
export interface DetectionBox {
  id: number;
  x: number;
  y: number;
  width: number;
  height: number;
  text?: string;
  confidence: number;
  icon_file?: string;
  type?: 'icon' | 'text' | 'button' | 'input' | 'unknown';
}

/**
 * Region grouping multiple boxes
 */
export interface Region {
  id: number;
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
  box_ids: number[];
  label?: string;
}

/**
 * Canvas data structure
 */
export interface CanvasData {
  boxes: DetectionBox[];
  regions?: Region[];
  stats?: {
    total_boxes: number;
    ocr_processed: number;
    detection_time_ms?: number;
  };
  background_image?: string;
}

/**
 * Layer visibility configuration
 */
export interface LayerVisibility {
  components: boolean;
  icons: boolean;
  texts: boolean;
  regions: boolean;
}

/**
 * Canvas configuration options
 */
export interface MoireCanvasConfig {
  zoom?: number;
  showMinimap?: boolean;
  layers?: Partial<LayerVisibility>;
  autoRefreshInterval?: number;
  backgroundImage?: string;
  iconBaseUrl?: string;
}

/**
 * Command sent to host application
 */
export interface CanvasCommand {
  action: string;
  value?: string | number | boolean;
}

/**
 * Message handler for IPC communication
 */
export type MessageHandler = (command: CanvasCommand) => void;