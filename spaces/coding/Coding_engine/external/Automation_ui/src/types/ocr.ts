/**
 * OCR Type Definitions
 * TypeScript interfaces for OCR functionality
 */

export interface OCRRegion {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string;
  language?: string;
  confidence_threshold?: number;
}

export interface OCRResult {
  zone_id: string;
  text: string;
  confidence: number;
  region: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  metadata: {
    processing_time: number;
    engine: string;
    language: string;
    timestamp: string;
  };
}

export interface OCRExtractResponse {
  success: boolean;
  results: OCRResult[];
  total_regions: number;
  processing_time: number;
}

export interface OCRStatusResponse {
  success: boolean;
  status: {
    available: boolean;
    engines: string[];
    initialized: boolean;
    healthy: boolean;
  };
  service_name: string;
}

export interface OCREnginesResponse {
  success: boolean;
  engines: Array<{
    name: string;
    available: boolean;
    version: string;
  }>;
}

/**
 * OCR Region with UI state
 */
export interface OCRRegionWithState extends OCRRegion {
  isActive?: boolean;
  lastExtractedText?: string;
  lastConfidence?: number;
  lastUpdateTime?: string;
  hasChanged?: boolean;
}

/**
 * OCR Extraction State
 */
export interface OCRExtractionState {
  isExtracting: boolean;
  autoExtractEnabled: boolean;
  lastExtractionTime?: string;
  totalExtractions: number;
  errorCount: number;
}

/**
 * OCR Change Detection
 */
export interface OCRTextChange {
  zone_id: string;
  previous_text: string;
  current_text: string;
  confidence: number;
  timestamp: string;
  change_type: 'added' | 'modified' | 'removed';
}
