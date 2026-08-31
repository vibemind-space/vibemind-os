import { FileIcon, FilesIcon, FileTextIcon, GlobeIcon } from "lucide-react";

export function DataSourceIcon({
    type = undefined,
    size = "sm",
}: {
    type?: "crawl" | "urls" | "files" | "text" | undefined;
    size?: "sm" | "md";
}) {
    const sizeClass = size === "sm" ? "w-4 h-4" : "w-6 h-6";
    return <>
        {type === undefined && <FileIcon className={sizeClass} />}
        {type == "crawl" && <GlobeIcon className={sizeClass} />}
        {type == "urls" && <GlobeIcon className={sizeClass} />}
        {type == "files" && <FilesIcon className={sizeClass} />}
        {type == "text" && <FileTextIcon className={sizeClass} />}
    </>;
}
