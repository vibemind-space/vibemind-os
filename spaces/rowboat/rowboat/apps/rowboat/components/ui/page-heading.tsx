import clsx from 'clsx';
import { tokens } from "@/app/styles/design-tokens";

interface PageHeadingProps {
    title: string;
    description?: string;
}

export function PageHeading({ title, description }: PageHeadingProps) {
    return (
        <div>
            <h1 className={clsx(
                tokens.typography.weights.semibold,
                tokens.typography.sizes["2xl"],
                tokens.colors.light.text.primary,
                tokens.colors.dark.text.primary
            )}>
                {title}
            </h1>
            {description && (
                <p className={clsx(
                    "mt-2",
                    tokens.typography.sizes.base,
                    tokens.colors.light.text.secondary,
                    tokens.colors.dark.text.secondary
                )}>
                    {description}
                </p>
            )}
        </div>
    );
}
