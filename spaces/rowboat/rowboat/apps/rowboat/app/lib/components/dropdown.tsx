import { Select, SelectItem, Button } from "@heroui/react";
import { ReactNode } from "react";

export interface DropdownOption {
    key: string;
    label: string;
}

interface DropdownProps {
    options: DropdownOption[];
    value?: string;
    onChange: (value: string) => void;
    className?: string;
    placeholder?: string;
}

export function Dropdown({
    options,
    value,
    onChange,
    className = "w-60",
    placeholder
}: DropdownProps) {
    return (
        <Select
            variant="bordered"
            selectedKeys={value ? [value] : []}
            size="sm"
            className={className}
            onSelectionChange={(keys) => onChange(keys.currentKey as string)}
            placeholder={placeholder}
        >
            {options.map((option) => (
                <SelectItem key={option.key}>
                    {option.label}
                </SelectItem>
            ))}
        </Select>
    );
}
