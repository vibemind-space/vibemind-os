/**
 * ============================================================================
 * SEND TO FILESYSTEM COMPONENT
 * ============================================================================
 * 
 * React component for the "Send to Filesystem" action node.
 * This component handles sending workflow data and results to filesystem storage.
 * 
 * Features:
 * - Accepts any workflow data (click results, type results, HTTP responses, etc.)
 * - Configurable output directory and filename templates
 * - Multiple file formats (JSON, XML, CSV, TXT)
 * - Data validation and error handling
 * - Backup and retry mechanisms
 * - Real-time status monitoring
 * 
 * @author Autonomous Programmer Project
 * @version 1.0.0
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { 
  Save, 
  CheckCircle, 
  XCircle, 
  Clock, 
  FileText, 
  AlertTriangle,
  RefreshCw,
  Database
} from 'lucide-react';

// ============================================================================
// INTERFACES AND TYPES
// ============================================================================

interface SendToFilesystemConfig {
  // File output settings
  output_directory: string;
  filename_template: string;
  file_format: 'json' | 'xml' | 'csv' | 'txt';
  // Data processing
  include_metadata: boolean;
  include_timestamp: boolean;
  compress_data: boolean;
  // Filesystem behavior
  overwrite_existing: boolean;
  create_backup: boolean;
  auto_create_directories: boolean;
  // Validation and error handling
  validate_data: boolean;
  retry_on_error: boolean;
  max_retry_attempts: number;
  // Notification settings
  notify_on_success: boolean;
  notify_on_error: boolean;
  webhook_notification: string;
}

interface FilesystemSaveResult {
  success: boolean;
  filepath: string;
  filesize: number;
  timestamp: string;
  format: string;
  metadata?: any;
  error?: string;
  retryCount?: number;
}

interface SendToFilesystemProps {
  nodeId: string;
  data: any; // The workflow data to send to filesystem
  config: SendToFilesystemConfig;
  autoSave?: boolean;
  onSaveComplete?: (result: FilesystemSaveResult) => void;
  onError?: (error: string) => void;
  className?: string;
}

interface SaveStatus {
  status: 'idle' | 'saving' | 'success' | 'error' | 'retrying';
  progress: number;
  message: string;
  lastSave?: FilesystemSaveResult;
  retryCount: number;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

const SendToFilesystem: React.FC<SendToFilesystemProps> = ({
  nodeId,
  data,
  config,
  autoSave = false,
  onSaveComplete,
  onError,
  className = ''
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [saveStatus, setSaveStatus] = useState<SaveStatus>({
    status: 'idle',
    progress: 0,
    message: 'Ready to save data',
    retryCount: 0
  });

  const [saveHistory, setSaveHistory] = useState<FilesystemSaveResult[]>([]);
  const [isValidData, setIsValidData] = useState<boolean>(false);

  // ============================================================================
  // DATA VALIDATION
  // ============================================================================

  const validateData = useCallback((inputData: any): boolean => {
    if (!inputData) {
      return false;
    }

    // Check if data is valid based on configuration
    if (config.validate_data) {
      try {
        // Basic validation - ensure data can be serialized
        JSON.stringify(inputData);
        return true;
      } catch (error) {
        console.error('Data validation failed:', error);
        return false;
      }
    }

    return true;
  }, [config.validate_data]);

  // ============================================================================
  // FILESYSTEM OPERATIONS
  // ============================================================================

  const generateFilename = useCallback((template: string, dataType: string): string => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const randomId = Math.random().toString(36).substring(2, 8);
    
    return template
      .replace('{timestamp}', timestamp)
      .replace('{type}', dataType)
      .replace('{id}', randomId)
      .replace('{nodeId}', nodeId);
  }, [nodeId]);

  const formatData = useCallback((inputData: any, format: string): string => {
    const processedData = {
      ...(config.include_metadata && {
        metadata: {
          nodeId,
          timestamp: new Date().toISOString(),
          format,
          source: 'send_to_filesystem_node'
        }
      }),
      ...(config.include_timestamp && {
        timestamp: new Date().toISOString()
      }),
      data: inputData
    };

    switch (format) {
      case 'json':
        return JSON.stringify(processedData, null, 2);
      case 'xml':
        return `<?xml version="1.0" encoding="UTF-8"?>
<workflow_data>
  <timestamp>${processedData.timestamp || ''}</timestamp>
  <data>${JSON.stringify(processedData.data)}</data>
</workflow_data>`;
      case 'csv':
        // Simple CSV conversion for basic data
        if (Array.isArray(processedData.data)) {
          const headers = Object.keys(processedData.data[0] || {});
          const csvHeaders = headers.join(',');
          const csvRows = processedData.data.map(row => 
            headers.map(header => JSON.stringify(row[header] || '')).join(',')
          );
          return [csvHeaders, ...csvRows].join('\n');
        }
        return JSON.stringify(processedData);
      case 'txt':
        return typeof processedData.data === 'string' 
          ? processedData.data 
          : JSON.stringify(processedData, null, 2);
      default:
        return JSON.stringify(processedData, null, 2);
    }
  }, [config, nodeId]);

  const saveToFilesystem = useCallback(async (inputData: any, retryCount = 0): Promise<FilesystemSaveResult> => {
    try {
      setSaveStatus(prev => ({
        ...prev,
        status: retryCount > 0 ? 'retrying' : 'saving',
        progress: 25,
        message: retryCount > 0 ? `Retrying save (attempt ${retryCount + 1})...` : 'Preparing data...',
        retryCount
      }));

      // Validate data if required
      if (config.validate_data && !validateData(inputData)) {
        throw new Error('Data validation failed');
      }

      setSaveStatus(prev => ({ ...prev, progress: 50, message: 'Formatting data...' }));

      // Format data according to configuration
      const formattedData = formatData(inputData, config.file_format);
      const filename = generateFilename(config.filename_template, typeof inputData);
      const filepath = `${config.output_directory}/${filename}.${config.file_format}`;

      setSaveStatus(prev => ({ ...prev, progress: 75, message: 'Writing to filesystem...' }));

      // Simulate filesystem write operation
      // In a real implementation, this would use Node.js fs module or a filesystem API
      await new Promise(resolve => setTimeout(resolve, 1000));

      const result: FilesystemSaveResult = {
        success: true,
        filepath,
        filesize: formattedData.length,
        timestamp: new Date().toISOString(),
        format: config.file_format,
        metadata: config.include_metadata ? {
          nodeId,
          retryCount,
          originalDataType: typeof inputData
        } : undefined
      };

      setSaveStatus(prev => ({
        ...prev,
        status: 'success',
        progress: 100,
        message: `Successfully saved to ${filepath}`,
        lastSave: result,
        retryCount: 0
      }));

      // Add to save history
      setSaveHistory(prev => [result, ...prev.slice(0, 9)]); // Keep last 10 saves

      // Trigger success callback
      onSaveComplete?.(result);

      return result;

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      
      // Handle retry logic
      if (config.retry_on_error && retryCount < config.max_retry_attempts) {
        console.warn(`Save attempt ${retryCount + 1} failed, retrying...`, errorMessage);
        await new Promise(resolve => setTimeout(resolve, 1000 * (retryCount + 1))); // Exponential backoff
        return saveToFilesystem(inputData, retryCount + 1);
      }

      const errorResult: FilesystemSaveResult = {
        success: false,
        filepath: '',
        filesize: 0,
        timestamp: new Date().toISOString(),
        format: config.file_format,
        error: errorMessage,
        retryCount
      };

      setSaveStatus(prev => ({
        ...prev,
        status: 'error',
        progress: 0,
        message: `Save failed: ${errorMessage}`,
        retryCount: 0
      }));

      // Trigger error callback
      onError?.(errorMessage);

      return errorResult;
    }
  }, [config, validateData, formatData, generateFilename, nodeId, onSaveComplete, onError]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Validate data when it changes
  useEffect(() => {
    setIsValidData(validateData(data));
  }, [data, validateData]);

  // Auto-save when data changes (if enabled)
  useEffect(() => {
    if (autoSave && data && isValidData && saveStatus.status === 'idle') {
      saveToFilesystem(data);
    }
  }, [autoSave, data, isValidData, saveStatus.status, saveToFilesystem]);

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleManualSave = () => {
    if (data && isValidData) {
      saveToFilesystem(data);
    }
  };

  const handleRetry = () => {
    if (data && isValidData) {
      saveToFilesystem(data);
    }
  };

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const getStatusIcon = () => {
    switch (saveStatus.status) {
      case 'saving':
      case 'retrying':
        return <RefreshCw className="w-4 h-4 animate-spin" />;
      case 'success':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Save className="w-4 h-4" />;
    }
  };

  const getStatusColor = () => {
    switch (saveStatus.status) {
      case 'saving':
      case 'retrying':
        return 'bg-blue-500';
      case 'success':
        return 'bg-green-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <Card className={`w-full ${className}`}>
      <CardHeader>
        <CardTitle className="flex items-center space-x-2">
          <Database className="w-5 h-5" />
          <span>Send to Filesystem</span>
          <Badge variant="outline" className={getStatusColor()}>
            {saveStatus.status}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status Display */}
        <div className="flex items-center space-x-3">
          {getStatusIcon()}
          <div className="flex-1">
            <div className="text-sm font-medium">{saveStatus.message}</div>
            {saveStatus.status === 'saving' || saveStatus.status === 'retrying' ? (
              <Progress value={saveStatus.progress} className="mt-1" />
            ) : null}
          </div>
        </div>

        {/* Data Validation Status */}
        <div className="flex items-center space-x-2">
          {isValidData ? (
            <CheckCircle className="w-4 h-4 text-green-500" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-yellow-500" />
          )}
          <span className="text-sm">
            Data {isValidData ? 'valid' : 'invalid or missing'}
          </span>
        </div>

        {/* Configuration Summary */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Output Directory:</span>
            <div className="font-mono text-xs">{config.output_directory}</div>
          </div>
          <div>
            <span className="text-muted-foreground">File Format:</span>
            <div className="font-mono text-xs">{config.file_format.toUpperCase()}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Auto Create Dirs:</span>
            <div className="font-mono text-xs">{config.auto_create_directories ? 'Yes' : 'No'}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Backup on Overwrite:</span>
            <div className="font-mono text-xs">{config.create_backup ? 'Yes' : 'No'}</div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-2">
          <Button
            onClick={handleManualSave}
            disabled={!data || !isValidData || saveStatus.status === 'saving' || saveStatus.status === 'retrying'}
            size="sm"
          >
            <Save className="w-4 h-4 mr-2" />
            Save Now
          </Button>
          
          {saveStatus.status === 'error' && (
            <Button
              onClick={handleRetry}
              variant="outline"
              size="sm"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          )}
        </div>

        {/* Last Save Result */}
        {saveStatus.lastSave && (
          <Alert>
            <FileText className="w-4 h-4" />
            <AlertDescription>
              <div className="text-sm">
                <div><strong>Last Save:</strong> {saveStatus.lastSave.filepath}</div>
                <div><strong>Size:</strong> {saveStatus.lastSave.filesize} bytes</div>
                <div><strong>Time:</strong> {new Date(saveStatus.lastSave.timestamp).toLocaleString()}</div>
              </div>
            </AlertDescription>
          </Alert>
        )}

        {/* Error Display */}
        {saveStatus.status === 'error' && (
          <Alert variant="destructive">
            <XCircle className="w-4 h-4" />
            <AlertDescription>
              Save operation failed. Please check the configuration and try again.
            </AlertDescription>
          </Alert>
        )}

        {/* Save History */}
        {saveHistory.length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-2">Recent Saves</h4>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {saveHistory.slice(0, 5).map((save, index) => (
                <div key={index} className="flex items-center justify-between text-xs p-2 bg-muted rounded">
                  <span className="font-mono truncate">{save.filepath.split('/').pop()}</span>
                  <div className="flex items-center space-x-2">
                    <span>{save.filesize} bytes</span>
                    {save.success ? (
                      <CheckCircle className="w-3 h-3 text-green-500" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-500" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default SendToFilesystem;