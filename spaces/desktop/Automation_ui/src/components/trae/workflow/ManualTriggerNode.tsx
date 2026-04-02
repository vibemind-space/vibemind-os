/**
 * Manual Trigger Node Component
 * Interactive trigger node with execution options and visual feedback
 * Enhanced with improved layout consistency
 */

import React, { useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Badge } from '@/components/ui/badge';
import { Play, Loader2, CheckCircle, XCircle, Zap } from 'lucide-react';

interface ManualTriggerData {
  label: string;
  type: string;
  category: string;
  status?: 'idle' | 'running' | 'completed' | 'error';
  config?: {
    button_text?: string;
  };
  lastExecution?: {
    timestamp: string;
    success: boolean;
    duration?: number;
  };
  output?: any;
  outputs?: Array<{
    id: string;
    label: string;
    description?: string;
    type?: string;
    provides?: string;
  }>;
}

interface ManualTriggerNodeProps {
  data: ManualTriggerData;
  id: string;
  selected?: boolean;
}

const ManualTriggerNode: React.FC<ManualTriggerNodeProps> = ({ data, id, selected }) => {
  const [executionType, setExecutionType] = useState<'single' | 'workflow' | null>(null);
  
  const buttonText = data.config?.button_text || 'Execute';
  const isLoading = data.status === 'running';
  const isSuccess = data.status === 'completed';
  const isError = data.status === 'error';

  const handleExecute = () => {
    setExecutionType('single');
    
    // Create execution data
    const executionData = {
      triggered: true,
      timestamp: new Date().toISOString(),
      nodeId: id,
      executionType: 'single'
    };

    // Here we would trigger the actual execution
    // For now, just simulate the execution
    console.log(`Manual trigger executed: single`, executionData);
    
    // This would be connected to the execution engine
    // onExecute?.(executionData, 'single');
  };

  const getNodeStyle = () => {
    if (isLoading) {
      return 'bg-gradient-to-br from-blue-50 to-blue-100 border-2 border-blue-300 shadow-lg shadow-blue-200/30';
    }
    if (isSuccess) {
      return 'bg-gradient-to-br from-green-50 to-emerald-100 border-2 border-green-300 shadow-lg shadow-green-200/30';
    }
    if (isError) {
      return 'bg-gradient-to-br from-red-50 to-red-100 border-2 border-red-300 shadow-lg shadow-red-200/30';
    }
    return 'bg-gradient-to-br from-emerald-50 to-green-100 border-2 border-emerald-300 shadow-lg shadow-emerald-200/30';
  };

  const getButtonIcon = () => {
    if (isLoading) return <Loader2 className="w-4 h-4 animate-spin" />;
    if (isSuccess) return <CheckCircle className="w-4 h-4" />;
    if (isError) return <XCircle className="w-4 h-4" />;
    return <Play className="w-4 h-4" />;
  };

  const getButtonText = () => {
    if (isLoading) return 'Executing...';
    if (isSuccess) return 'Executed';
    if (isError) return 'Failed';
    return buttonText;
  };

  // Get output handles with consistent structure
  const outputHandles = data.outputs || (data.output ? [{ 
    id: 'output', 
    label: 'Output', 
    description: data.output.description,
    type: data.output.type,
    provides: data.output.provides || 'execution_start'
  }] : []);

  // Consistent height calculation
  const nodeHeight = 140; // Fixed height for trigger nodes

  return (
    <div className={`
      relative rounded-xl px-5 py-4 min-w-[240px] max-w-[280px] transition-all duration-300 hover:shadow-xl
      ${getNodeStyle()}
      ${selected ? 'ring-2 ring-blue-500 ring-offset-2 scale-105' : 'hover:scale-102'}
    `} style={{ height: `${nodeHeight}px` }}>
      
      {/* Main Node Content with improved layout */}
      <div className="flex flex-col h-full">
        {/* Header Section */}
        <div className="flex items-center space-x-3 mb-3">
          <div className="flex-shrink-0 p-2.5 bg-white/80 rounded-lg shadow-sm">
            <Play className="w-6 h-6 text-emerald-600" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-gray-800 truncate">{data.label}</div>
            <div className="text-xs text-gray-600 capitalize">trigger</div>
          </div>
          
          {/* Status Badge */}
          {data.status && data.status !== 'idle' && (
            <Badge 
              variant={isSuccess ? 'default' : isError ? 'destructive' : 'secondary'}
              className="text-xs px-2 py-1"
            >
              {data.status}
            </Badge>
          )}
        </div>

        {/* Execute Button Section */}
        <div className="flex-1 flex items-center justify-center">
          <button 
            onClick={handleExecute}
            disabled={isLoading}
            className={`
              flex items-center space-x-2 px-4 py-2 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg font-medium text-white
              ${isLoading ? 'bg-blue-500 cursor-not-allowed' : 
                isSuccess ? 'bg-green-500 hover:bg-green-600' : 
                isError ? 'bg-red-500 hover:bg-red-600' : 
                'bg-emerald-500 hover:bg-emerald-600 hover:scale-105'}
            `}
          >
            {getButtonIcon()}
            <span className="text-sm">{getButtonText()}</span>
          </button>
        </div>

        {/* Last Execution Info */}
        {data.lastExecution && (
          <div className="mt-auto pt-2 border-t border-gray-200">
            <div className="text-xs text-gray-600 bg-white/60 rounded-lg px-3 py-2">
              <div className="flex items-center justify-between mb-1">
                <span>Last executed:</span>
                <span className="font-mono">
                  {new Date(data.lastExecution.timestamp).toLocaleTimeString()}
                </span>
              </div>
              {data.lastExecution.duration && (
                <div className="flex items-center justify-between">
                  <span>Duration:</span>
                  <span className="font-mono">{data.lastExecution.duration}ms</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Output Handles with C4 Architecture styling */}
      {outputHandles.map((output, index) => {
        const topPosition = nodeHeight / 2; // Center position for trigger outputs
        
        return (
          <div key={output.id} className="group absolute" style={{ right: -8, top: topPosition }}>
            <Handle
              id={output.id}
              type="source"
              position={Position.Right}
              className="w-4 h-4 bg-emerald-500 border-2 border-white shadow-lg hover:bg-emerald-600 transition-all duration-200 hover:scale-110"
            >
              {/* Handle icon */}
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-2 h-2 bg-white rounded-full flex items-center justify-center">
                  <Zap className="w-2 h-2 text-emerald-500" />
                </div>
              </div>
            </Handle>
            {/* Improved tooltip with better visibility */}
            <div className="absolute -top-16 left-1/2 transform -translate-x-1/2 text-xs text-gray-700 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-white px-3 py-2 rounded-lg shadow-xl z-50 border border-gray-200 pointer-events-none">
              <div className="font-semibold text-gray-800">{output.label}</div>
              {output.description && (
                <div className="text-gray-600 mt-1">{output.description}</div>
              )}
              <div className="text-xs text-emerald-600 mt-1 font-medium">
                Trigger Connection
              </div>
              {/* Tooltip arrow */}
              <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-white"></div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ManualTriggerNode;