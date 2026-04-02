/**
 * OCR Backend Service
 * API client for communication with Python OCR backend
 * 
 * @version 1.1.0 - Erweitert mit Komprimierung und verbessertem Logging
 */

import { safeExecute, transformError, withRetry, ErrorCode } from '@/utils/errorHandling';

// Mock OCR server is running on port 8007 (Python OCR backend crashed - missing dependencies)
const OCR_BACKEND_URL = 'http://localhost:8007/api/v1/ocr';

// Konfiguration für Komprimierung und Performance
const DEFAULT_IMAGE_QUALITY = 0.85; // JPEG-Qualität (0.0 - 1.0)
const MAX_IMAGE_DIMENSION = 1920; // Maximale Bildbreite/-höhe
const ENABLE_LOGGING = true;

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

export class OCRBackendService {
  /**
   * Check OCR backend health and availability
   */
  static async getStatus(): Promise<OCRStatusResponse> {
    const result = await safeExecute(async () => {
      const response = await fetch(`${OCR_BACKEND_URL}/status`, {
        signal: AbortSignal.timeout(5000), // 5 second timeout
      });
      
      if (!response.ok) {
        throw new Error(`OCR status check failed: ${response.statusText}`);
      }
      
      return await response.json() as OCRStatusResponse;
    }, { operation: 'getStatus', endpoint: `${OCR_BACKEND_URL}/status` });

    if (result.error) {
      throw transformError(result.error, { operation: 'getStatus' });
    }

    if (!result.data) {
      throw transformError(new Error('No status data returned'), { operation: 'getStatus' });
    }

    return result.data;
  }

  /**
   * Get list of available OCR engines
   */
  static async getEngines(): Promise<OCREnginesResponse> {
    const result = await safeExecute(async () => {
      const response = await fetch(`${OCR_BACKEND_URL}/engines`, {
        signal: AbortSignal.timeout(5000), // 5 second timeout
      });
      
      if (!response.ok) {
        throw new Error(`OCR engines fetch failed: ${response.statusText}`);
      }
      
      return await response.json() as OCREnginesResponse;
    }, { operation: 'getEngines', endpoint: `${OCR_BACKEND_URL}/engines` });

    if (result.error) {
      throw transformError(result.error, { operation: 'getEngines' });
    }

    if (!result.data) {
      throw transformError(new Error('No engines data returned'), { operation: 'getEngines' });
    }

    return result.data;
  }

  /**
   * Extract text from multiple regions in an image (batch processing)
   * @param imageData Base64 encoded image data
   * @param regions Array of OCR regions to extract
   */
  static async extractText(
    imageData: string,
    regions: OCRRegion[]
  ): Promise<OCRExtractResponse> {
    // Early return for empty regions
    if (regions.length === 0) {
      return {
        success: true,
        results: [],
        total_regions: 0,
        processing_time: 0
      };
    }

    // For single region, use the single-region endpoint
    if (regions.length === 1) {
      const result = await this.extractTextFromRegion(imageData, regions[0]);
      return {
        success: true,
        results: [result],
        total_regions: 1,
        processing_time: result.metadata.processing_time
      };
    }

    // For multiple regions, use batch endpoint with retry logic
    const result = await safeExecute(async () => {
      return await withRetry(async () => {
        const response = await fetch(`${OCR_BACKEND_URL}/extract-regions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            image_data: `data:image/png;base64,${imageData}`,
            regions: regions.map(r => ({
              x: r.x,
              y: r.y,
              width: r.width,
              height: r.height
            })),
            language: regions[0]?.language || 'eng+deu',
            confidence_threshold: regions[0]?.confidence_threshold || 0.7
          }),
          signal: AbortSignal.timeout(30000), // 30 second timeout
        });

        if (!response.ok) {
          throw new Error(`Batch OCR extraction failed: ${response.statusText}`);
        }

        const data = await response.json();

        // Transform batch response to match expected format
        const results: OCRResult[] = data.results.map((result: any, index: number) => ({
          zone_id: regions[index]?.id || `region_${index}`,
          text: result.text || '',
          confidence: result.confidence || 0,
          region: {
            x: regions[index].x,
            y: regions[index].y,
            width: regions[index].width,
            height: regions[index].height
          },
          metadata: {
            processing_time: result.processing_time || 0,
            engine: result.engine || 'unknown',
            language: result.language || 'eng+deu',
            timestamp: new Date().toISOString()
          }
        }));

        return {
          success: data.success,
          results,
          total_regions: data.total_regions,
          processing_time: data.processing_time
        } as OCRExtractResponse;
      }, {
        maxRetries: 2,
        initialDelay: 1000,
        retryableErrors: [ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR, ErrorCode.SERVICE_UNAVAILABLE],
      });
    }, { operation: 'extractText', regionCount: regions.length });

    if (result.error) {
      throw transformError(result.error, { operation: 'extractText', regionCount: regions.length });
    }

    if (!result.data) {
      throw transformError(new Error('No OCR results returned'), { operation: 'extractText' });
    }

    return result.data;
  }

  /**
   * Extract text from a single region
   * @param imageData Base64 encoded image data
   * @param region Single OCR region to extract
   */
  static async extractTextFromRegion(
    imageData: string,
    region: OCRRegion
  ): Promise<OCRResult> {
    const result = await safeExecute(async () => {
      return await withRetry(async () => {
        const response = await fetch(`${OCR_BACKEND_URL}/extract-region`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            image_data: imageData,
            region: {
              x: region.x,
              y: region.y,
              width: region.width,
              height: region.height
            },
            language: region.language || 'eng+deu',
            confidence_threshold: region.confidence_threshold || 0.7
          }),
          signal: AbortSignal.timeout(15000), // 15 second timeout
        });

        if (!response.ok) {
          throw new Error(`OCR region extraction failed: ${response.statusText}`);
        }

        const data = await response.json();
        return {
          zone_id: region.id || 'region',
          text: data.result?.text || '',
          confidence: data.result?.confidence || 0,
          region: {
            x: region.x,
            y: region.y,
            width: region.width,
            height: region.height
          },
          metadata: {
            processing_time: data.result?.processing_time || 0,
            engine: data.result?.engine || 'unknown',
            language: region.language || 'eng+deu',
            timestamp: new Date().toISOString()
          }
        } as OCRResult;
      }, {
        maxRetries: 2,
        initialDelay: 1000,
        retryableErrors: [ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT_ERROR],
      });
    }, { operation: 'extractTextFromRegion', regionId: region.id });

    if (result.error) {
      throw transformError(result.error, { operation: 'extractTextFromRegion', regionId: region.id });
    }

    if (!result.data) {
      throw transformError(new Error('No OCR result returned'), { operation: 'extractTextFromRegion' });
    }

    return result.data;
  }

  /**
   * Convert canvas to base64 image data with compression options
   * @param canvas HTMLCanvasElement from stream
   * @param options Compression options
   */
  static canvasToBase64(canvas: HTMLCanvasElement, options?: {
    quality?: number;
    maxDimension?: number;
    format?: 'png' | 'jpeg' | 'webp';
  }): string {
    const quality = options?.quality ?? DEFAULT_IMAGE_QUALITY;
    const maxDim = options?.maxDimension ?? MAX_IMAGE_DIMENSION;
    const format = options?.format ?? 'jpeg';

    // Check if resizing needed
    const needsResize = canvas.width > maxDim || canvas.height > maxDim;
    
    if (needsResize) {
      // Create temporary canvas for resizing
      const tempCanvas = document.createElement('canvas');
      const ctx = tempCanvas.getContext('2d');
      
      if (!ctx) {
        // Fallback to original if context not available
        if (ENABLE_LOGGING) {
          console.warn('[OCRBackendService] Could not create temp canvas for resizing');
        }
        return canvas.toDataURL(`image/${format}`, quality).split(',')[1];
      }

      // Calculate new dimensions maintaining aspect ratio
      const ratio = Math.min(maxDim / canvas.width, maxDim / canvas.height);
      tempCanvas.width = canvas.width * ratio;
      tempCanvas.height = canvas.height * ratio;

      // Draw scaled image
      ctx.drawImage(canvas, 0, 0, tempCanvas.width, tempCanvas.height);

      if (ENABLE_LOGGING) {
        console.log('[OCRBackendService] Image resized:', {
          original: `${canvas.width}x${canvas.height}`,
          resized: `${tempCanvas.width}x${tempCanvas.height}`,
          format,
          quality
        });
      }

      return tempCanvas.toDataURL(`image/${format}`, quality).split(',')[1];
    }

    // No resizing needed
    const result = canvas.toDataURL(`image/${format}`, quality).split(',')[1];
    
    if (ENABLE_LOGGING) {
      const sizeKB = Math.round((result.length * 3) / 4 / 1024);
      console.log('[OCRBackendService] Image converted:', {
        dimensions: `${canvas.width}x${canvas.height}`,
        format,
        quality,
        sizeKB: `${sizeKB}KB`
      });
    }

    return result;
  }

  /**
   * Convert canvas to base64 with optimal compression for OCR
   * Uses JPEG with 85% quality for best balance of size/quality
   */
  static canvasToBase64Optimized(canvas: HTMLCanvasElement): string {
    return this.canvasToBase64(canvas, {
      quality: 0.85,
      maxDimension: 1920,
      format: 'jpeg'
    });
  }

  /**
   * Check if backend is available and healthy
   */
  static async isHealthy(): Promise<boolean> {
    try {
      const status = await this.getStatus();
      return status.success && status.status.healthy && status.status.available;
    } catch {
      return false;
    }
  }
}
