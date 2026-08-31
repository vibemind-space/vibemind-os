'use client';

import { createContext, useContext, useState, ReactNode } from 'react';
import { HelpModal } from '@/components/common/help-modal';

interface HelpModalContextType {
    showHelpModal: () => void;
    hideHelpModal: () => void;
}

const HelpModalContext = createContext<HelpModalContextType | undefined>(undefined);

export function HelpModalProvider({ children }: { children: ReactNode }) {
    const [isOpen, setIsOpen] = useState(false);

    const showHelpModal = () => setIsOpen(true);
    const hideHelpModal = () => setIsOpen(false);

    const handleStartTour = () => {
        localStorage.removeItem('user_product_tour_completed');
        window.location.reload();
    };

    return (
        <HelpModalContext.Provider value={{ showHelpModal, hideHelpModal }}>
            {children}
            <HelpModal 
                isOpen={isOpen}
                onClose={hideHelpModal}
                onStartTour={handleStartTour}
            />
        </HelpModalContext.Provider>
    );
}

export function useHelpModal() {
    const context = useContext(HelpModalContext);
    if (context === undefined) {
        throw new Error('useHelpModal must be used within a HelpModalProvider');
    }
    return context;
} 