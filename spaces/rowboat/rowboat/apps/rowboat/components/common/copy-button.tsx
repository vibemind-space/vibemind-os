'use client';
import { Button } from "@/components/ui/button";
import { CopyIcon, CheckIcon } from "lucide-react";
import { useState } from "react";

export function CopyButton({
    onCopy,
    label,
    successLabel,
}: {
    onCopy: () => void;
    label: string;
    successLabel: string;
}) {
    const [showCopySuccess, setShowCopySuccess] = useState(false);
    
    const handleCopy = () => {
        onCopy();
        setShowCopySuccess(true);
        setTimeout(() => {
            setShowCopySuccess(false);
        }, 500);
    }

    return (
        <Button
            variant="secondary"
            size="sm"
            onClick={handleCopy}
            className="gap-2"
            showHoverContent
            hoverContent={showCopySuccess ? successLabel : label}
        >
            {showCopySuccess ? (
                <CheckIcon className="h-4 w-4" />
            ) : (
                <CopyIcon className="h-4 w-4" />
            )}
        </Button>
    );
}