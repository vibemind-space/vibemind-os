/**
 * Intent Chat Panel
 *
 * Chat interface for processing intents via MCP tools.
 * Supports text input and displays automation results.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Loader2, Send, Bot, User, Zap, Eye, MousePointer, Terminal, CheckCircle, XCircle } from 'lucide-react';

// ============================================
// Types
// ============================================

export interface StreamEvent {
  type: 'thinking' | 'tool_start' | 'tool_result' | 'summary' | 'error' | 'done'
    | 'approval_required' | 'waiting_approval' | 'tool_approved' | 'tool_denied'
    | 'click_confirm' | 'waiting_click_confirm' | 'click_confirmed' | 'click_denied'
    | 'action_visual'
    | 'video_analysis' | 'guardian_correction' | 'guardian_status' | 'monitor_alert';
  iteration?: number;
  content?: string;
  tool?: string;
  params?: Record<string, unknown>;
  result?: Record<string, unknown>;
  success?: boolean;
  step_index?: number;
  message?: string;
  has_tool_calls?: boolean;
  total_steps?: number;
  iterations?: number;
  duration_ms?: number;
  conversation_id?: string;
  x?: number;
  y?: number;
  action?: string;
  // Guardian Mode fields
  args?: Record<string, unknown>;
  status?: string;
  corrections_count?: number;
  // Video Analysis fields
  verified?: boolean;
  screen_state?: string;
  confidence?: number;
  viewport?: { x: number; y: number; width: number; height: number };
  ocr_hint?: { x: number; y: number };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  metadata?: {
    action?: string;
    coordinates?: { x: number; y: number };
    detectedElements?: Array<{ label: string; confidence: number }>;
    status?: 'pending' | 'processing' | 'completed' | 'failed';
    tool?: string;
    stepIndex?: number;
    iteration?: number;
    isToolStep?: boolean;
  };
}

export interface IntentResult {
  success: boolean;
  action: string;
  target?: string;
  coordinates?: { x: number; y: number };
  detectedElements?: Array<{ label: string; x: number; y: number; confidence: number }>;
  ocrText?: string;
  error?: string;
}

interface IntentChatPanelProps {
  onIntent?: (intent: string) => Promise<IntentResult | null>;
  onIntentStream?: (intent: string, onEvent: (event: StreamEvent) => void) => Promise<void>;
  onReadScreen?: () => Promise<{ text: string; elements: Array<{ label: string; x: number; y: number }> } | null>;
  onValidate?: (target: string) => Promise<{ found: boolean; x?: number; y?: number; confidence?: number } | null>;
  onAction?: (action: string, params: Record<string, unknown>) => Promise<{ success: boolean; error?: string } | null>;
  className?: string;
}

// ============================================
// Component
// ============================================

export const IntentChatPanel: React.FC<IntentChatPanelProps> = ({
  onIntent,
  onIntentStream,
  onReadScreen,
  onValidate,
  onAction,
  className = ''
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'system',
      content: 'Desktop Automation Ready. Type your intent or use commands:\n• "read screen" - Capture and analyze screen\n• "find [element]" - Locate UI element\n• "click [target]" - Click on element\n• "type [text]" - Type text',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<{ conversationId: string; tool: string } | null>(null);
  const [pendingClickConfirm, setPendingClickConfirm] = useState<{
    conversationId: string; element: string; x: number; y: number; confirmed: number; threshold: number;
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Add message helper
  const addMessage = useCallback((role: ChatMessage['role'], content: string, metadata?: ChatMessage['metadata']) => {
    const message: ChatMessage = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      role,
      content,
      timestamp: new Date(),
      metadata
    };
    setMessages(prev => [...prev, message]);
    return message.id;
  }, []);

  // Update message status
  const updateMessageStatus = useCallback((id: string, status: 'pending' | 'processing' | 'completed' | 'failed') => {
    setMessages(prev => prev.map(msg =>
      msg.id === id ? { ...msg, metadata: { ...msg.metadata, status } } : msg
    ));
  }, []);

  // Update message content and metadata
  const updateMessage = useCallback((id: string, updates: { content?: string; metadata?: Partial<ChatMessage['metadata']> }) => {
    setMessages(prev => prev.map(msg =>
      msg.id === id ? {
        ...msg,
        ...(updates.content !== undefined ? { content: updates.content } : {}),
        ...(updates.metadata ? { metadata: { ...msg.metadata, ...updates.metadata } } : {})
      } : msg
    ));
  }, []);

  // Process intent
  const processIntent = useCallback(async (text: string) => {
    const lowerText = text.toLowerCase().trim();

    // Read Screen command
    if (lowerText === 'read screen' || lowerText === 'scan' || lowerText === 'analyze') {
      if (onReadScreen) {
        const msgId = addMessage('assistant', 'Reading screen...', { action: 'read_screen', status: 'processing' });
        try {
          const result = await onReadScreen();
          if (result) {
            updateMessageStatus(msgId, 'completed');
            addMessage('assistant', `Screen analyzed:\n• Text found: ${result.text.substring(0, 200)}${result.text.length > 200 ? '...' : ''}\n• Elements detected: ${result.elements.length}`, {
              action: 'read_screen',
              detectedElements: result.elements.map(e => ({ label: e.label, confidence: 1 })),
              status: 'completed'
            });
          } else {
            updateMessageStatus(msgId, 'failed');
            addMessage('assistant', 'Failed to read screen. Make sure MCP server is running.');
          }
        } catch (err) {
          updateMessageStatus(msgId, 'failed');
          addMessage('assistant', `Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
        }
        return;
      }
    }

    // Find/Validate command
    const findMatch = lowerText.match(/^(?:find|locate|search|validate)\s+(.+)$/);
    if (findMatch && onValidate) {
      const target = findMatch[1];
      const msgId = addMessage('assistant', `Looking for "${target}"...`, { action: 'validate', status: 'processing' });
      try {
        const result = await onValidate(target);
        if (result?.found) {
          updateMessageStatus(msgId, 'completed');
          addMessage('assistant', `Found "${target}" at (${result.x}, ${result.y}) with ${Math.round((result.confidence || 0) * 100)}% confidence`, {
            action: 'validate',
            coordinates: { x: result.x!, y: result.y! },
            status: 'completed'
          });
        } else {
          updateMessageStatus(msgId, 'failed');
          addMessage('assistant', `Could not find "${target}" on screen.`);
        }
      } catch (err) {
        updateMessageStatus(msgId, 'failed');
        addMessage('assistant', `Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
      return;
    }

    // Click command
    const clickMatch = lowerText.match(/^click\s+(.+)$/);
    if (clickMatch && onAction) {
      const target = clickMatch[1];

      // First validate to get coordinates
      if (onValidate) {
        const msgId = addMessage('assistant', `Finding "${target}" to click...`, { action: 'click', status: 'processing' });
        try {
          const validateResult = await onValidate(target);
          if (validateResult?.found && validateResult.x !== undefined && validateResult.y !== undefined) {
            const actionResult = await onAction('click', { x: validateResult.x, y: validateResult.y });
            if (actionResult?.success) {
              updateMessageStatus(msgId, 'completed');
              addMessage('assistant', `Clicked "${target}" at (${validateResult.x}, ${validateResult.y})`, {
                action: 'click',
                coordinates: { x: validateResult.x, y: validateResult.y },
                status: 'completed'
              });
            } else {
              updateMessageStatus(msgId, 'failed');
              addMessage('assistant', `Click failed: ${actionResult?.error || 'Unknown error'}`);
            }
          } else {
            updateMessageStatus(msgId, 'failed');
            addMessage('assistant', `Could not find "${target}" to click.`);
          }
        } catch (err) {
          updateMessageStatus(msgId, 'failed');
          addMessage('assistant', `Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
        }
        return;
      }
    }

    // Type command
    const typeMatch = lowerText.match(/^type\s+(.+)$/);
    if (typeMatch && onAction) {
      const text = typeMatch[1];
      const msgId = addMessage('assistant', `Typing "${text}"...`, { action: 'type', status: 'processing' });
      try {
        const result = await onAction('type', { text });
        if (result?.success) {
          updateMessageStatus(msgId, 'completed');
          addMessage('assistant', `Typed: "${text}"`, { action: 'type', status: 'completed' });
        } else {
          updateMessageStatus(msgId, 'failed');
          addMessage('assistant', `Type failed: ${result?.error || 'Unknown error'}`);
        }
      } catch (err) {
        updateMessageStatus(msgId, 'failed');
        addMessage('assistant', `Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
      return;
    }

    // General intent processing - prefer streaming if available
    if (onIntentStream) {
      let currentMsgId = addMessage('assistant', 'Thinking...', { action: 'intent', status: 'processing' });

      try {
        await onIntentStream(text, (event: StreamEvent) => {
          switch (event.type) {
            case 'thinking': {
              const thinkingText = event.content
                ? event.content
                : event.has_tool_calls
                  ? `Iteration ${event.iteration}: Planning actions...`
                  : `Iteration ${event.iteration}: Formulating response...`;
              updateMessage(currentMsgId, {
                content: thinkingText,
                metadata: { status: 'processing', iteration: event.iteration }
              });
              break;
            }

            case 'tool_start': {
              // Mark previous message as done
              updateMessage(currentMsgId, { metadata: { status: 'completed' } });
              // Add new message for tool execution
              const paramStr = event.params
                ? Object.entries(event.params).map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ')
                : '';
              currentMsgId = addMessage('assistant',
                `${event.tool}(${paramStr})...`, {
                action: event.tool,
                status: 'processing',
                isToolStep: true,
                tool: event.tool,
                stepIndex: event.step_index,
                iteration: event.iteration
              });
              break;
            }

            case 'tool_result': {
              const icon = event.success ? 'OK' : 'FAIL';
              let resultText = `${event.tool} → ${icon}`;
              if (event.result) {
                const rStr = JSON.stringify(event.result);
                if (rStr !== '{}' && rStr !== '{"success":true}') {
                  resultText += `\n${rStr}`;
                }
              }
              updateMessage(currentMsgId, {
                content: resultText,
                metadata: {
                  status: event.success ? 'completed' : 'failed',
                  tool: event.tool,
                  isToolStep: true,
                  stepIndex: event.step_index,
                  iteration: event.iteration
                }
              });
              // Prepare a new thinking message for next iteration
              currentMsgId = addMessage('assistant', 'Thinking...', { action: 'intent', status: 'processing' });
              break;
            }

            case 'summary': {
              updateMessage(currentMsgId, {
                content: event.content || 'Done.',
                metadata: { status: 'completed', action: 'summary' }
              });
              break;
            }

            case 'approval_required': {
              // Show approval request with tool details
              updateMessage(currentMsgId, { metadata: { status: 'completed' } });
              const paramStr = event.params
                ? Object.entries(event.params).map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ')
                : '';
              currentMsgId = addMessage('system',
                `APPROVAL REQUIRED: ${event.tool}(${paramStr})\n${event.message || 'This tool needs your permission to run.'}`, {
                action: 'approval',
                status: 'pending',
                tool: event.tool,
              });
              // Store conversation_id for approve/deny
              if (event.conversation_id) {
                setPendingApproval({ conversationId: event.conversation_id, tool: event.tool || '' });
              }
              break;
            }

            case 'tool_approved': {
              updateMessage(currentMsgId, {
                content: `APPROVED: ${event.tool} - executing...`,
                metadata: { status: 'processing', tool: event.tool }
              });
              setPendingApproval(null);
              currentMsgId = addMessage('assistant', 'Executing approved tool...', { status: 'processing' });
              break;
            }

            case 'tool_denied': {
              updateMessage(currentMsgId, {
                content: `DENIED: ${event.tool}`,
                metadata: { status: 'failed', tool: event.tool }
              });
              setPendingApproval(null);
              currentMsgId = addMessage('assistant', 'Thinking...', { status: 'processing' });
              break;
            }

            case 'click_confirm': {
              const e = event as any;
              currentMsgId = addMessage('system',
                `Klick auf "${e.element}" bei (${e.x}, ${e.y}) — Richtig?`, {
                action: 'click_confirm', status: 'pending'
              });
              if (e.conversation_id) {
                setPendingClickConfirm({
                  conversationId: e.conversation_id,
                  element: e.element || '',
                  x: e.x || 0, y: e.y || 0,
                  confirmed: e.user_confirmed || 0,
                  threshold: e.threshold || 3,
                });
              }
              break;
            }

            case 'click_confirmed': {
              const e = event as any;
              updateMessage(currentMsgId, {
                content: `Klick bestaetigt: "${e.element}"${e.trusted ? ' (Auto-Trust aktiviert)' : ''}`,
                metadata: { status: 'completed' }
              });
              setPendingClickConfirm(null);
              currentMsgId = addMessage('assistant', 'Fortfahren...', { status: 'processing' });
              break;
            }

            case 'click_denied': {
              const e = event as any;
              updateMessage(currentMsgId, {
                content: `Klick verworfen: "${e.element}" — Position wird neu gesucht.`,
                metadata: { status: 'failed' }
              });
              setPendingClickConfirm(null);
              currentMsgId = addMessage('assistant', 'Korrigiere...', { status: 'processing' });
              break;
            }

            case 'video_analysis': {
              // Video Agent analysis - show only if not verified or low confidence
              if (event.verified === false || (event.confidence && event.confidence < 0.7)) {
                const analysisText = `📹 Video: ${event.screen_state || 'Analyzing...'}${event.confidence ? ` (conf: ${(event.confidence * 100).toFixed(0)}%)` : ''}`;
                addMessage('system', analysisText, {
                  action: 'video_analysis',
                  status: event.verified ? 'completed' : 'failed',
                  tool: event.tool,
                  stepIndex: event.step_index
                });
              }
              break;
            }

            case 'guardian_correction': {
              // Guardian Mode correction attempt
              const paramStr = event.args
                ? Object.entries(event.args).map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ')
                : '';
              const correctionText = `🛡️ Guardian: ${event.tool}(${paramStr})${event.result?.success ? ' ✓' : ' ✗'}`;
              addMessage('system', correctionText, {
                action: 'guardian_correction',
                status: event.result?.success ? 'completed' : 'failed',
                tool: event.tool,
                stepIndex: event.step_index
              });
              break;
            }

            case 'guardian_status': {
              // Guardian final status
              let statusText = '';
              let status: 'completed' | 'failed' | 'processing' = 'completed';

              if (event.status === 'verified') {
                statusText = '✅ Verified - action successful';
              } else if (event.status === 'corrected') {
                statusText = `🔧 Corrected after ${event.corrections_count || 0} attempt(s)`;
                status = 'completed';
              } else if (event.status === 'failed') {
                statusText = `❌ Correction failed after ${event.corrections_count || 0} attempt(s)`;
                status = 'failed';
              }

              if (statusText) {
                addMessage('system', statusText, {
                  action: 'guardian_status',
                  status,
                  stepIndex: event.step_index
                });
              }
              break;
            }

            case 'monitor_alert': {
              // Monitor Mode alert
              addMessage('system', `⚠️ Monitor: ${event.message || 'Screen change detected'}`, {
                action: 'monitor_alert',
                status: 'pending'
              });
              break;
            }

            case 'error': {
              updateMessage(currentMsgId, {
                content: `Error: ${event.message}`,
                metadata: { status: 'failed' }
              });
              break;
            }

            case 'done': {
              // Clean up any leftover "Thinking..." messages
              setMessages(prev => prev.filter(msg =>
                !(msg.content === 'Thinking...' && msg.metadata?.status === 'processing')
              ));
              if (event.duration_ms) {
                addMessage('system', `${event.total_steps} steps, ${event.iterations} iterations, ${(event.duration_ms / 1000).toFixed(1)}s`);
              }
              break;
            }
          }
        });
      } catch (err) {
        updateMessage(currentMsgId, {
          content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          metadata: { status: 'failed' }
        });
      }
      return;
    }

    // Fallback: non-streaming intent processing
    if (onIntent) {
      const msgId = addMessage('assistant', 'Processing intent...', { action: 'intent', status: 'processing' });
      try {
        const result = await onIntent(text);
        if (result?.success) {
          updateMessageStatus(msgId, 'completed');
          let responseText = `Executed: ${result.action}`;
          if (result.target) responseText += ` on "${result.target}"`;
          if (result.coordinates) responseText += ` at (${result.coordinates.x}, ${result.coordinates.y})`;
          addMessage('assistant', responseText, {
            action: result.action,
            coordinates: result.coordinates,
            detectedElements: result.detectedElements?.map(e => ({ label: e.label, confidence: e.confidence })),
            status: 'completed'
          });
        } else {
          updateMessageStatus(msgId, 'failed');
          addMessage('assistant', `Intent failed: ${result?.error || 'Could not process intent'}`);
        }
      } catch (err) {
        updateMessageStatus(msgId, 'failed');
        addMessage('assistant', `Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
      return;
    }

    // No handler available
    addMessage('assistant', 'No handler available for this command. Available commands:\n• read screen\n• find [element]\n• click [target]\n• type [text]');
  }, [onIntent, onIntentStream, onReadScreen, onValidate, onAction, addMessage, updateMessage, updateMessageStatus]);

  // Handle tool approval/denial
  const handleApproval = useCallback(async (approved: boolean) => {
    if (!pendingApproval) return;
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
    try {
      await fetch(`${backendUrl}/api/llm/intent/intervene`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: pendingApproval.conversationId,
          action: approved ? 'approve_tool' : 'deny_tool',
        })
      });
    } catch (err) {
      console.error('Approval request failed:', err);
    }
    setPendingApproval(null);
  }, [pendingApproval]);

  // Handle click confirmation (Richtig/Falsch)
  const handleClickConfirm = useCallback(async (correct: boolean) => {
    if (!pendingClickConfirm) return;
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
    try {
      await fetch(`${backendUrl}/api/llm/intent/intervene`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: pendingClickConfirm.conversationId,
          action: correct ? 'confirm_click' : 'deny_click',
        })
      });
    } catch (err) {
      console.error('Click confirm request failed:', err);
    }
    setPendingClickConfirm(null);
  }, [pendingClickConfirm]);

  // Handle send
  const handleSend = useCallback(async () => {
    if (!input.trim() || isProcessing) return;

    const userMessage = input.trim();
    setInput('');
    addMessage('user', userMessage);

    setIsProcessing(true);
    try {
      await processIntent(userMessage);
    } finally {
      setIsProcessing(false);
    }
  }, [input, isProcessing, addMessage, processIntent]);

  // Handle key press
  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // Render message
  const renderMessage = (message: ChatMessage) => {
    const isUser = message.role === 'user';
    const isSystem = message.role === 'system';

    return (
      <div
        key={message.id}
        className={`flex gap-2 mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}
      >
        {!isUser && (
          <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isSystem ? 'bg-gray-700' : 'bg-blue-600'}`}>
            <Bot className="w-4 h-4 text-white" />
          </div>
        )}

        <div className={`max-w-[80%] ${isUser ? 'order-first' : ''}`}>
          <div
            className={`rounded-lg px-3 py-2 text-sm ${
              isUser
                ? 'bg-blue-600 text-white'
                : isSystem
                  ? 'bg-gray-800 text-gray-300 border border-gray-700'
                  : 'bg-gray-800 text-gray-100'
            }`}
          >
            <pre className="whitespace-pre-wrap font-sans">{message.content}</pre>

            {message.metadata && (
              <div className="mt-2 flex flex-wrap gap-1">
                {message.metadata.isToolStep && message.metadata.stepIndex !== undefined && (
                  <Badge variant="outline" className="text-xs font-mono">
                    Step {message.metadata.stepIndex + 1}
                  </Badge>
                )}
                {message.metadata.isToolStep && message.metadata.tool && (
                  <Badge variant="secondary" className="text-xs font-mono">
                    <Terminal className="w-3 h-3 mr-1" />
                    {message.metadata.tool}
                  </Badge>
                )}
                {!message.metadata.isToolStep && message.metadata.action && message.metadata.action !== 'intent' && message.metadata.action !== 'summary' && (
                  <Badge variant="outline" className="text-xs">
                    {message.metadata.action === 'click' && <MousePointer className="w-3 h-3 mr-1" />}
                    {message.metadata.action === 'read_screen' && <Eye className="w-3 h-3 mr-1" />}
                    {message.metadata.action === 'validate' && <Zap className="w-3 h-3 mr-1" />}
                    {message.metadata.action}
                  </Badge>
                )}
                {message.metadata.coordinates && (
                  <Badge variant="secondary" className="text-xs">
                    ({message.metadata.coordinates.x}, {message.metadata.coordinates.y})
                  </Badge>
                )}
                {message.metadata.status === 'processing' && (
                  <Badge variant="default" className="text-xs">
                    <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                    processing
                  </Badge>
                )}
                {message.metadata.status === 'failed' && (
                  <Badge variant="destructive" className="text-xs">
                    <XCircle className="w-3 h-3 mr-1" />
                    failed
                  </Badge>
                )}
                {message.metadata.isToolStep && message.metadata.status === 'completed' && (
                  <Badge variant="outline" className="text-xs text-green-400 border-green-600">
                    <CheckCircle className="w-3 h-3 mr-1" />
                    ok
                  </Badge>
                )}
              </div>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1 px-1">
            {message.timestamp.toLocaleTimeString()}
          </div>
        </div>

        {isUser && (
          <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center shrink-0">
            <User className="w-4 h-4 text-white" />
          </div>
        )}
      </div>
    );
  };

  return (
    <Card className={`flex flex-col h-full bg-gray-900 border-gray-800 ${className}`}>
      <CardHeader className="py-3 px-4 border-b border-gray-800">
        <CardTitle className="text-sm font-medium text-gray-200 flex items-center gap-2">
          <Bot className="w-4 h-4" />
          Intent Processing
          {isProcessing && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
        </CardTitle>
      </CardHeader>

      <CardContent className="flex-1 p-0 flex flex-col overflow-hidden">
        <ScrollArea className="flex-1 p-4" ref={scrollRef}>
          {messages.map(renderMessage)}
        </ScrollArea>

        {pendingApproval && (
          <div className="p-3 border-t border-yellow-800 bg-yellow-950/50">
            <div className="flex items-center gap-3">
              <div className="flex-1 text-sm text-yellow-200">
                <span className="font-semibold">{pendingApproval.tool}</span> requires your approval
              </div>
              <Button
                onClick={() => handleApproval(true)}
                className="bg-green-700 hover:bg-green-600 text-white px-4 py-1 text-sm"
                size="sm"
              >
                <CheckCircle className="w-4 h-4 mr-1" /> Approve
              </Button>
              <Button
                onClick={() => handleApproval(false)}
                className="bg-red-700 hover:bg-red-600 text-white px-4 py-1 text-sm"
                size="sm"
                variant="destructive"
              >
                <XCircle className="w-4 h-4 mr-1" /> Deny
              </Button>
            </div>
          </div>
        )}

        {pendingClickConfirm && (
          <div className="p-3 border-t border-blue-800 bg-blue-950/50">
            <div className="flex items-center gap-3">
              <MousePointer className="w-4 h-4 text-blue-400" />
              <div className="flex-1 text-sm text-blue-200">
                Klick auf <span className="font-semibold">"{pendingClickConfirm.element}"</span> bei ({pendingClickConfirm.x}, {pendingClickConfirm.y}) richtig?
                <span className="text-blue-400 ml-2">({pendingClickConfirm.confirmed}/{pendingClickConfirm.threshold})</span>
              </div>
              <Button
                onClick={() => handleClickConfirm(true)}
                className="bg-green-700 hover:bg-green-600 text-white px-4 py-1 text-sm"
                size="sm"
              >
                <CheckCircle className="w-4 h-4 mr-1" /> Richtig
              </Button>
              <Button
                onClick={() => handleClickConfirm(false)}
                className="bg-red-700 hover:bg-red-600 text-white px-4 py-1 text-sm"
                size="sm"
                variant="destructive"
              >
                <XCircle className="w-4 h-4 mr-1" /> Falsch
              </Button>
            </div>
          </div>
        )}

        <div className="p-3 border-t border-gray-800">
          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Type your intent... (e.g., 'click Submit button')"
              className="min-h-[60px] max-h-[120px] bg-gray-800 border-gray-700 text-gray-100 placeholder-gray-500 resize-none"
              disabled={isProcessing}
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isProcessing}
              className="h-[60px] px-4"
            >
              {isProcessing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default IntentChatPanel;
