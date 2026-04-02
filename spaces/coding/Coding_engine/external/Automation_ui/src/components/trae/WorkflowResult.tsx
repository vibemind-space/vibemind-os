/**
 * Workflow Result Component
 * 
 * Result node that gathers and aggregates action results from the filesystem
 * Provides data collection, filtering, and export capabilities
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  FileText, 
  Download, 
  Filter, 
  Search, 
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Database,
  BarChart3,
  Settings,
  Trash2,
  Eye,
  Calendar
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FilesystemBridge, WorkflowData, ActionResult } from '@/services/filesystemBridge';

// ============================================================================
// INTERFACES
// ============================================================================

interface ResultFilter {
  nodeType?: string;
  status?: 'pending' | 'processing' | 'completed' | 'failed';
  dateRange?: {
    start: Date;
    end: Date;
  };
  searchTerm?: string;
}

interface ResultAggregation {
  totalResults: number;
  successCount: number;
  failureCount: number;
  pendingCount: number;
  averageExecutionTime: number;
  nodeTypeBreakdown: Record<string, number>;
  statusBreakdown: Record<string, number>;
  timeRangeData: Array<{
    timestamp: number;
    count: number;
  }>;
}

interface ExportConfig {
  format: 'json' | 'csv' | 'xml';
  includeMetadata: boolean;
  dateRange?: {
    start: Date;
    end: Date;
  };
  filterByStatus?: string[];
  filterByNodeType?: string[];
}

interface WorkflowResultProps {
  /** Unique result collector ID */
  resultId?: string;
  /** Filesystem bridge instance */
  filesystemBridge?: FilesystemBridge;
  /** Auto-refresh interval in seconds */
  refreshInterval?: number;
  /** Maximum results to keep in memory */
  maxResults?: number;
  /** Enable real-time monitoring */
  enableRealTimeMonitoring?: boolean;
  /** Workflow data input from connected nodes */
  workflowDataInput?: WorkflowData[];
  /** Action results input from connected action nodes */
  actionResultsInput?: ActionResult[];
  /** Callback for result updates */
  onResultUpdate?: (aggregation: ResultAggregation) => void;
  /** Callback for export completion */
  onExportComplete?: (exportPath: string) => void;
  /** Callback for errors */
  onError?: (error: string) => void;
  /** CSS classes */
  className?: string;
}

// ============================================================================
// DEFAULT CONFIGURATIONS
// ============================================================================

const DEFAULT_EXPORT_CONFIG: ExportConfig = {
  format: 'json',
  includeMetadata: true,
  filterByStatus: ['completed', 'failed'],
  filterByNodeType: []
};

// ============================================================================
// WORKFLOW RESULT COMPONENT
// ============================================================================

export const WorkflowResult: React.FC<WorkflowResultProps> = ({
  resultId = 'workflow-result-collector',
  filesystemBridge,
  refreshInterval = 5,
  maxResults = 1000,
  enableRealTimeMonitoring = true,
  workflowDataInput = [],
  actionResultsInput = [],
  onResultUpdate,
  onExportComplete,
  onError,
  className = ''
}) => {
  // ========================================================================
  // STATE MANAGEMENT
  // ========================================================================

  const [results, setResults] = useState<WorkflowData[]>([]);
  const [filteredResults, setFilteredResults] = useState<WorkflowData[]>([]);
  const [filter, setFilter] = useState<ResultFilter>({});
  const [aggregation, setAggregation] = useState<ResultAggregation>({
    totalResults: 0,
    successCount: 0,
    failureCount: 0,
    pendingCount: 0,
    averageExecutionTime: 0,
    nodeTypeBreakdown: {},
    statusBreakdown: {},
    timeRangeData: []
  });
  
  const [exportConfig, setExportConfig] = useState<ExportConfig>(DEFAULT_EXPORT_CONFIG);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [selectedResult, setSelectedResult] = useState<WorkflowData | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const { toast } = useToast();

  // ========================================================================
  // DATA COLLECTION AND FILTERING
  // ========================================================================

  const collectResults = useCallback(async () => {
    try {
      setIsLoading(true);

      const allResults: WorkflowData[] = [];

      // Process input data from connected nodes
      const inputData: WorkflowData[] = [];

      // Process workflow data input
      if (workflowDataInput && workflowDataInput.length > 0) {
        workflowDataInput.forEach(data => {
          inputData.push({
            ...data,
            metadata: {
            ...data.metadata
            }
          });
        });
      }

      // Process action results input
      if (actionResultsInput && actionResultsInput.length > 0) {
        actionResultsInput.forEach(actionResult => {
          const workflowData: WorkflowData = {
            id: `action_${Date.now()}`,
            timestamp: Date.now(),
            nodeId: 'unknown',
            nodeType: 'action',
            data: actionResult,
            metadata: {
              executionId: `execution_${Date.now()}`,
              workflowId: `workflow_${Date.now()}`,
              status: 'completed' as const
            }
          };
          inputData.push(workflowData);
        });
      }

      allResults.push(...inputData);

      // Collect results from filesystem if bridge is available
      if (filesystemBridge) {
        const nodeTypes = ['click_action', 'type_text_action', 'http_request_action', 'ocr_extract', 'n8n_webhook', 'send_to_filesystem'];
        
        for (const nodeType of nodeTypes) {
          try {
            const nodeResults = await filesystemBridge.readWorkflowData(nodeType, 'action_result');
            allResults.push(...nodeResults);
          } catch (error) {
            console.warn(`Failed to read results for ${nodeType}:`, error);
          }
        }
      }

      // Sort by timestamp (newest first) and limit results
      const sortedResults = allResults
        .sort((a, b) => b.timestamp - a.timestamp)
        .slice(0, maxResults);

      setResults(sortedResults);

      if (onResultUpdate) {
        // Create ResultAggregation object from sorted results
        const successResults = sortedResults.filter(r => r.metadata?.status === 'completed');
        const failedResults = sortedResults.filter(r => r.metadata?.status === 'failed');
        const pendingResults = sortedResults.filter(r => r.metadata?.status === 'pending');
        
        // Calculate node type breakdown
        const nodeTypeBreakdown: Record<string, number> = {};
        sortedResults.forEach(r => {
          nodeTypeBreakdown[r.nodeType] = (nodeTypeBreakdown[r.nodeType] || 0) + 1;
        });

        // Calculate status breakdown
        const statusBreakdown: Record<string, number> = {
          completed: successResults.length,
          failed: failedResults.length,
          pending: pendingResults.length
        };

        // Calculate time range data (group by hour)
        const timeRangeData = sortedResults.reduce((acc, r) => {
          const hourTimestamp = Math.floor(r.timestamp / 3600000) * 3600000;
          const existing = acc.find(item => item.timestamp === hourTimestamp);
          if (existing) {
            existing.count++;
          } else {
            acc.push({ timestamp: hourTimestamp, count: 1 });
          }
          return acc;
        }, [] as Array<{ timestamp: number; count: number }>);

        const aggregation: ResultAggregation = {
          totalResults: sortedResults.length,
          successCount: successResults.length,
          failureCount: failedResults.length,
          pendingCount: pendingResults.length,
          averageExecutionTime: 0, // No execution time data available in WorkflowData
          nodeTypeBreakdown,
          statusBreakdown,
          timeRangeData
        };
        onResultUpdate(aggregation);
      }

      toast({
        title: "Results Updated",
        description: `Collected ${sortedResults.length} workflow results`,
      });

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      
      if (onError) {
        onError(errorMessage);
      }
      
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  }, [filesystemBridge, maxResults, workflowDataInput, actionResultsInput, onResultUpdate, onError, toast]);

  // Filter function for manual filtering (not used in useEffect to avoid loops)
  const applyFiltersToResults = useCallback((sourceResults: WorkflowData[], currentFilter: ResultFilter) => {
    let filtered = [...sourceResults];

    // Filter by node type
    if (currentFilter.nodeType) {
      filtered = filtered.filter(result => result.nodeType === currentFilter.nodeType);
    }

    // Filter by status
    if (currentFilter.status) {
      filtered = filtered.filter(result => result.metadata.status === currentFilter.status);
    }

    // Filter by date range
    if (currentFilter.dateRange) {
      filtered = filtered.filter(result => {
        const resultDate = new Date(result.timestamp);
        return resultDate >= currentFilter.dateRange!.start && resultDate <= currentFilter.dateRange!.end;
      });
    }

    // Filter by search term
    if (currentFilter.searchTerm) {
      const searchLower = currentFilter.searchTerm.toLowerCase();
      filtered = filtered.filter(result => 
        result.nodeId.toLowerCase().includes(searchLower) ||
        result.nodeType.toLowerCase().includes(searchLower) ||
        JSON.stringify(result.data).toLowerCase().includes(searchLower)
      );
    }

    return filtered;
  }, []);

  const calculateAggregation = useCallback((resultsToAggregate: WorkflowData[]) => {
    const agg: ResultAggregation = {
      totalResults: resultsToAggregate.length,
      successCount: 0,
      failureCount: 0,
      pendingCount: 0,
      averageExecutionTime: 0,
      nodeTypeBreakdown: {},
      statusBreakdown: {},
      timeRangeData: []
    };

    let totalExecutionTime = 0;
    let executionTimeCount = 0;

    resultsToAggregate.forEach(result => {
      // Count by status
      const status = result.metadata.status;
      agg.statusBreakdown[status] = (agg.statusBreakdown[status] || 0) + 1;
      
      switch (status) {
        case 'completed': {
          agg.successCount++;
          break;
        }
        case 'failed': {
          agg.failureCount++;
          break;
        }
        case 'pending':
        case 'processing': {
          agg.pendingCount++;
          break;
        }
      }

      // Count by node type
      agg.nodeTypeBreakdown[result.nodeType] = (agg.nodeTypeBreakdown[result.nodeType] || 0) + 1;

      // Calculate execution time if available
      if (result.data && result.data.executionTime) {
        totalExecutionTime += result.data.executionTime;
        executionTimeCount++;
      }
    });

    if (executionTimeCount > 0) {
      agg.averageExecutionTime = totalExecutionTime / executionTimeCount;
    }

    // Generate time range data (hourly buckets for last 24 hours)
    const now = Date.now();
    const hourlyBuckets: Record<number, number> = {};
    
    for (let i = 23; i >= 0; i--) {
      const hourStart = now - (i * 60 * 60 * 1000);
      const hourKey = Math.floor(hourStart / (60 * 60 * 1000));
      hourlyBuckets[hourKey] = 0;
    }

    resultsToAggregate.forEach(result => {
      const hourKey = Math.floor(result.timestamp / (60 * 60 * 1000));
      if (Object.prototype.hasOwnProperty.call(hourlyBuckets, hourKey)) {
        hourlyBuckets[hourKey]++;
      }
    });

    agg.timeRangeData = Object.entries(hourlyBuckets).map(([timestamp, count]) => ({
      timestamp: parseInt(timestamp) * 60 * 60 * 1000,
      count
    }));

    setAggregation(agg);

    if (onResultUpdate) {
      onResultUpdate(agg);
    }
  }, [onResultUpdate]);

  // ========================================================================
  // EXPORT FUNCTIONALITY
  // ========================================================================

  const exportResults = useCallback(async () => {
    try {
      setIsExporting(true);

      let dataToExport = filteredResults;

      // Apply export filters
      if (exportConfig.filterByStatus && exportConfig.filterByStatus.length > 0) {
        dataToExport = dataToExport.filter(result => 
          exportConfig.filterByStatus!.includes(result.metadata.status)
        );
      }

      if (exportConfig.filterByNodeType && exportConfig.filterByNodeType.length > 0) {
        dataToExport = dataToExport.filter(result => 
          exportConfig.filterByNodeType!.includes(result.nodeType)
        );
      }

      if (exportConfig.dateRange) {
        dataToExport = dataToExport.filter(result => {
          const resultDate = new Date(result.timestamp);
          return resultDate >= exportConfig.dateRange!.start && resultDate <= exportConfig.dateRange!.end;
        });
      }

      // Prepare export data
      const exportData = dataToExport.map(result => {
        const baseData = {
          id: result.id,
          timestamp: new Date(result.timestamp).toISOString(),
          nodeId: result.nodeId,
          nodeType: result.nodeType,
          status: result.metadata.status,
          data: result.data
        };

        if (exportConfig.includeMetadata) {
          return {
            ...baseData,
            metadata: result.metadata
          };
        }

        return baseData;
      });

      // Generate export content based on format
      let exportContent: string;
      let fileName: string;

      switch (exportConfig.format) {
        case 'json':
          exportContent = JSON.stringify(exportData, null, 2);
          fileName = `workflow-results-${Date.now()}.json`;
          break;
        
        case 'csv': {
          const headers = Object.keys(exportData[0] || {});
          const csvRows = [
            headers.join(','),
            ...exportData.map(row => 
              headers.map(header => {
                const value = (row as any)[header];
                return typeof value === 'object' ? JSON.stringify(value) : value;
              }).join(',')
            )
          ];
          exportContent = csvRows.join('\n');
          fileName = `workflow-results-${Date.now()}.csv`;
          break;
        }
        
        case 'xml':
          exportContent = `<?xml version="1.0" encoding="UTF-8"?>
<workflowResults>
${exportData.map(result => `
  <result>
    <id>${result.id}</id>
    <timestamp>${result.timestamp}</timestamp>
    <nodeId>${result.nodeId}</nodeId>
    <nodeType>${result.nodeType}</nodeType>
    <status>${result.status}</status>
    <data>${JSON.stringify(result.data)}</data>
    ${exportConfig.includeMetadata ? `<metadata>${JSON.stringify((result as any).metadata)}</metadata>` : ''}
  </result>`, '').join('')}
</workflowResults>`;
          fileName = `workflow-results-${Date.now()}.xml`;
          break;
        
        default:
          throw new Error(`Unsupported export format: ${exportConfig.format}`);
      }

      // In a real implementation, you would write to the filesystem
      // For now, we'll create a download blob
      const blob = new Blob([exportContent], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: "Export Complete",
        description: `Exported ${exportData.length} results to ${fileName}`,
      });

      if (onExportComplete) {
        onExportComplete(fileName);
      }

    } catch (error) {
      const errorMessage = `Export failed: ${error}`;
      toast({
        title: "Export Error",
        description: errorMessage,
        variant: "destructive"
      });

      if (onError) {
        onError(errorMessage);
      }
    } finally {
      setIsExporting(false);
    }
  }, [filteredResults, exportConfig, onExportComplete, onError]);

  // ========================================================================
  // LIFECYCLE EFFECTS
  // ========================================================================

  // Apply filters when filter changes - using stable function to avoid loops
  useEffect(() => {
    const filtered = applyFiltersToResults(results, filter);
    setFilteredResults(filtered);
    calculateAggregation(filtered);
  }, [filter, results, applyFiltersToResults, calculateAggregation]);

  // Set up refresh interval for real-time monitoring
  useEffect(() => {
    if (enableRealTimeMonitoring && refreshInterval > 0) {
      const intervalId = setInterval(() => {
        collectResults();
      }, refreshInterval * 1000);
      refreshIntervalRef.current = intervalId;

      return () => {
        if (refreshIntervalRef.current) {
          clearInterval(refreshIntervalRef.current);
        }
      };
    }
  }, [enableRealTimeMonitoring, refreshInterval, collectResults]);

  // Initial data collection on mount and when key dependencies change
  useEffect(() => {
    collectResults();
  }, [filesystemBridge, workflowDataInput, actionResultsInput]);

  // ========================================================================
  // RENDER COMPONENT
  // ========================================================================

  return (
    <div className={`workflow-result ${className}`}>
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Workflow Results
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant="outline">
                {aggregation.totalResults} Total
              </Badge>
              <Badge variant="default">
                {aggregation.successCount} Success
              </Badge>
              <Badge variant="destructive">
                {aggregation.failureCount} Failed
              </Badge>
              <Button
                onClick={collectResults}
                disabled={isLoading}
                size="sm"
                variant="outline"
              >
                {isLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="results">Results</TabsTrigger>
              <TabsTrigger value="analytics">Analytics</TabsTrigger>
              <TabsTrigger value="export">Export</TabsTrigger>
            </TabsList>

            {/* Overview Tab */}
            <TabsContent value="overview" className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      <div>
                        <p className="text-sm font-medium">Success Rate</p>
                        <p className="text-2xl font-bold">
                          {aggregation.totalResults > 0 
                            ? Math.round((aggregation.successCount / aggregation.totalResults) * 100)
                            : 0
                          }%
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-blue-500" />
                      <div>
                        <p className="text-sm font-medium">Avg. Execution</p>
                        <p className="text-2xl font-bold">
                          {Math.round(aggregation.averageExecutionTime)}ms
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-purple-500" />
                      <div>
                        <p className="text-sm font-medium">Node Types</p>
                        <p className="text-2xl font-bold">
                          {Object.keys(aggregation.nodeTypeBreakdown).length}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4 text-orange-500" />
                      <div>
                        <p className="text-sm font-medium">Last 24h</p>
                        <p className="text-2xl font-bold">
                          {aggregation.timeRangeData.reduce((sum, bucket) => sum + bucket.count, 0)}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Quick Filters */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Quick Filters</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <Label htmlFor="search">Search</Label>
                      <Input
                        id="search"
                        placeholder="Search results..."
                        value={filter.searchTerm || ''}
                        onChange={(e) => setFilter(prev => ({ ...prev, searchTerm: e.target.value }))}
                      />
                    </div>
                    
                    <div>
                      <Label htmlFor="node-type">Node Type</Label>
                      <Select
                        value={filter.nodeType || 'all-types'}
                        onValueChange={(value) => setFilter(prev => ({ ...prev, nodeType: value === 'all-types' ? undefined : value }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="All types" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all-types">All types</SelectItem>
                          {Object.keys(aggregation.nodeTypeBreakdown).map(type => (
                            <SelectItem key={type} value={type}>{type}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label htmlFor="status">Status</Label>
                      <Select
                        value={filter.status || 'all-statuses'}
                        onValueChange={(value) => setFilter(prev => ({ ...prev, status: value === 'all-statuses' ? undefined : value as any }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="All statuses" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all-statuses">All statuses</SelectItem>
                          <SelectItem value="completed">Completed</SelectItem>
                          <SelectItem value="failed">Failed</SelectItem>
                          <SelectItem value="pending">Pending</SelectItem>
                          <SelectItem value="processing">Processing</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex items-end">
                      <Button
                        onClick={() => setFilter({})}
                        variant="outline"
                        size="sm"
                        className="w-full"
                      >
                        Clear Filters
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Results Tab */}
            <TabsContent value="results" className="space-y-4">
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {filteredResults.map((result, index) => (
                  <Card key={index} className="cursor-pointer hover:bg-muted/50" onClick={() => {
                    setSelectedResult(result);
                    setShowDetailModal(true);
                  }}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <Badge variant={
                            result.metadata.status === 'completed' ? 'default' :
                            result.metadata.status === 'failed' ? 'destructive' :
                            'secondary'
                          }>
                            {result.metadata.status === 'completed' && <CheckCircle className="h-3 w-3 mr-1" />}
                            {result.metadata.status === 'failed' && <XCircle className="h-3 w-3 mr-1" />}
                            {result.metadata.status === 'pending' && <Clock className="h-3 w-3 mr-1" />}
                            {result.metadata.status}
                          </Badge>
                          <div>
                            <p className="font-medium">{result.nodeId}</p>
                            <p className="text-sm text-muted-foreground">{result.nodeType}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm">{new Date(result.timestamp).toLocaleString()}</p>
                          {result.data?.executionTime && (
                            <p className="text-xs text-muted-foreground">{result.data.executionTime}ms</p>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>

            {/* Analytics Tab */}
            <TabsContent value="analytics" className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Node Type Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {Object.entries(aggregation.nodeTypeBreakdown).map(([type, count]) => (
                        <div key={type} className="flex justify-between items-center">
                          <span className="text-sm">{type}</span>
                          <Badge variant="outline">{count}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Status Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {Object.entries(aggregation.statusBreakdown).map(([status, count]) => (
                        <div key={status} className="flex justify-between items-center">
                          <span className="text-sm capitalize">{status}</span>
                          <Badge variant={
                            status === 'completed' ? 'default' :
                            status === 'failed' ? 'destructive' :
                            'secondary'
                          }>{count}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* Export Tab */}
            <TabsContent value="export" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Export Configuration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="export-format">Format</Label>
                      <Select
                        value={exportConfig.format}
                        onValueChange={(value) => setExportConfig(prev => ({ ...prev, format: value as any }))}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="json">JSON</SelectItem>
                          <SelectItem value="csv">CSV</SelectItem>
                          <SelectItem value="xml">XML</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex items-center space-x-2 pt-6">
                      <Switch
                        id="include-metadata"
                        checked={exportConfig.includeMetadata}
                        onCheckedChange={(checked) => setExportConfig(prev => ({ ...prev, includeMetadata: checked }))}
                      />
                      <Label htmlFor="include-metadata">Include Metadata</Label>
                    </div>
                  </div>

                  <Button
                    onClick={exportResults}
                    disabled={isExporting || filteredResults.length === 0}
                    className="w-full"
                  >
                    {isExporting ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4 mr-2" />
                    )}
                    Export {filteredResults.length} Results
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Result Detail Modal */}
      {showDetailModal && selectedResult && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Result Details</CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowDetailModal(false)}
                >
                  ×
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <pre className="text-sm bg-muted p-4 rounded overflow-x-auto">
                {JSON.stringify(selectedResult, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default WorkflowResult;