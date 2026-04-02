
/**
 * Simplified Node Templates - n8n Style
 * Each node has exactly 1 input and 1 output (except config nodes)
 */

import { NodeInputSpec, NodeOutputSpec, NodeDependency } from '../types/dataFlow';
import { WEBSOCKET_CONFIG } from './websocketConfig';

export interface SimplifiedNodeTemplate {
  id: string;
  type: string;
  label: string;
  description: string;
  category: 'triggers' | 'actions' | 'logic' | 'config' | 'interface' | 'results';
  icon: string;
  color: string;
  
  // Enhanced I/O for new architecture
  input?: NodeInputSpec;
  output?: NodeOutputSpec;
  
  // Multiple inputs for interface and result nodes
  inputs?: NodeInputSpec[];
  outputs?: NodeOutputSpec[];
  
  // Dependencies (config nodes, services)
  dependencies: NodeDependency[];
  
  // Configuration schema
  configSchema: Record<string, any>;
  defaultConfig: Record<string, any>;
  
  // Filesystem integration
  filesystemConfig?: {
    dataPath: string;
    watchFiles: boolean;
    outputFormat: 'json' | 'xml' | 'csv';
  };
}

export const SIMPLIFIED_NODE_TEMPLATES: Record<string, SimplifiedNodeTemplate> = {
  // TRIGGER NODES
  manual_trigger: {
    id: 'manual_trigger',
    type: 'manual_trigger',
    label: 'Manual Trigger',
    description: 'Start workflow manually',
    category: 'triggers',
    icon: 'Play',
    color: '#10b981',
    // No input for triggers
    outputs: [
      {
        id: 'trigger_output',
        name: 'Trigger',
        type: 'trigger',
        provides: 'execution_start',
        description: 'Workflow execution trigger'
      }
    ],
    dependencies: [],
    configSchema: {
      button_text: { type: 'string', default: 'Start Workflow', label: 'Button Text' }
    },
    defaultConfig: { button_text: 'Start Workflow' }
  },
  
  webhook_trigger: {
    id: 'webhook_trigger',
    type: 'webhook_trigger',
    label: 'Webhook',
    description: 'Trigger via HTTP webhook',
    category: 'triggers',
    icon: 'Webhook',
    color: '#3b82f6',
    outputs: [
      {
        id: 'webhook_output',
        name: 'Webhook Data',
        type: 'data',
        provides: 'webhook_payload',
        description: 'HTTP request data'
      }
    ],
    dependencies: [],
    configSchema: {
      path: { type: 'string', required: true, label: 'Webhook Path' },
      method: { type: 'select', options: ['POST', 'GET'], default: 'POST' },
      execution_history: { type: 'array', default: [], hidden: true }
    },
    defaultConfig: { 
      path: '/webhook', 
      method: 'POST',
      execution_history: []
    }
  },
  
  // CONFIG NODES (connect to interface nodes)
  websocket_config: {
    id: 'websocket_config',
    type: 'websocket_config',
    label: 'WebSocket Config',
    description: 'WebSocket service configuration and filesystem bridge',
    category: 'config',
    icon: 'Wifi',
    color: '#8b5cf6',
    // Config nodes output connection info to interface nodes
    outputs: [
      {
        id: 'websocket_output',
        name: 'WebSocket Connection',
        type: 'config',
        provides: 'websocket_connection',
        description: 'WebSocket connection with filesystem bridge'
      }
    ],
    dependencies: [],
    configSchema: {
      url: { type: 'string', required: true, label: 'WebSocket URL' },
      port: { type: 'number', default: 8080, label: 'Port' },
      reconnect: { type: 'boolean', default: true, label: 'Auto Reconnect' },
      service_command: { type: 'string', label: 'Service Start Command' },
      auto_start: { type: 'boolean', default: false, label: 'Auto Start Service' },
      health_check_url: { type: 'string', label: 'Health Check URL' },
      process_id: { type: 'number', label: 'Process ID (auto-filled)' },
      status: { type: 'select', options: ['stopped', 'starting', 'running', 'failed'], default: 'stopped' },
      // Filesystem integration settings
      filesystem_bridge: { type: 'boolean', default: true, label: 'Enable Filesystem Bridge' },
      data_directory: { type: 'string', default: './workflow-data', label: 'Data Directory' },
      file_format: { type: 'select', options: ['json', 'xml', 'csv'], default: 'json', label: 'File Format' },
      watch_interval: { type: 'number', default: 1000, min: 100, label: 'File Watch Interval (ms)' }
    },
    defaultConfig: { 
      url: WEBSOCKET_CONFIG.BASE_URL, 
      port: 8080,
      reconnect: true,
      service_command: 'node websocket-server.js',
      auto_start: false,
      status: 'stopped',
      filesystem_bridge: true,
      data_directory: './workflow-data',
      file_format: 'json',
      watch_interval: 1000
    },
    filesystemConfig: {
      dataPath: './workflow-data/websocket',
      watchFiles: true,
      outputFormat: 'json'
    }
  },
  
  // INTERFACE NODES (central connection hubs)
  live_desktop: {
    id: 'live_desktop',
    type: 'live_desktop',
    label: 'Live Desktop Interface',
    description: 'Central desktop interface hub - connects config, triggers, and actions',
    category: 'interface',
    icon: 'Monitor',
    color: '#64748b',
    // Interface nodes accept multiple input types
    inputs: [
      {
        id: 'config_input',
        name: 'WebSocket Config',
        type: 'config',
        required: true,
        accepts: ['websocket_connection'],
        description: 'WebSocket service configuration',
        placeholder: 'Connect WebSocket config'
      },
      {
        id: 'trigger_input',
        name: 'Trigger',
        type: 'trigger',
        required: true,
        accepts: ['execution_start', 'webhook_payload'],
        description: 'Workflow trigger input',
        placeholder: 'Connect trigger'
      },
      {
        id: 'action_input',
        name: 'Action Commands',
        type: 'data',
        required: false,
        accepts: ['click_result', 'type_result', 'http_response', 'extracted_text'],
        description: 'Action commands to execute',
        placeholder: 'Connect action nodes'
      }
    ],
    // Interface nodes provide multiple outputs
    outputs: [
      {
        id: 'desktop_stream_output',
        name: 'Desktop Stream',
        type: 'data',
        provides: 'desktop_stream',
        description: 'Live desktop stream data'
      },
      {
        id: 'interface_status_output',
        name: 'Interface Status',
        type: 'data',
        provides: 'interface_status',
        description: 'Interface connection and health status'
      },
      {
        id: 'filesystem_output',
        name: 'Filesystem Bridge',
        type: 'data',
        provides: 'filesystem_bridge',
        description: 'Filesystem data bridge for actions'
      }
    ],
    dependencies: [],
    configSchema: {
      fps: { type: 'number', default: 30, min: 1, max: 60, label: 'FPS' },
      quality: { type: 'number', default: 80, min: 10, max: 100, label: 'Quality %' },
      width: { type: 'number', default: 1200, label: 'Width' },
      height: { type: 'number', default: 900, label: 'Height' },
      // Filesystem integration
      enable_filesystem: { type: 'boolean', default: true, label: 'Enable Filesystem Bridge' },
      data_output_path: { type: 'string', default: './workflow-data/desktop', label: 'Data Output Path' },
      action_queue_path: { type: 'string', default: './workflow-data/actions', label: 'Action Queue Path' },
      result_collection_path: { type: 'string', default: './workflow-data/results', label: 'Result Collection Path' },
      auto_cleanup: { type: 'boolean', default: true, label: 'Auto Cleanup Old Files' },
      max_file_age: { type: 'number', default: 3600000, label: 'Max File Age (ms)' }
    },
    defaultConfig: { 
      fps: 30, 
      quality: 80, 
      width: 1200, 
      height: 900,
      enable_filesystem: true,
      data_output_path: './workflow-data/desktop',
      action_queue_path: './workflow-data/actions',
      result_collection_path: './workflow-data/results',
      auto_cleanup: true,
      max_file_age: 3600000
    },
    filesystemConfig: {
      dataPath: './workflow-data/desktop',
      watchFiles: true,
      outputFormat: 'json'
    }
  },
  
  // ACTION NODES (connect to interface and write to filesystem)
  click_action: {
    id: 'click_action',
    type: 'click_action',
    label: 'Click Action',
    description: 'Perform mouse click via filesystem bridge',
    category: 'actions',
    icon: 'MousePointer',
    color: '#f97316',
    input: {
      id: 'click_input',
      name: 'Interface Bridge',
      type: 'data',
      required: true,
      accepts: ['desktop_stream', 'filesystem_bridge', 'interface_status'],
      description: 'Connect from Live Desktop Interface',
      placeholder: 'Connect interface bridge'
    },
    outputs: [
      {
        id: 'click_output',
        name: 'Click Command',
        type: 'data',
        provides: 'click_result',
        description: 'Click action command for filesystem'
      }
    ],
    dependencies: [],
    configSchema: {
      x: { type: 'number', required: true, label: 'X Coordinate' },
      y: { type: 'number', required: true, label: 'Y Coordinate' },
      button: { type: 'select', options: ['left', 'right', 'middle'], default: 'left' },
      // Filesystem integration
      output_to_filesystem: { type: 'boolean', default: true, label: 'Output to Filesystem' },
      command_file: { type: 'string', default: 'click_command.json', label: 'Command Filename' },
      wait_for_execution: { type: 'boolean', default: true, label: 'Wait for Execution' },
      execution_timeout: { type: 'number', default: 5000, label: 'Execution Timeout (ms)' }
    },
    defaultConfig: { 
      x: 0, 
      y: 0, 
      button: 'left',
      output_to_filesystem: true,
      command_file: 'click_command.json',
      wait_for_execution: true,
      execution_timeout: 5000
    },
    filesystemConfig: {
      dataPath: './workflow-data/actions/click',
      watchFiles: true,
      outputFormat: 'json'
    }
  },
  
  type_text_action: {
    id: 'type_text_action',
    type: 'type_text_action',
    label: 'Type Text Action',
    description: 'Type text via filesystem bridge',
    category: 'actions',
    icon: 'Keyboard',
    color: '#8b5cf6',
    input: {
      id: 'type_input',
      name: 'Interface Bridge',
      type: 'data',
      required: true,
      accepts: ['filesystem_bridge', 'click_result', 'interface_status'],
      description: 'Connect from interface or previous action',
      placeholder: 'Connect interface bridge'
    },
    outputs: [
      {
        id: 'type_output',
        name: 'Type Command',
        type: 'data',
        provides: 'type_result',
        description: 'Text typing command for filesystem'
      }
    ],
    dependencies: [],
    configSchema: {
      text: { type: 'string', required: true, label: 'Text to Type' },
      delay: { type: 'number', default: 100, min: 0, label: 'Delay (ms)' },
      // Filesystem integration
      output_to_filesystem: { type: 'boolean', default: true, label: 'Output to Filesystem' },
      command_file: { type: 'string', default: 'type_command.json', label: 'Command Filename' },
      wait_for_execution: { type: 'boolean', default: true, label: 'Wait for Execution' },
      execution_timeout: { type: 'number', default: 5000, label: 'Execution Timeout (ms)' }
    },
    defaultConfig: { 
      text: '', 
      delay: 100,
      output_to_filesystem: true,
      command_file: 'type_command.json',
      wait_for_execution: true,
      execution_timeout: 5000
    },
    filesystemConfig: {
      dataPath: './workflow-data/actions/type',
      watchFiles: true,
      outputFormat: 'json'
    }
  },
  
  http_request_action: {
    id: 'http_request_action',
    type: 'http_request_action',
    label: 'HTTP Request',
    description: 'Make HTTP request',
    category: 'actions',
    icon: 'Globe',
    color: '#ef4444',
    input: {
      id: 'http_input',
      name: 'Data',
      type: 'data',
      required: true,
      accepts: ['type_result', 'click_result', 'webhook_payload'],
      description: 'Connect data to send',
      placeholder: 'Connect data source'
    },
    outputs: [
      {
        id: 'http_output',
        name: 'Response',
        type: 'data',
        provides: 'http_response',
        description: 'HTTP response data'
      }
    ],
    dependencies: [],
    configSchema: {
      url: { type: 'string', required: true, label: 'URL' },
      method: { type: 'select', options: ['GET', 'POST', 'PUT', 'DELETE'], default: 'POST' },
      headers: { type: 'object', default: {}, label: 'Headers' }
    },
    defaultConfig: { url: '', method: 'POST', headers: {} }
  },
  
  // LOGIC NODES
  if_condition: {
    id: 'if_condition',
    type: 'if_condition',
    label: 'IF Condition',
    description: 'Conditional logic branch',
    category: 'logic',
    icon: 'GitBranch',
    color: '#06b6d4',
    input: {
      id: 'condition_input',
      name: 'Data',
      type: 'data',
      required: true,
      accepts: ['http_response', 'click_result', 'type_result'],
      description: 'Data to evaluate',
      placeholder: 'Connect data to check'
    },
    outputs: [
      {
        id: 'condition_output',
        name: 'Result',
        type: 'data',
        provides: 'condition_result',
        description: 'Condition evaluation result'
      }
    ],
    dependencies: [],
    configSchema: {
      condition: { type: 'string', required: true, label: 'Condition' },
      operator: { type: 'select', options: ['equals', 'contains', 'greater', 'less'], default: 'equals' }
    },
    defaultConfig: { condition: '', operator: 'equals' }
  },
  
  delay: {
    id: 'delay',
    type: 'delay',
    label: 'Delay',
    description: 'Wait for specified time',
    category: 'logic',
    icon: 'Timer',
    color: '#eab308',
    input: {
      id: 'delay_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['click_result', 'type_result', 'condition_result'],
      description: 'Previous action result',
      placeholder: 'Connect previous action'
    },
    outputs: [
      {
        id: 'delay_output',
        name: 'Continue',
        type: 'data',
        provides: 'delay_complete',
        description: 'Delay completion signal'
      }
    ],
    dependencies: [],
    configSchema: {
      duration: { type: 'number', required: true, min: 100, label: 'Duration (ms)' }
    },
    defaultConfig: { duration: 1000 }
  },

  // OCR NODES
  ocr_region: {
    id: 'ocr_region',
    type: 'ocr_region',
    label: 'OCR Region',
    description: 'Define text extraction region on desktop',
    category: 'actions',
    icon: 'ScanText',
    color: '#9333ea',
    input: {
      id: 'ocr_region_input',
      name: 'Desktop Stream',
      type: 'data',
      required: true,
      accepts: ['desktop_stream'],
      description: 'Connect from Live Desktop',
      placeholder: 'Connect desktop stream'
    },
    outputs: [
      {
        id: 'ocr_region_output',
        name: 'OCR Region',
        type: 'data',
        provides: 'ocr_region_data',
        description: 'OCR region configuration'
      }
    ],
    dependencies: [],
    configSchema: {
      x: { type: 'number', required: true, label: 'X Position' },
      y: { type: 'number', required: true, label: 'Y Position' },
      width: { type: 'number', required: true, label: 'Width' },
      height: { type: 'number', required: true, label: 'Height' },
      label: { type: 'string', default: 'Region 1', label: 'Region Label' },
      enabled: { type: 'boolean', default: true, label: 'Enabled' }
    },
    defaultConfig: { x: 100, y: 100, width: 200, height: 50, label: 'Region 1', enabled: true }
  },

  ocr_extract: {
    id: 'ocr_extract',
    type: 'ocr_extract',
    label: 'OCR Extract',
    description: 'Extract text from defined regions',
    category: 'actions',
    icon: 'FileText',
    color: '#dc2626',
    input: {
      id: 'ocr_extract_input',
      name: 'OCR Region',
      type: 'data',
      required: true,
      accepts: ['ocr_region_data'],
      description: 'Connect from OCR Region',
      placeholder: 'Connect OCR region'
    },
    outputs: [
      {
        id: 'ocr_extract_output',
        name: 'Extracted Text',
        type: 'data',
        provides: 'extracted_text',
        description: 'Extracted text data'
      }
    ],
    dependencies: [],
    configSchema: {
      interval: { type: 'number', default: 240000, min: 10000, label: 'Extraction Interval (ms)' },
      confidence_threshold: { type: 'number', default: 0.7, min: 0, max: 1, label: 'Confidence Threshold' },
      auto_start: { type: 'boolean', default: true, label: 'Auto Start Extraction' },
      preprocessing: { 
        type: 'select', 
        options: ['none', 'grayscale', 'threshold', 'blur'], 
        default: 'grayscale',
        label: 'Image Preprocessing'
      }
    },
    defaultConfig: { 
      interval: 240000, // 4 minutes
      confidence_threshold: 0.7,
      auto_start: true,
      preprocessing: 'grayscale'
    }
  },

  n8n_webhook: {
    id: 'n8n_webhook',
    type: 'n8n_webhook',
    label: 'N8N Webhook',
    description: 'Send data to N8N for interpretation',
    category: 'actions',
    icon: 'Webhook',
    color: '#ea580c',
    input: {
      id: 'n8n_input',
      name: 'Text Data',
      type: 'data',
      required: true,
      accepts: ['extracted_text'],
      description: 'Connect extracted text',
      placeholder: 'Connect extracted text'
    },
    outputs: [
      {
        id: 'n8n_output',
        name: 'N8N Response',
        type: 'data',
        provides: 'n8n_response',
        description: 'N8N interpretation response'
      }
    ],
    dependencies: [],
    configSchema: {
      webhook_url: { type: 'string', required: true, label: 'N8N Webhook URL' },
      api_key: { type: 'string', label: 'API Key (optional)' },
      timeout: { type: 'number', default: 30000, label: 'Timeout (ms)' },
      retry_attempts: { type: 'number', default: 3, min: 1, max: 10, label: 'Retry Attempts' },
      data_format: {
        type: 'select',
        options: ['json', 'form-data', 'raw'],
        default: 'json',
        label: 'Data Format'
      }
    },
    defaultConfig: { 
      webhook_url: '',
      timeout: 30000,
      retry_attempts: 3,
      data_format: 'json'
    }
  },



  // FILESYSTEM ACTION NODES (send data to filesystem)
  send_to_filesystem: {
    id: 'send_to_filesystem',
    type: 'send_to_filesystem',
    label: 'Send to Filesystem',
    description: 'Send workflow data and results to filesystem storage',
    category: 'actions',
    icon: 'Save',
    color: '#0ea5e9',
    input: {
      id: 'data_input',
      name: 'Data to Send',
      type: 'data',
      required: true,
      accepts: ['click_result', 'type_result', 'http_response', 'extracted_text', 'n8n_response', 'workflow_results'],
      description: 'Connect any workflow data to send to filesystem',
      placeholder: 'Connect data to save'
    },
    outputs: [
      {
        id: 'filesystem_output',
        name: 'Filesystem Result',
        type: 'data',
        provides: 'filesystem_save_result',
        description: 'Filesystem save operation result'
      }
    ],
    dependencies: [],
    configSchema: {
      // File output settings
      output_directory: { type: 'string', default: './workflow-data/output', label: 'Output Directory' },
      filename_template: { type: 'string', default: 'data_{timestamp}_{type}', label: 'Filename Template' },
      file_format: { type: 'select', options: ['json', 'xml', 'csv', 'txt'], default: 'json', label: 'File Format' },
      // Data processing
      include_metadata: { type: 'boolean', default: true, label: 'Include Metadata' },
      include_timestamp: { type: 'boolean', default: true, label: 'Include Timestamp' },
      compress_data: { type: 'boolean', default: false, label: 'Compress Data' },
      // Filesystem behavior
      overwrite_existing: { type: 'boolean', default: false, label: 'Overwrite Existing Files' },
      create_backup: { type: 'boolean', default: true, label: 'Create Backup Before Overwrite' },
      auto_create_directories: { type: 'boolean', default: true, label: 'Auto Create Directories' },
      // Validation and error handling
      validate_data: { type: 'boolean', default: true, label: 'Validate Data Before Save' },
      retry_on_error: { type: 'boolean', default: true, label: 'Retry on Error' },
      max_retry_attempts: { type: 'number', default: 3, min: 1, max: 10, label: 'Max Retry Attempts' },
      // Notification settings
      notify_on_success: { type: 'boolean', default: false, label: 'Notify on Success' },
      notify_on_error: { type: 'boolean', default: true, label: 'Notify on Error' },
      webhook_notification: { type: 'string', default: '', label: 'Webhook URL for Notifications' }
    },
    defaultConfig: { 
      output_directory: './workflow-data/output',
      filename_template: 'data_{timestamp}_{type}',
      file_format: 'json',
      include_metadata: true,
      include_timestamp: true,
      compress_data: false,
      overwrite_existing: false,
      create_backup: true,
      auto_create_directories: true,
      validate_data: true,
      retry_on_error: true,
      max_retry_attempts: 3,
      notify_on_success: false,
      notify_on_error: true,
      webhook_notification: ''
    },
    filesystemConfig: {
      dataPath: './workflow-data/output',
      watchFiles: false, // This node writes, doesn't watch
      outputFormat: 'json'
    }
  },



  // RESULT NODES (gather action results from filesystem)
  workflow_result: {
    id: 'workflow_result',
    type: 'workflow_result',
    label: 'Workflow Results',
    description: 'Gather and aggregate action results from filesystem',
    category: 'results',
    icon: 'Database',
    color: '#059669',
    // Result nodes accept multiple action outputs and workflow data
    inputs: [
      {
        id: 'action_results_input',
        name: 'Action Results',
        type: 'data',
        required: false,
        accepts: ['click_result', 'type_result', 'http_response', 'extracted_text', 'n8n_response', 'filesystem_save_result'],
        description: 'Connect action node outputs',
        placeholder: 'Connect action results'
      },
      {
        id: 'workflow_data_input',
        name: 'Workflow Data',
        type: 'data',
        required: false,
        accepts: ['workflow_data', 'processed_data', 'user_input', 'external_data', 'config_data'],
        description: 'Connect any workflow data for processing',
        placeholder: 'Connect workflow data'
      },
      {
        id: 'filesystem_input',
        name: 'Filesystem Bridge',
        type: 'data',
        required: true,
        accepts: ['filesystem_bridge'],
        description: 'Connect filesystem bridge from interface',
        placeholder: 'Connect filesystem bridge'
      }
    ],
    outputs: [
      {
        id: 'aggregated_results_output',
        name: 'Aggregated Results',
        type: 'data',
        provides: 'workflow_results',
        description: 'Aggregated workflow execution results'
      }
    ],
    dependencies: [],
    configSchema: {
      // Result collection settings
      collect_all_results: { type: 'boolean', default: true, label: 'Collect All Results' },
      result_format: { type: 'select', options: ['json', 'xml', 'csv'], default: 'json', label: 'Result Format' },
      include_timestamps: { type: 'boolean', default: true, label: 'Include Timestamps' },
      include_metadata: { type: 'boolean', default: true, label: 'Include Metadata' },
      // Filesystem monitoring
      watch_filesystem: { type: 'boolean', default: true, label: 'Watch Filesystem for Results' },
      result_directory: { type: 'string', default: './workflow-data/results', label: 'Result Directory' },
      auto_aggregate: { type: 'boolean', default: true, label: 'Auto Aggregate Results' },
      aggregation_interval: { type: 'number', default: 2000, min: 500, label: 'Aggregation Interval (ms)' },
      // Export settings
      export_results: { type: 'boolean', default: false, label: 'Export Results' },
      export_path: { type: 'string', default: './exports', label: 'Export Path' },
      max_results_history: { type: 'number', default: 100, min: 10, label: 'Max Results History' }
    },
    defaultConfig: { 
      collect_all_results: true,
      result_format: 'json',
      include_timestamps: true,
      include_metadata: true,
      watch_filesystem: true,
      result_directory: './workflow-data/results',
      auto_aggregate: true,
      aggregation_interval: 2000,
      export_results: false,
      export_path: './exports',
      max_results_history: 100
    },
    filesystemConfig: {
      dataPath: './workflow-data/results',
      watchFiles: true,
      outputFormat: 'json'
    }
  },

  // ============= MCP HANDOFF NODES =============
  // Integration with Moire MCP Tools via VibeMind Bridge

  mcp_click: {
    id: 'mcp_click',
    type: 'mcp_click',
    label: 'MCP Click',
    description: 'Click action via MCP Handoff Tools',
    category: 'actions',
    icon: 'MousePointer2',
    color: '#f97316',
    input: {
      id: 'mcp_click_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'delay_complete', 'condition_result'],
      description: 'Connect trigger or previous MCP action',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_click_output',
        name: 'Click Result',
        type: 'data',
        provides: 'mcp_result',
        description: 'MCP click action result'
      }
    ],
    dependencies: [],
    configSchema: {
      x: { type: 'number', required: true, label: 'X Position' },
      y: { type: 'number', required: true, label: 'Y Position' },
      button: { type: 'select', options: ['left', 'right', 'middle'], default: 'left', label: 'Mouse Button' },
      use_element_finder: { type: 'boolean', default: false, label: 'Use Element Finder' },
      element_text: { type: 'string', label: 'Element Text (if finder enabled)' }
    },
    defaultConfig: {
      x: 0,
      y: 0,
      button: 'left',
      use_element_finder: false,
      element_text: ''
    }
  },

  mcp_type: {
    id: 'mcp_type',
    type: 'mcp_type',
    label: 'MCP Type',
    description: 'Type text via MCP Handoff Tools',
    category: 'actions',
    icon: 'Keyboard',
    color: '#8b5cf6',
    input: {
      id: 'mcp_type_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'delay_complete'],
      description: 'Connect trigger or previous action',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_type_output',
        name: 'Type Result',
        type: 'data',
        provides: 'mcp_result',
        description: 'MCP type action result'
      }
    ],
    dependencies: [],
    configSchema: {
      text: { type: 'string', required: true, label: 'Text to Type' },
      interval: { type: 'number', default: 0, min: 0, label: 'Interval between chars (ms)' },
      clear_first: { type: 'boolean', default: false, label: 'Clear field first' }
    },
    defaultConfig: {
      text: '',
      interval: 0,
      clear_first: false
    }
  },

  mcp_shell: {
    id: 'mcp_shell',
    type: 'mcp_shell',
    label: 'MCP Shell',
    description: 'Execute shell command via MCP Handoff',
    category: 'actions',
    icon: 'Terminal',
    color: '#22c55e',
    input: {
      id: 'mcp_shell_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'delay_complete', 'condition_result'],
      description: 'Connect trigger or previous action',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_shell_output',
        name: 'Shell Result',
        type: 'data',
        provides: 'mcp_shell_result',
        description: 'Shell command output (stdout, stderr, exit_code)'
      }
    ],
    dependencies: [],
    configSchema: {
      command: { type: 'string', required: true, label: 'Command' },
      timeout: { type: 'number', default: 30, min: 1, max: 600, label: 'Timeout (seconds)' },
      shell: { type: 'select', options: ['auto', 'powershell', 'cmd', 'bash'], default: 'auto', label: 'Shell Type' }
    },
    defaultConfig: {
      command: '',
      timeout: 30,
      shell: 'auto'
    }
  },

  mcp_find_element: {
    id: 'mcp_find_element',
    type: 'mcp_find_element',
    label: 'MCP Find Element',
    description: 'Find UI element by text or type via OCR + CNN',
    category: 'actions',
    icon: 'Search',
    color: '#3b82f6',
    input: {
      id: 'mcp_find_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'desktop_stream'],
      description: 'Connect trigger',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_find_output',
        name: 'Element Found',
        type: 'data',
        provides: 'mcp_element',
        description: 'Found element with coordinates'
      }
    ],
    dependencies: [],
    configSchema: {
      text: { type: 'string', label: 'Text to find' },
      element_type: {
        type: 'select',
        options: ['any', 'button', 'input', 'link', 'checkbox', 'dropdown', 'icon', 'text', 'menu'],
        default: 'any',
        label: 'Element Type'
      },
      near_text: { type: 'string', label: 'Near text (optional)' },
      click_if_found: { type: 'boolean', default: false, label: 'Click if found' }
    },
    defaultConfig: {
      text: '',
      element_type: 'any',
      near_text: '',
      click_if_found: false
    }
  },

  mcp_scroll: {
    id: 'mcp_scroll',
    type: 'mcp_scroll',
    label: 'MCP Scroll',
    description: 'Scroll screen via MCP Handoff',
    category: 'actions',
    icon: 'ArrowUpDown',
    color: '#06b6d4',
    input: {
      id: 'mcp_scroll_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'delay_complete'],
      description: 'Connect trigger',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_scroll_output',
        name: 'Scroll Result',
        type: 'data',
        provides: 'mcp_result',
        description: 'Scroll action result'
      }
    ],
    dependencies: [],
    configSchema: {
      direction: { type: 'select', options: ['down', 'up'], default: 'down', label: 'Direction' },
      amount: { type: 'number', default: 3, min: 1, max: 20, label: 'Scroll Amount' },
      x: { type: 'number', label: 'X Position (optional)' },
      y: { type: 'number', label: 'Y Position (optional)' }
    },
    defaultConfig: {
      direction: 'down',
      amount: 3
    }
  },

  mcp_read_screen: {
    id: 'mcp_read_screen',
    type: 'mcp_read_screen',
    label: 'MCP Read Screen',
    description: 'Capture screenshot and extract text via OCR',
    category: 'actions',
    icon: 'Camera',
    color: '#ec4899',
    input: {
      id: 'mcp_read_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'delay_complete'],
      description: 'Connect trigger',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_read_output',
        name: 'Screen Content',
        type: 'data',
        provides: 'mcp_screen_text',
        description: 'OCR extracted text from screen'
      }
    ],
    dependencies: [],
    configSchema: {
      region: { type: 'object', label: 'Region (optional)' },
      include_coordinates: { type: 'boolean', default: true, label: 'Include text coordinates' }
    },
    defaultConfig: {
      include_coordinates: true
    }
  },

  mcp_doc_scan: {
    id: 'mcp_doc_scan',
    type: 'mcp_doc_scan',
    label: 'MCP Doc Scanner',
    description: 'Scan multi-page document and extract structure',
    category: 'actions',
    icon: 'FileSearch',
    color: '#a855f7',
    input: {
      id: 'mcp_doc_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result'],
      description: 'Connect trigger',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_doc_output',
        name: 'Document Structure',
        type: 'data',
        provides: 'mcp_document',
        description: 'Scanned document with sections and structure'
      }
    ],
    dependencies: [],
    configSchema: {
      max_pages: { type: 'number', default: 20, min: 1, max: 100, label: 'Max Pages' },
      scroll_amount: { type: 'number', default: 800, label: 'Scroll Amount (px)' },
      detect_structure: { type: 'boolean', default: true, label: 'Detect headings/lists' }
    },
    defaultConfig: {
      max_pages: 20,
      scroll_amount: 800,
      detect_structure: true
    }
  },

  mcp_scroll_to: {
    id: 'mcp_scroll_to',
    type: 'mcp_scroll_to',
    label: 'MCP Scroll To Element',
    description: 'Scroll until element is found, optionally click',
    category: 'actions',
    icon: 'MousePointerClick',
    color: '#14b8a6',
    input: {
      id: 'mcp_scrollto_input',
      name: 'Trigger',
      type: 'data',
      required: true,
      accepts: ['execution_start', 'mcp_result', 'delay_complete'],
      description: 'Connect trigger',
      placeholder: 'Connect trigger'
    },
    outputs: [
      {
        id: 'mcp_scrollto_output',
        name: 'Element Result',
        type: 'data',
        provides: 'mcp_element',
        description: 'Found element after scrolling'
      }
    ],
    dependencies: [],
    configSchema: {
      target: { type: 'string', required: true, label: 'Target Text' },
      element_type: {
        type: 'select',
        options: ['any', 'button', 'input', 'link', 'checkbox'],
        default: 'any',
        label: 'Element Type'
      },
      then_click: { type: 'boolean', default: false, label: 'Click when found' },
      max_scrolls: { type: 'number', default: 10, min: 1, max: 50, label: 'Max Scroll Attempts' },
      direction: { type: 'select', options: ['down', 'up'], default: 'down', label: 'Scroll Direction' }
    },
    defaultConfig: {
      target: '',
      element_type: 'any',
      then_click: false,
      max_scrolls: 10,
      direction: 'down'
    }
  }
};
