import { Select, SelectItem, SelectProps } from "@heroui/react";
import { ReactNode, ChangeEvent } from "react";

export interface DropdownOption {
  key: string;
  label: string;
  startContent?: ReactNode;
  endContent?: ReactNode;
}

interface DropdownProps extends Omit<SelectProps, 'children' | 'onChange'> {
  options: DropdownOption[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  width?: string | number;
  containerClassName?: string;
}

export function Dropdown({
  options,
  value,
  onChange,
  className = "",
  width = "100%",
  containerClassName = "",
  ...selectProps
}: DropdownProps) {
  return (
    <div className={`${containerClassName}`} style={{ width }}>
      <Select
        {...selectProps}
        selectedKeys={[value]}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
        className={`${className}`}
      >
        {options.map((option) => (
          <SelectItem
            key={option.key}
            startContent={option.startContent}
            endContent={option.endContent}
          >
            {option.label}
          </SelectItem>
        ))}
      </Select>
    </div>
  );
}
