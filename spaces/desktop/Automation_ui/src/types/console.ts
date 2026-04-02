
export type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'execution';

export interface ConsoleLog {
  id: string;
  timestamp: string;
  level: LogLevel;
  message: string;
  source?: string;
  nodeId?: string;
  executionId?: string;
  details?: any;
}

export interface ConsoleFilters {
  levels: LogLevel[];
  search: string;
  nodeId?: string;
  executionId?: string;
}
