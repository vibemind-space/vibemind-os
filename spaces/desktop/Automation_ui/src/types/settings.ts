
export interface PanelSettings {
  layout: {
    defaultPanelSizes: {
      canvas: number;
      debug: number;
    };
    rememberPanelState: boolean;
    autoHideEmptyPanels: boolean;
  };
  theme: {
    mode: 'light' | 'dark' | 'system';
    highContrast: boolean;
    reducedMotion: boolean;
  };
  console: {
    autoScroll: boolean;
    maxLogEntries: number;
    logLevels: ('error' | 'warn' | 'info' | 'debug')[];
    timestampFormat: '12h' | '24h' | 'relative';
  };
  variables: {
    autoExpand: boolean;
    showTypes: boolean;
    maxStringLength: number;
    jsonIndentation: 2 | 4 | 'tab';
  };
}

export interface WorkflowExecutionSettings {
  timeout: {
    nodeTimeout: number; // in seconds
    workflowTimeout: number; // in seconds
    enableTimeouts: boolean;
  };
  errorHandling: {
    stopOnError: boolean;
    retryFailedNodes: boolean;
    maxRetries: number;
    retryDelay: number; // in milliseconds
  };
  logging: {
    level: 'error' | 'warn' | 'info' | 'debug' | 'trace';
    enableNodeTiming: boolean;
    enableMemoryTracking: boolean;
    enableDetailedLogs: boolean;
  };
  performance: {
    maxConcurrentNodes: number;
    memoryLimit: number; // in MB
    enableCaching: boolean;
    cacheTimeout: number; // in minutes
  };
}

export interface CanvasSettings {
  grid: {
    enabled: boolean;
    size: number;
    snapToGrid: boolean;
    showGrid: boolean;
  };
  nodes: {
    showMinimap: boolean;
    enableAnimations: boolean;
    nodeSpacing: number;
    autoAlign: boolean;
    showNodeIds: boolean;
  };
  connections: {
    validateConnections: boolean;
    showConnectionLabels: boolean;
    animateConnections: boolean;
    connectionStyle: 'bezier' | 'straight' | 'step';
  };
  autoSave: {
    enabled: boolean;
    interval: number; // in minutes
    maxVersions: number;
  };
}

export interface IntegrationSettings {
  api: {
    baseUrl: string;
    timeout: number;
    retryAttempts: number;
  };
  webhooks: {
    enableWebhooks: boolean;
    defaultTimeout: number;
    maxPayloadSize: number; // in KB
  };
  external: {
    enableThirdPartyIntegrations: boolean;
    trustedDomains: string[];
    apiKeyStorage: 'local' | 'secure';
  };
}

export interface WorkflowSettings {
  panel: PanelSettings;
  execution: WorkflowExecutionSettings;
  canvas: CanvasSettings;
  integration: IntegrationSettings;
}

export const DEFAULT_WORKFLOW_SETTINGS: WorkflowSettings = {
  panel: {
    layout: {
      defaultPanelSizes: { canvas: 70, debug: 30 },
      rememberPanelState: true,
      autoHideEmptyPanels: false,
    },
    theme: {
      mode: 'system',
      highContrast: false,
      reducedMotion: false,
    },
    console: {
      autoScroll: true,
      maxLogEntries: 1000,
      logLevels: ['error', 'warn', 'info'],
      timestampFormat: '24h',
    },
    variables: {
      autoExpand: false,
      showTypes: true,
      maxStringLength: 100,
      jsonIndentation: 2,
    },
  },
  execution: {
    timeout: {
      nodeTimeout: 30,
      workflowTimeout: 300,
      enableTimeouts: true,
    },
    errorHandling: {
      stopOnError: true,
      retryFailedNodes: false,
      maxRetries: 3,
      retryDelay: 1000,
    },
    logging: {
      level: 'info',
      enableNodeTiming: true,
      enableMemoryTracking: false,
      enableDetailedLogs: false,
    },
    performance: {
      maxConcurrentNodes: 10,
      memoryLimit: 512,
      enableCaching: true,
      cacheTimeout: 60,
    },
  },
  canvas: {
    grid: {
      enabled: true,
      size: 20,
      snapToGrid: true,
      showGrid: true,
    },
    nodes: {
      showMinimap: true,
      enableAnimations: true,
      nodeSpacing: 100,
      autoAlign: false,
      showNodeIds: false,
    },
    connections: {
      validateConnections: true,
      showConnectionLabels: false,
      animateConnections: true,
      connectionStyle: 'bezier',
    },
    autoSave: {
      enabled: true,
      interval: 5,
      maxVersions: 10,
    },
  },
  integration: {
    api: {
      baseUrl: '',
      timeout: 30000,
      retryAttempts: 3,
    },
    webhooks: {
      enableWebhooks: true,
      defaultTimeout: 30000,
      maxPayloadSize: 1024,
    },
    external: {
      enableThirdPartyIntegrations: false,
      trustedDomains: [],
      apiKeyStorage: 'secure',
    },
  },
};
