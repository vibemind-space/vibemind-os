import clsx from 'clsx';

interface HorizontalDividerProps {
    className?: string;
}

export function HorizontalDivider({ className }: HorizontalDividerProps) {
    return (
        <div className={clsx(
            "border-t border-gray-200 dark:border-gray-700",
            className
        )} />
    );
}
