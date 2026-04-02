export const getPaneClasses = (isActive: boolean, otherIsActive: boolean) => [
    "transition-all duration-300",
    isActive ? "scale-[1.02] shadow-xl relative z-10" : "",
    otherIsActive ? "scale-[0.98] opacity-50" : ""
]; 