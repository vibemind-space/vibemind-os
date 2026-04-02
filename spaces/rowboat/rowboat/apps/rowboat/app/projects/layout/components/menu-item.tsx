import { LucideIcon } from "lucide-react";

interface MenuItemProps {
    icon: LucideIcon;
    selected?: boolean;
    collapsed?: boolean;
    children?: React.ReactNode;
}

export default function MenuItem({ 
    icon: Icon, 
    selected = false, 
    collapsed = false,
    children 
}: MenuItemProps) {
    return (
        <div
            className={`
                w-full px-3 py-2 rounded-md flex items-center gap-3
                text-sm font-medium transition-all duration-200
                ${selected 
                    ? 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10' 
                    : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
                }
            `}
        >
            <Icon size={16} />
            {!collapsed && children}
        </div>
    );
} 