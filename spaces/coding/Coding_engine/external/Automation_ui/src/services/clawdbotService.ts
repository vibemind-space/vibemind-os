/**
 * Clawdbot Service - Messaging Integration
 *
 * Provides frontend access to the Clawdbot bridge API for monitoring
 * and interacting with the messaging gateway integration.
 *
 * API Base: /api/clawdbot
 */

// ============================================================================
// INTERFACES & TYPES
// ============================================================================

export interface ClawdbotCommandRequest {
  command: string;
  user_id?: string;
  platform?: string;
  message_id?: string;
}

export interface ClawdbotCommandResponse {
  success: boolean;
  message: string;
  data?: Record<string, unknown>;
  image_base64?: string;
  error?: string;
  execution_time_ms: number;
}

export interface ClawdbotStatus {
  status: 'connected' | 'initializing' | 'disconnected';
  initialized: boolean;
  active_sessions: number;
  capabilities: string[];
  timestamp: string;
}

export interface ClawdbotSession {
  user_id: string;
  platform: string;
  last_command?: string;
  created_at: string;
  updated_at: string;
}

export interface ClawdbotMessage {
  id: string;
  user_id: string;
  platform: string;
  direction: 'incoming' | 'outgoing';
  text: string;
  success?: boolean;
  timestamp: string;
  image?: string;
}

export interface ClawdbotWebhookPayload {
  type: 'message' | 'status';
  user_id: string;
  platform: string;
  text?: string;
  message_id?: string;
  data?: Record<string, unknown>;
}

// ============================================================================
// CLAWDBOT SERVICE CLASS
// ============================================================================

class ClawdbotServiceClass {
  private baseUrl: string;
  private messageHistory: ClawdbotMessage[] = [];
  private maxHistorySize: number = 100;

  constructor(baseUrl: string = '/api/clawdbot') {
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
      const error = await response.text();
      throw new Error(`Clawdbot API error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  // ============================================================================
  // PUBLIC API METHODS
  // ============================================================================

  /**
   * Execute a desktop automation command via Clawdbot bridge
   */
  async executeCommand(request: ClawdbotCommandRequest): Promise<ClawdbotCommandResponse> {
    const result = await this.request<ClawdbotCommandResponse>('/command', {
      method: 'POST',
      body: JSON.stringify(request),
    });

    // Add to message history
    this.addToHistory({
      id: `cmd_${Date.now()}`,
      user_id: request.user_id || 'web_user',
      platform: request.platform || 'web',
      direction: 'outgoing',
      text: request.command,
      success: result.success,
      timestamp: new Date().toISOString(),
    });

    if (result.message) {
      this.addToHistory({
        id: `res_${Date.now()}`,
        user_id: request.user_id || 'web_user',
        platform: request.platform || 'web',
        direction: 'incoming',
        text: result.message,
        success: result.success,
        timestamp: new Date().toISOString(),
        image: result.image_base64,
      });
    }

    return result;
  }

  /**
   * Get current screenshot as base64
   */
  async getScreenshot(): Promise<string> {
    const response = await fetch(`${this.baseUrl}/screenshot`);

    if (!response.ok) {
      throw new Error(`Screenshot failed: ${response.status}`);
    }

    const blob = await response.blob();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /**
   * Get screenshot as Blob
   */
  async getScreenshotBlob(): Promise<Blob> {
    const response = await fetch(`${this.baseUrl}/screenshot`);

    if (!response.ok) {
      throw new Error(`Screenshot failed: ${response.status}`);
    }

    return response.blob();
  }

  /**
   * Get Clawdbot bridge status
   */
  async getStatus(): Promise<ClawdbotStatus> {
    return this.request<ClawdbotStatus>('/status');
  }

  /**
   * Get all active user sessions
   */
  async getSessions(): Promise<ClawdbotSession[]> {
    return this.request<ClawdbotSession[]>('/sessions');
  }

  /**
   * Send a notification to a user
   */
  async sendNotification(
    userId: string,
    platform: string,
    message: string,
    type: 'info' | 'success' | 'warning' | 'error' = 'info'
  ): Promise<{ status: string }> {
    const params = new URLSearchParams({
      user_id: userId,
      platform: platform,
      message: message,
      notification_type: type,
    });

    return this.request<{ status: string }>(`/notify?${params}`, {
      method: 'POST',
    });
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string; service: string }> {
    return this.request<{ status: string; service: string }>('/health');
  }

  // ============================================================================
  // MESSAGE HISTORY (LOCAL)
  // ============================================================================

  private addToHistory(message: ClawdbotMessage): void {
    this.messageHistory.unshift(message);

    // Trim history if too large
    if (this.messageHistory.length > this.maxHistorySize) {
      this.messageHistory = this.messageHistory.slice(0, this.maxHistorySize);
    }
  }

  /**
   * Get message history (local cache)
   */
  getMessageHistory(limit: number = 50): ClawdbotMessage[] {
    return this.messageHistory.slice(0, limit);
  }

  /**
   * Clear message history
   */
  clearMessageHistory(): void {
    this.messageHistory = [];
  }

  /**
   * Add external message to history (e.g., from WebSocket)
   */
  addExternalMessage(message: ClawdbotMessage): void {
    this.addToHistory(message);
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

// Get backend URL from environment or use default
const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
const apiBase = `${backendUrl}/api/clawdbot`;

export const ClawdbotService = new ClawdbotServiceClass(apiBase);

// Also export the class for custom instances
export { ClawdbotServiceClass };

// ============================================================================
// CONTACT TYPES
// ============================================================================

export interface Contact {
  name: string;
  whatsapp?: string;
  telegram?: string;
  discord?: string;
  email?: string;
  signal?: string;
  imessage?: string;
  aliases?: string[];
  notes?: string;
}

export interface ContactCreateRequest {
  key: string;
  name: string;
  whatsapp?: string;
  telegram?: string;
  discord?: string;
  email?: string;
  signal?: string;
  imessage?: string;
  aliases?: string[];
  notes?: string;
}

export interface ContactSearchResult {
  key: string;
  contact: Contact;
  score: number;
}

// ============================================================================
// CONTACT SERVICE
// ============================================================================

class ContactServiceClass {
  private baseUrl: string;

  constructor(baseUrl: string = '/api/clawdbot') {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Contact API error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  /**
   * List all contacts
   */
  async listContacts(): Promise<Record<string, Contact>> {
    return this.request<Record<string, Contact>>('/contacts');
  }

  /**
   * Search contacts with fuzzy matching
   */
  async searchContacts(query: string, limit: number = 5): Promise<{
    query: string;
    results: ContactSearchResult[];
  }> {
    return this.request(`/contacts/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  }

  /**
   * Get a specific contact by key
   */
  async getContact(key: string): Promise<{ key: string; contact: Contact }> {
    return this.request(`/contacts/${encodeURIComponent(key)}`);
  }

  /**
   * Create or update a contact
   */
  async createContact(contact: ContactCreateRequest): Promise<{
    status: string;
    key: string;
    contact: Contact;
  }> {
    return this.request('/contacts', {
      method: 'POST',
      body: JSON.stringify(contact),
    });
  }

  /**
   * Delete a contact
   */
  async deleteContact(key: string): Promise<{ status: string; key: string }> {
    return this.request(`/contacts/${encodeURIComponent(key)}`, {
      method: 'DELETE',
    });
  }

  /**
   * Resolve a contact query (supports fuzzy matching)
   */
  async resolveContact(query: string, platform?: string): Promise<{
    found: boolean;
    query: string;
    contact?: Contact;
    suggestions?: string[];
    platform?: string;
    recipient_id?: string;
  }> {
    const params = platform ? `?platform=${encodeURIComponent(platform)}` : '';
    return this.request(`/contacts/${encodeURIComponent(query)}/resolve${params}`, {
      method: 'POST',
    });
  }

  /**
   * List all variables
   */
  async listVariables(): Promise<Record<string, string>> {
    return this.request('/variables');
  }

  /**
   * Set a variable
   */
  async setVariable(name: string, value: string): Promise<{
    status: string;
    name: string;
    value: string;
  }> {
    return this.request(`/variables/${encodeURIComponent(name)}?value=${encodeURIComponent(value)}`, {
      method: 'POST',
    });
  }

  /**
   * List all templates
   */
  async listTemplates(): Promise<Record<string, string>> {
    return this.request('/templates');
  }

  /**
   * Render a template
   */
  async renderTemplate(name: string, values?: Record<string, string>): Promise<{
    name: string;
    rendered: string;
  }> {
    const params = new URLSearchParams({ name });
    return this.request(`/templates/render?${params}`, {
      method: 'POST',
      body: values ? JSON.stringify(values) : undefined,
    });
  }
}

// Get backend URL from environment or use default
const contactApiBase = `${backendUrl}/api/clawdbot`;

export const ContactService = new ContactServiceClass(contactApiBase);

// Also export the class for custom instances
export { ContactServiceClass };
