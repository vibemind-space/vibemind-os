/**
 * Automation UI Plugin for Clawdbot
 *
 * Bridges Clawdbot messaging (WhatsApp, Telegram, Discord, etc.)
 * to the Automation_ui desktop automation backend.
 *
 * Installation:
 *   1. Copy this folder to ~/.clawdbot/extensions/automation-ui/
 *   2. Or symlink: ln -s /path/to/automation-ui ~/.clawdbot/extensions/automation-ui
 *   3. Restart Clawdbot Gateway
 */

import type { ClawdbotPluginApi, Message, ToolResult } from 'clawdbot';

interface AutomationConfig {
  backendUrl: string;
  wsUrl: string;
  timeout: number;
}

interface CommandResult {
  success: boolean;
  message: string;
  data?: Record<string, unknown>;
  image_base64?: string;
  error?: string;
  execution_time_ms: number;
}

const DEFAULT_CONFIG: AutomationConfig = {
  backendUrl: 'http://localhost:8007',
  wsUrl: 'ws://localhost:8007/ws/clawdbot',
  timeout: 30000,
};

export default function automationUiPlugin(api: ClawdbotPluginApi) {
  const config: AutomationConfig = {
    ...DEFAULT_CONFIG,
    ...api.getConfig('automation-ui'),
  };

  // Register the main desktop automation tool
  api.registerAgentTool({
    name: 'desktop_automation',
    description: `Execute desktop automation commands.
    Supports: opening apps/URLs, clicking, typing, scrolling, screenshots, OCR.
    Examples: "open chrome", "type Hello World", "scroll down", "screenshot"`,
    parameters: {
      type: 'object',
      properties: {
        command: {
          type: 'string',
          description: 'Natural language command to execute (German or English)',
        },
      },
      required: ['command'],
    },
    handler: async ({ command }): Promise<ToolResult> => {
      try {
        const response = await fetch(`${config.backendUrl}/api/clawdbot/command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            command,
            user_id: api.getCurrentUserId?.() || 'clawdbot_user',
            platform: api.getCurrentPlatform?.() || 'clawdbot',
          }),
          signal: AbortSignal.timeout(config.timeout),
        });

        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }

        const result: CommandResult = await response.json();

        // Return image if present
        if (result.image_base64) {
          return {
            success: result.success,
            text: result.message,
            image: Buffer.from(result.image_base64, 'base64'),
          };
        }

        return {
          success: result.success,
          text: result.message,
          data: result.data,
        };
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        return {
          success: false,
          text: `Automation failed: ${errorMessage}`,
        };
      }
    },
  });

  // Register screenshot command for quick access
  api.registerCommand({
    name: 'screenshot',
    aliases: ['screen', 'bildschirm', 'ss'],
    description: 'Take and send a screenshot of the desktop',
    handler: async (): Promise<{ text?: string; image?: Buffer }> => {
      try {
        const response = await fetch(`${config.backendUrl}/api/clawdbot/screenshot`, {
          method: 'GET',
          signal: AbortSignal.timeout(config.timeout),
        });

        if (!response.ok) {
          throw new Error(`Screenshot failed: ${response.status}`);
        }

        const imageBuffer = Buffer.from(await response.arrayBuffer());

        return {
          text: '📸 Screenshot',
          image: imageBuffer,
        };
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        return { text: `❌ Screenshot failed: ${errorMessage}` };
      }
    },
  });

  // Register status command
  api.registerCommand({
    name: 'automation-status',
    aliases: ['astatus', 'desktop-status'],
    description: 'Check automation backend status',
    handler: async (): Promise<{ text: string }> => {
      try {
        const response = await fetch(`${config.backendUrl}/api/clawdbot/status`, {
          signal: AbortSignal.timeout(5000),
        });

        if (!response.ok) {
          return { text: '❌ Automation backend nicht erreichbar' };
        }

        const status = await response.json();

        return {
          text: `🤖 Desktop Automation Status:
• Status: ${status.status === 'connected' ? '✅ Verbunden' : '⏳ Initialisiert'}
• Aktive Sessions: ${status.active_sessions}
• Fähigkeiten: ${status.capabilities.join(', ')}`,
        };
      } catch (error) {
        return { text: '❌ Automation backend nicht erreichbar' };
      }
    },
  });

  // Register OCR/read command
  api.registerCommand({
    name: 'read-screen',
    aliases: ['ocr', 'lesen', 'read'],
    description: 'Read text from the current screen using OCR',
    handler: async (): Promise<{ text: string }> => {
      try {
        const response = await fetch(`${config.backendUrl}/api/clawdbot/command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            command: 'ocr',
            user_id: api.getCurrentUserId?.() || 'clawdbot_user',
            platform: api.getCurrentPlatform?.() || 'clawdbot',
          }),
          signal: AbortSignal.timeout(config.timeout),
        });

        const result: CommandResult = await response.json();

        if (result.success && result.data?.text) {
          const text = String(result.data.text);
          // Truncate if too long
          const truncated = text.length > 3000 ? text.substring(0, 3000) + '...' : text;
          return { text: `📖 Bildschirmtext:\n\n${truncated}` };
        }

        return { text: result.message };
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        return { text: `❌ OCR failed: ${errorMessage}` };
      }
    },
  });

  // Register webhook handler for async results from backend
  // This receives callbacks when async operations complete
  api.registerWebhook?.({
    path: '/automation-results',
    method: 'POST',
    handler: async (req: {
      body: {
        user_id: string;
        platform: string;
        success: boolean;
        message: string;
        data?: Record<string, unknown>;
        image_base64?: string;
        error?: string;
        execution_time_ms?: number;
        timestamp?: string;
      };
    }): Promise<{ status: string }> => {
      const { user_id, platform, success, message, image_base64 } = req.body;

      try {
        // Route the response back to the user
        const messagePayload: { text: string; image?: Buffer } = {
          text: message,
        };

        // Include image if present
        if (image_base64) {
          messagePayload.image = Buffer.from(image_base64, 'base64');
        }

        // Send message back to user via Clawdbot's messaging system
        await api.sendMessage?.(user_id, platform, messagePayload);

        api.log?.info?.(`Callback routed to ${user_id}@${platform}`);

        return { status: 'delivered' };
      } catch (error) {
        api.log?.error?.(`Failed to route callback: ${error}`);
        return { status: 'error' };
      }
    },
  });

  // Log successful registration
  api.log?.info?.('Automation UI plugin registered successfully');

  return {
    name: 'automation-ui',
    version: '1.0.0',
  };
}
