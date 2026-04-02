'use client';

import { Button, Spinner } from "@heroui/react";
import { useRef, useState, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";

// Add a type to support both message formats
type FlexibleMessage = {
    role: 'user' | 'assistant' | 'system' | 'tool';
    content: string | any;
    version?: string;
    chatId?: string;
    createdAt?: string;
    // Add any other optional fields that might be needed
};

export function ComposeBox({
    minRows=3,
    disabled=false,
    loading=false,
    handleUserMessage,
    messages,
}: {
    minRows?: number;
    disabled?: boolean;
    loading?: boolean;
    handleUserMessage: (prompt: string) => void;
    messages: FlexibleMessage[];  // Use the flexible message type
}) {
    const [input, setInput] = useState('');
    const [isFocused, setIsFocused] = useState(false);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    function handleInput() {
        console.log('handleInput called');
        const prompt = input.trim();
        if (!prompt) {
            console.log('Prompt is empty, returning');
            return;
        }
        
        console.log('Clearing input');
        setInput('');
        if (inputRef.current) {
            inputRef.current.value = '';
        }
        
        console.log('Calling handleUserMessage with prompt:', prompt);
        handleUserMessage(prompt);
        console.log('handleInput completed');
    }

    function handleInputKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleInput();
        }
    }
    // focus on the input field
    useEffect(() => {
        if (inputRef.current) {
            inputRef.current.focus();
            inputRef.current.value = input; // Ensure sync with state
        }
    }, [messages, input]);

    useEffect(() => {
        console.log('Input state changed to:', input);
    }, [input]);

    return (
        <div className="relative group">
            {/* Keyboard shortcut hint */}
            <div className="absolute -top-6 right-0 text-xs text-gray-500 dark:text-gray-400 opacity-0 
                          group-hover:opacity-100 transition-opacity">
                Press ⌘ + Enter to send
            </div>

            {/* Outer container with padding */}
            <div className="rounded-2xl border-[1.5px] border-gray-200 dark:border-[#2a2d31] p-3 relative 
                          bg-white dark:bg-[#1e2023] flex items-end gap-2">
                {/* Textarea */}
                <div className="flex-1">
                    <Textarea
                        ref={inputRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleInputKeyDown}
                        onFocus={() => setIsFocused(true)}
                        onBlur={() => setIsFocused(false)}
                        disabled={disabled || loading}
                        placeholder="Type a message..."
                        autoResize={true}
                        maxHeight={120}
                        className={`
                            min-h-0!
                            border-0! shadow-none! ring-0!
                            bg-transparent
                            resize-none
                            overflow-y-auto
                            [&::-webkit-scrollbar]:w-1
                            [&::-webkit-scrollbar-track]:bg-transparent
                            [&::-webkit-scrollbar-thumb]:bg-gray-300
                            [&::-webkit-scrollbar-thumb]:dark:bg-[#2a2d31]
                            [&::-webkit-scrollbar-thumb]:rounded-full
                            placeholder:text-gray-500 dark:placeholder:text-gray-400
                        `}
                    />
                </div>

                {/* Send button */}
                <Button
                    size="sm"
                    isIconOnly
                    disabled={disabled || loading || !input.trim()}
                    onPress={handleInput}
                    className={`
                        transition-all duration-200
                        ${input.trim() 
                            ? 'bg-indigo-50 hover:bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:hover:bg-indigo-800/60 dark:text-indigo-300' 
                            : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500'
                        }
                        scale-100 hover:scale-105 active:scale-95
                        disabled:opacity-50 disabled:scale-95
                        hover:shadow-md dark:hover:shadow-indigo-950/10
                        mb-0.5
                    `}
                >
                    {loading ? (
                        <Spinner size="sm" color={input.trim() ? "primary" : "default"} />
                    ) : (
                        <SendIcon 
                            size={16} 
                            className={`transform transition-transform ${isFocused ? 'translate-x-0.5' : ''}`}
                        />
                    )}
                </Button>
            </div>
        </div>
    );
}

// Custom SendIcon component for better visual alignment
function SendIcon({ size, className }: { size: number, className?: string }) {
    return (
        <svg 
            width={size} 
            height={size} 
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="currentColor" 
            strokeWidth="2" 
            strokeLinecap="round" 
            strokeLinejoin="round"
            className={className}
        >
            <path d="M22 2L11 13" />
            <path d="M22 2L15 22L11 13L2 9L22 2Z" />
        </svg>
    );
}
