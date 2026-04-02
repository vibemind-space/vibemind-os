'use client';
import { useRef, useState } from "react";
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";

interface ProfileContextBoxProps {
    content: string;
    onChange: (content: string) => void;
    locked?: boolean;
}

export function ProfileContextBox({
    content,
    onChange,
    locked = false,
}: ProfileContextBoxProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Calculate the content height (number of lines * line height + padding)
    const getContentHeight = () => {
        if (!content) return 'auto';
        const lineCount = content.split('\n').length;
        const minHeight = 40; // minimum height in pixels
        const lineHeight = 20; // approximate line height in pixels
        const height = Math.max(minHeight, Math.min(300, lineCount * lineHeight + 32)); // 32px for padding
        return `${height}px`;
    };

    return (
        <div className="text-sm border border-gray-200 dark:border-[#2a2d31] rounded-lg">
            <div 
                className={`flex items-center gap-2 cursor-pointer text-gray-500 dark:text-gray-400 
                    hover:text-gray-700 dark:hover:text-gray-300
                    px-3 py-2 bg-transparent dark:bg-[#1e2023]
                    ${isExpanded ? 'border-b border-gray-200 dark:border-[#2a2d31]' : ''}`}
                onClick={() => setIsExpanded(!isExpanded)}
            >
                {isExpanded ? (
                    <ChevronDownIcon className="w-4 h-4" />
                ) : (
                    <ChevronRightIcon className="w-4 h-4" />
                )}
                <span className="font-medium">Profile Context</span>
            </div>
            {isExpanded && (
                <Textarea
                    ref={textareaRef}
                    value={content}
                    readOnly
                    disabled
                    placeholder="Select a test profile to provide context"
                    style={{ height: getContentHeight() }}
                    className="border-0 rounded-none cursor-not-allowed 
                        bg-gray-50 dark:bg-[#1e2023]
                        [&::-webkit-scrollbar]{width:6px}
                        [&::-webkit-scrollbar-track]{background:transparent}
                        [&::-webkit-scrollbar-thumb]{background-color:rgb(156 163 175)}
                        dark:[&::-webkit-scrollbar-thumb]{background-color:#2a2d31}
                        overflow-y-auto
                        placeholder:px-3 placeholder:pt-3"
                />
            )}
        </div>
    );
}
