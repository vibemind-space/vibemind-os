import { CopyButton } from "@/components/common/copy-button";

export function CopyAsJsonButton({ onCopy }: { onCopy: () => void }) {
    return <div className="absolute top-0 right-0">
        <CopyButton
            onCopy={onCopy}
            label="Copy as JSON"
            successLabel="Copied"
        />
    </div>
}