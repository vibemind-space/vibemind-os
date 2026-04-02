import clsx from 'clsx';
import { TextareaHTMLAttributes, forwardRef, useEffect, useRef, useState, useCallback } from "react";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  autoResize?: boolean;
  maxHeight?: number;
  useValidation?: boolean;
  validate?: (value: string) => { valid: boolean; errorMessage?: string };
  onValidatedChange?: (value: string) => void;
  updateOnBlur?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(({
  className,
  label,
  autoResize = false,
  maxHeight = 120, // default max height (roughly 5 lines)
  value: propValue,
  onChange,
  // New validation props
  useValidation = false,
  validate,
  onValidatedChange,
  updateOnBlur = false,
  onBlur,
  onKeyDown,
  ...props
}, ref) => {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = (ref as any) || internalRef;
  const adjustHeightTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // Local state for validation mode
  const [localValue, setLocalValue] = useState(propValue as string);
  const [validationError, setValidationError] = useState<string | undefined>();
  const [isEditing, setIsEditing] = useState(false);

  // update local value when prop value changes
  useEffect(() => {
    setLocalValue(propValue as string);
  }, [propValue]);

  // Sync local state with prop value when not editing
  useEffect(() => {
    if (!isEditing) {
      setLocalValue(propValue as string);
    }
  }, [propValue, isEditing]);

  // Debounced adjustHeight function to prevent interference during rapid state changes
  const debouncedAdjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea || !autoResize) return;

    // Clear any pending timeout
    if (adjustHeightTimeoutRef.current) {
      clearTimeout(adjustHeightTimeoutRef.current);
    }

    // Debounce the height adjustment to prevent interference during rapid changes
    adjustHeightTimeoutRef.current = setTimeout(() => {
      // Store current focus state
      const hadFocus = document.activeElement === textarea;
      const selectionStart = textarea.selectionStart;
      const selectionEnd = textarea.selectionEnd;
      
      // Only adjust if the textarea is properly mounted and not currently being focused
      if (textarea.offsetParent === null) return;
      
      // Prevent adjustment during focus events to avoid disruption
      requestAnimationFrame(() => {
        textarea.style.height = 'auto';
        const scrollHeight = textarea.scrollHeight;
        textarea.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
        
        // Add scrolling if content exceeds maxHeight
        textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
        
        // Restore focus and selection if it was focused before
        if (hadFocus && document.activeElement !== textarea) {
          textarea.focus();
          textarea.setSelectionRange(selectionStart, selectionEnd);
        }
      });
    }, 10); // Small debounce delay
  }, [autoResize, maxHeight, textareaRef]);

  useEffect(() => {
    debouncedAdjustHeight();
    
    // Add window resize listener
    window.addEventListener('resize', debouncedAdjustHeight);
    return () => {
      window.removeEventListener('resize', debouncedAdjustHeight);
      // Clear timeout on cleanup
      if (adjustHeightTimeoutRef.current) {
        clearTimeout(adjustHeightTimeoutRef.current);
      }
    };
  }, [localValue, debouncedAdjustHeight]);

  const validateAndUpdate = (value: string) => {
    if (validate) {
      const result = validate(value);
      setValidationError(result.errorMessage);
      if (result.valid && onValidatedChange) {
        onValidatedChange(value);
        return true;
      }
      return false;
    } else if (onValidatedChange) {
      onValidatedChange(value);
      return true;
    }
    return false;
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setLocalValue(newValue);
    setIsEditing(true);

    if (!updateOnBlur) {
      if (useValidation) {
        validateAndUpdate(newValue);
      } else {
        onChange?.(e);
      }
    }
  };

  const handleBlur = (e: React.FocusEvent<HTMLTextAreaElement>) => {
    setIsEditing(false);
    if (updateOnBlur) {
      if (useValidation) {
        validateAndUpdate(localValue);
      } else {
        const syntheticEvent = {
          ...e,
          target: { ...e.target, value: localValue },
          currentTarget: { ...e.currentTarget, value: localValue }
        };
        onChange?.(syntheticEvent as any);
      }
    }
    onBlur?.(e);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (updateOnBlur && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      textareaRef.current?.blur();
    }
    onKeyDown?.(e);
  };

  return (
    <div className="space-y-2">
      {label && (
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
        </label>
      )}
      <textarea
        ref={textareaRef}
        onChange={handleChange}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        value={localValue}
        className={clsx(
          "flex w-full text-sm focus-visible:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "transition-colors",
          className
        )}
        style={{
          ...props.style,
          minHeight: autoResize ? '24px' : undefined,
        }}
        {...props}
      />
    </div>
  );
});

Textarea.displayName = "Textarea"; 