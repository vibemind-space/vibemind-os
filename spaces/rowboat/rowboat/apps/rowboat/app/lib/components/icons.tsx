export function WorkflowIcon({
    size = 24,
    strokeWidth = 1,
}: {
    size?: number;
    strokeWidth?: number;
}) {
    return <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-workflow">
        <rect width="8" height="8" x="3" y="3" rx="2" />
        <path d="M7 11v4a2 2 0 0 0 2 2h4" />
        <rect width="8" height="8" x="13" y="13" rx="2" />
    </svg>;
}

export function HamburgerIcon({
    size = 24,
    strokeWidth = 1,
}: {
    size?: number;
    strokeWidth?: number;
}) {
    return <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-hamburger">
        <path d="M3 7h18" />
        <path d="M3 12h18" />
        <path d="M3 17h18" />
    </svg>;
}

export function BackIcon({
    size = 24,
    strokeWidth = 1,
}: {
    size?: number;
    strokeWidth?: number;
}) {
    return <svg width={size} height={size} aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} d="M5 12h14M5 12l4-4m-4 4 4 4"/>
    </svg>;
}