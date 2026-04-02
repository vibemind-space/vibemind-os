export function UrlList({ urls }: { urls: string }) {
    return <pre className="max-w-[450px] border p-1 border-gray-300 rounded overflow-auto min-h-7 max-h-52 text-nowrap">
        {urls}
    </pre>;
}

export function TableLabel({ children, className }: { children: React.ReactNode, className?: string }) {
    return <th className={`font-medium text-gray-800 text-left align-top pr-4 py-4 ${className}`}>{children}</th>;
}

export function TableValue({ children, className }: { children: React.ReactNode, className?: string }) {
    return <td className={`align-top py-4 ${className}`}>{children}</td>;
}