/**
 * MCP Bridge Service - VibeMind Integration
 *
 * Provides frontend access to MCP Handoff Tools via the FastAPI backend bridge.
 * Used by MCP workflow nodes to execute desktop automation actions.
 *
 * API Base: /api/mcp
 */

// ============================================================================
// INTERFACES & TYPES
// ============================================================================

export interface MCPClickRequest {
  x: number;
  y: number;
  button?: 'left' | 'right' | 'middle';
}

export interface MCPTypeRequest {
  text: string;
  interval?: number;
}

export interface MCPShellRequest {
  command: string;
  timeout?: number;
  shell?: 'auto' | 'powershell' | 'cmd' | 'bash';
}

export interface MCPFindElementRequest {
  text?: string;
  element_type?: string;
  near_text?: string;
}

export interface MCPScrollRequest {
  direction: 'up' | 'down';
  amount?: number;
  x?: number;
  y?: number;
}

export interface MCPScrollToRequest {
  target: string;
  element_type?: string;
  then_click?: boolean;
  max_scrolls?: number;
  direction?: 'up' | 'down';
}

export interface MCPDocScanRequest {
  max_pages?: number;
  scroll_amount?: number;
  detect_structure?: boolean;
}

export interface MCPDocEditRequest {
  document_id: string;
  page: number;
  section_index: number;
  new_text: string;
  operation?: 'replace' | 'append' | 'prepend' | 'delete';
}

export interface MCPResult {
  success: boolean;
  data?: any;
  error?: string;
}

export interface MCPHealthStatus {
  status: 'healthy' | 'degraded';
  mcp_available: boolean;
  available_handlers?: string[];
  error?: string;
  mcp_path?: string;
}

// ============================================================================
// MCP BRIDGE SERVICE CLASS
// ============================================================================

class MCPBridgeService {
  private baseUrl: string;

  constructor(baseUrl: string = '/api/mcp') {
    this.baseUrl = baseUrl;
  }

  // ============================================================================
  // PRIVATE HELPERS
  // ============================================================================

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const response = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  // ============================================================================
  // HEALTH & STATUS
  // ============================================================================

  /**
   * Check MCP Bridge health status
   */
  async getHealth(): Promise<MCPHealthStatus> {
    return this.request<MCPHealthStatus>('/health');
  }

  // ============================================================================
  // DESKTOP AUTOMATION ACTIONS
  // ============================================================================

  /**
   * Execute click action
   */
  async click(req: MCPClickRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/click', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Type text
   */
  async type(req: MCPTypeRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/type', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Execute shell command
   */
  async shell(req: MCPShellRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/shell', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Find UI element by text and/or type
   */
  async findElement(req: MCPFindElementRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/find-element', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Scroll the mouse wheel
   */
  async scroll(req: MCPScrollRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/scroll', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Scroll until element is found
   */
  async scrollTo(req: MCPScrollToRequest): Promise<MCPResult> {
    const params = new URLSearchParams();
    params.set('target', req.target);
    if (req.element_type) params.set('element_type', req.element_type);
    if (req.then_click !== undefined) params.set('then_click', String(req.then_click));

    return this.request<MCPResult>(`/scroll-to?${params.toString()}`, {
      method: 'POST',
    });
  }

  /**
   * Capture screenshot and read text via OCR
   */
  async readScreen(): Promise<MCPResult> {
    return this.request<MCPResult>('/read-screen');
  }

  // ============================================================================
  // DOCUMENT SCANNER
  // ============================================================================

  /**
   * Scan document and extract structured text
   */
  async docScan(req: MCPDocScanRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/doc/scan', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Edit document section virtually
   */
  async docEdit(req: MCPDocEditRequest): Promise<MCPResult> {
    return this.request<MCPResult>('/doc/edit', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /**
   * Apply virtual edits to real document
   */
  async docApply(documentId: string, dryRun: boolean = false): Promise<MCPResult> {
    return this.request<MCPResult>(`/doc/apply/${documentId}?dry_run=${dryRun}`, {
      method: 'POST',
    });
  }

  /**
   * Export document structure
   */
  async docExport(documentId: string, format: 'json' | 'markdown' = 'json'): Promise<MCPResult> {
    return this.request<MCPResult>(`/doc/export/${documentId}?format=${format}`);
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

export const mcpBridgeService = new MCPBridgeService();
export default mcpBridgeService;


// ============================================================================
// NODE EXECUTOR - For workflow execution
// ============================================================================

/**
 * Execute MCP node action based on node type and config
 */
export async function executeMCPNode(
  nodeType: string,
  config: Record<string, any>
): Promise<MCPResult> {
  try {
    switch (nodeType) {
      case 'mcp_click':
        if (config.use_element_finder && config.element_text) {
          // First find element, then click
          const found = await mcpBridgeService.findElement({ text: config.element_text });
          if (found.success && found.data?.x !== undefined) {
            return mcpBridgeService.click({
              x: found.data.x,
              y: found.data.y,
              button: config.button,
            });
          }
          return { success: false, error: 'Element not found' };
        }
        return mcpBridgeService.click({
          x: config.x,
          y: config.y,
          button: config.button,
        });

      case 'mcp_type':
        return mcpBridgeService.type({
          text: config.text,
          interval: config.interval,
        });

      case 'mcp_shell':
        return mcpBridgeService.shell({
          command: config.command,
          timeout: config.timeout,
          shell: config.shell,
        });

      case 'mcp_find_element': {
        const result = await mcpBridgeService.findElement({
          text: config.text,
          element_type: config.element_type === 'any' ? undefined : config.element_type,
          near_text: config.near_text,
        });

        if (config.click_if_found && result.success && result.data?.x !== undefined) {
          await mcpBridgeService.click({ x: result.data.x, y: result.data.y });
        }
        return result;
      }

      case 'mcp_scroll':
        return mcpBridgeService.scroll({
          direction: config.direction,
          amount: config.amount,
          x: config.x,
          y: config.y,
        });

      case 'mcp_scroll_to':
        return mcpBridgeService.scrollTo({
          target: config.target,
          element_type: config.element_type === 'any' ? undefined : config.element_type,
          then_click: config.then_click,
          max_scrolls: config.max_scrolls,
          direction: config.direction,
        });

      case 'mcp_read_screen':
        return mcpBridgeService.readScreen();

      case 'mcp_doc_scan':
        return mcpBridgeService.docScan({
          max_pages: config.max_pages,
          scroll_amount: config.scroll_amount,
          detect_structure: config.detect_structure,
        });

      default:
        return { success: false, error: `Unknown MCP node type: ${nodeType}` };
    }
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}
