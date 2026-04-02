'use client';

import { useFormStatus } from "react-dom";
import { Button } from "@/components/ui/button";
import { ButtonHTMLAttributes } from "react";

export function FormStatusButton({
    props
}: {
    props: ButtonHTMLAttributes<HTMLButtonElement> & {
        startContent?: React.ReactNode;
        endContent?: React.ReactNode;
        variant?: 'primary' | 'secondary' | 'tertiary';
        size?: 'sm' | 'md' | 'lg';
        isLoading?: boolean;
    };
}) {
    const { pending } = useFormStatus();

    return <Button {...props} isLoading={pending} />;
}