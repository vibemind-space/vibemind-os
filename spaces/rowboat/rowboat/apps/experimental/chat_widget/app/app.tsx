"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { apiV1 } from "rowboat-shared";
import { z } from "zod";
import { Button, Dropdown, DropdownItem, DropdownMenu, DropdownTrigger, Textarea } from "@nextui-org/react";
import MarkdownContent from "./markdown-content";

type Message = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_call_id?: string;
  tool_name?: string;
}

function ChatWindowHeader({
  chatId,
  closeChat,
  closed,
  setMinimized,
}: {
  chatId: string | null;
  closeChat: () => Promise<void>;
  closed: boolean;
  setMinimized: (minimized: boolean) => void;
}) {
  return <div className="shrink-0 flex justify-between items-center gap-2 bg-gray-400 px-2 py-1 rounded-t-lg dark:bg-gray-800">
    <div className="text-gray-800 dark:text-white">Chat</div>
    <div className="flex gap-1 items-center">
      {(chatId && !closed) && <Dropdown>
        <DropdownTrigger>
          <button>
            <svg className="w-6 h-6 text-gray-800 dark:text-white" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeWidth="2" d="M6 12h.01m6 0h.01m5.99 0h.01" />
            </svg>
          </button>
        </DropdownTrigger>
        <DropdownMenu onAction={(key) => {
          if (key === "close") {
            closeChat();
          }
        }}>
          <DropdownItem key="close">
            Close chat
          </DropdownItem>
        </DropdownMenu>
      </Dropdown>}
      <button onClick={() => setMinimized(true)}>
        <svg className="w-6 h-6 text-gray-800 dark:text-white" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24">
          <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m19 9-7 7-7-7" />
        </svg>
      </button>
    </div>
  </div>
}

function LoadingAssistantResponse() {
  return <div className="flex gap-2 items-end">
    <div className="shrink-0 w-10 h-10 bg-gray-400 rounded-full dark:bg-gray-800"></div>
    <div className="bg-white rounded-md dark:bg-gray-800 text-gray-800 dark:text-white mr-[20%] rounded-bl-none p-2">
      <div className="flex gap-1">
        <div className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-600 animate-bounce"></div>
        <div className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-600 animate-bounce [animation-delay:0.2s]"></div>
        <div className="w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-600 animate-bounce [animation-delay:0.4s]"></div>
      </div>
    </div>
  </div>
}
function AssistantMessage({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="flex flex-col gap-1 items-start">
    <div className="text-gray-800 dark:text-white text-xs pl-2">Assistant</div>
    <div className="bg-gray-200 rounded-md dark:bg-gray-800 text-gray-800 dark:text-white mr-[20%] rounded-bl-none p-2">
      {typeof children === 'string' ? <MarkdownContent content={children} /> : children}
    </div>
  </div>
}

function UserMessage({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="flex flex-col gap-1 items-end">
    <div className="bg-gray-200 rounded-md dark:bg-gray-800 text-gray-800 dark:text-white ml-[20%] rounded-br-none p-2">
      {typeof children === 'string' ? <MarkdownContent content={children} /> : children}
    </div>
  </div>
}
function ChatWindowMessages({
  messages,
  loadingAssistantResponse,
}: {
  messages: Message[];
  loadingAssistantResponse: boolean;
}) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return <div className="flex flex-col grow p-2 gap-4 overflow-auto">
    <AssistantMessage>
      Hello! I&apos;m Rowboat, your personal assistant. How can I help you today?
    </AssistantMessage>
    {messages.map((message, index) => {
      switch (message.role) {
        case "user":
          return <UserMessage key={index}>{message.content}</UserMessage>;
        case "assistant":
          return <AssistantMessage key={index}>{message.content}</AssistantMessage>;
        case "system":
          return null; // Hide system messages from the UI
        case "tool":
          return <AssistantMessage key={index}>
            Tool response ({message.tool_name}): {message.content}
          </AssistantMessage>;
        default:
          return null;
      }
    })}
    {loadingAssistantResponse && <LoadingAssistantResponse />}
    <div ref={messagesEndRef} />
  </div>
}

function ChatWindowInput({
  handleUserMessage,
}: {
  handleUserMessage: (message: string) => Promise<void>;
}) {
  const [prompt, setPrompt] = useState<string>("");

  function handleInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      const input = prompt.trim();
      setPrompt('');

      handleUserMessage(input);
    }
  }

  return <div className="bg-white rounded-md dark:bg-gray-900 shrink-0 p-2">
    <Textarea
      placeholder="Ask me anything..."
      minRows={1}
      maxRows={3}
      variant="flat"
      className="w-full"
      onKeyDown={handleInputKeyDown}
      value={prompt}
      onValueChange={setPrompt}
    />
  </div>
}

function ChatWindowBody({
  chatId,
  createChat,
  getAssistantResponse,
  closed,
  resetState,
  messages,
  setMessages,
}: {
  chatId: string | null;
  createChat: () => Promise<string>;
  getAssistantResponse: (chatId: string, message: string) => Promise<Message>;
  closed: boolean;
  resetState: () => Promise<void>;
  messages: Message[];
  setMessages: (messages: Message[]) => void;
}) {
  const [loadingAssistantResponse, setLoadingAssistantResponse] = useState<boolean>(false);

  async function handleUserMessage(message: string) {
    const userMessage: Message = { role: "user", content: message };
    setMessages([...messages, userMessage]);
    setLoadingAssistantResponse(true);

    let availableChatId = chatId;
    if (!availableChatId) {
      availableChatId = await createChat();
    }

    const response = await getAssistantResponse(availableChatId, message);
    setMessages([...messages, userMessage, response]);
    setLoadingAssistantResponse(false);
  }

  return <div className="flex flex-col grow bg-white rounded-b-lg dark:bg-gray-900 overflow-auto">
    <ChatWindowMessages messages={messages} loadingAssistantResponse={loadingAssistantResponse} />
    {!closed && <ChatWindowInput
      handleUserMessage={handleUserMessage}
    />}
    {closed && <div className="flex flex-col items-center py-4 gap-2">
      <div className="text-gray-800 dark:text-white">This chat is closed</div>
      <Button
        onPress={resetState}
      >
        Start new chat
      </Button>
    </div>}
  </div>
}

function ChatWindow({
  chatId,
  closed,
  closeChat,
  createChat,
  getAssistantResponse,
  resetState,
  messages,
  setMessages,
  setMinimized,
}: {
  chatId: string | null;
  closed: boolean;
  closeChat: () => Promise<void>;
  createChat: () => Promise<string>;
  getAssistantResponse: (chatId: string, message: string) => Promise<Message>;
  resetState: () => Promise<void>;
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  setMinimized: (minimized: boolean) => void;
}) {
  return <div className="h-full flex flex-col rounded-lg overflow-hidden">
    <ChatWindowHeader
      chatId={chatId}
      closeChat={closeChat}
      closed={closed}
      setMinimized={setMinimized}
    />
    <ChatWindowBody
      chatId={chatId}
      createChat={createChat}
      getAssistantResponse={getAssistantResponse}
      closed={closed}
      resetState={resetState}
      messages={messages}
      setMessages={setMessages}
    />
  </div>
}

export function App({
  apiUrl,
}: {
  apiUrl: string;
}) {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [minimized, setMinimized] = useState(searchParams.get("minimized") === 'true');
  const [chatId, setChatId] = useState<string | null>(null);
  const [closed, setClosed] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);

  const fetchLastChat = useCallback(async (): Promise<{
    chat: z.infer<typeof apiV1.ApiGetChatsResponse.shape.chats.element>;
    messages: Message[];
  } | null> => {
    const response = await fetch(`${apiUrl}/chats`, {
      headers: {
        "Authorization": `Bearer ${sessionId}`,
      },
    });
    if (response.status === 403) {
      window.parent.postMessage({
        type: 'sessionExpired'
      }, '*');
      return null;
    }
    if (!response.ok) {
      throw new Error("Failed to fetch last chat");
    }
    const { chats }: z.infer<typeof apiV1.ApiGetChatsResponse> = await response.json();
    if (chats.length === 0) {
      return null;
    }
    const chat = chats[0];

    // fetch all chat messages
    let allMessages: Message[] = [];
    let nextCursor: string | undefined = undefined;

    do {
      const url = new URL(`${apiUrl}/chats/${chat.id}/messages`);
      if (nextCursor) {
        url.searchParams.set('next', nextCursor);
      }

      const messagesResponse = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${sessionId}`,
        },
      });
      if (!messagesResponse.ok) {
        throw new Error("Failed to fetch chat messages");
      }
      const { messages, next }: z.infer<typeof apiV1.ApiGetChatMessagesResponse> = await messagesResponse.json();
      
      const formattedMessages = messages.map(m => ({
        role: m.role,
        content: m.role === "assistant" ? (m.content || '') : m.content,
        ...(m.role === "tool" ? {
          tool_call_id: m.tool_call_id,
          tool_name: m.tool_name,
        } : {})
      }));
      
      allMessages = [...allMessages, ...formattedMessages];
      nextCursor = next;
    } while (nextCursor);

    return {
      chat,
      messages: allMessages,
    };
  }, [sessionId, apiUrl]);

  async function resetState() {
    setChatId(null);
    setClosed(false);
    setMessages([]);
  }

  async function closeChat() {
    const response = await fetch(`${apiUrl}/chats/${chatId}/close`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${sessionId}`,
      },
    });
    if (response.status === 403) {
      window.parent.postMessage({
        type: 'sessionExpired'
      }, '*');
      return;
    }
    if (!response.ok) {
      throw new Error("Failed to close chat");
    }
    setClosed(true);
  }

  async function createChat(): Promise<string> {
    const response = await fetch(`${apiUrl}/chats`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${sessionId}`,
      },
      body: JSON.stringify({}),
    });

    if (response.status === 403) {
      window.parent.postMessage({
        type: 'sessionExpired'
      }, '*');
      throw new Error("Session expired");
    }

    const { id }: z.infer<typeof apiV1.ApiCreateChatResponse> = await response.json();
    setChatId(id);
    return id;
  }

  async function getAssistantResponse(chatId: string, message: string): Promise<Message> {
    const response = await fetch(`${apiUrl}/chats/${chatId}/turn`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${sessionId}`,
      },
      body: JSON.stringify({
        message: message,
      }),
    });
    if (response.status === 403) {
      window.parent.postMessage({
        type: 'sessionExpired'
      }, '*');
      throw new Error("Session expired");
    }
    if (!response.ok) {
      throw new Error("Failed to get assistant response");
    }
    const { content }: z.infer<typeof apiV1.ApiChatTurnResponse> = await response.json();
    return {
      role: "assistant",
      content: content || '',
    };
  }

  useEffect(() => {
    window.parent.postMessage({
      type: 'chatStateChange',
      isMinimized: minimized
    }, '*');
  }, [minimized]);

  useEffect(() => {
    let abort = false;
    async function process(){
      const lastChat = await fetchLastChat();
      if (abort) {
        return;
      }
      if (lastChat) {
        setChatId(lastChat.chat.id);
        setClosed(lastChat.chat.closed || false);
        setMessages(lastChat.messages);
      }
    }
    process()
      .finally(() => {
        if (!abort) {
          window.parent.postMessage({
            type: 'chatLoaded',
          }, '*');
        }
      });

    return () => {
      abort = true;
    }
  }, [sessionId, fetchLastChat]);

  if (!sessionId) {
    return <></>;
  }

  return <>
    {minimized && <div className="fixed bottom-0 right-0">
      <button
        onClick={() => setMinimized(false)}
        className="w-12 h-12 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 rounded-full flex items-center justify-center shadow-lg transition-colors"
      >
        <svg className="w-6 h-6 text-gray-800 dark:text-white" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24">
          <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17h6l3 3v-3h2V9h-2M4 4h11v8H9l-3 3v-3H4V4Z" />
        </svg>
      </button>
    </div>}
    {!minimized && <div className="fixed h-full">
      <ChatWindow
        key={sessionId}
        chatId={chatId}
        closed={closed}
        closeChat={closeChat}
        createChat={createChat}
        getAssistantResponse={getAssistantResponse}
        resetState={resetState}
        messages={messages}
        setMessages={setMessages}
        setMinimized={setMinimized}
      />
    </div>}
  </>
}