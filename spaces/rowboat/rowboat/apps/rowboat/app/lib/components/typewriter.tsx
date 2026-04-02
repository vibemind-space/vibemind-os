"use client";

import { useState, useEffect } from "react";

const phrases = [
    "Can you help me choose the right product?",
    "Which plan is right for me?",
    "Do you have a discount code available?",
    "How do I get early access?",
    "Can you explain the charges?",
];

export function TypewriterEffect() {
    const [displayText, setDisplayText] = useState("");
    const [index, setIndex] = useState(0);
    const [phraseIndex, setPhraseIndex] = useState(0);
    const [isTyping, setIsTyping] = useState(true);

    useEffect(() => {
        let timer: NodeJS.Timeout;
        const currentPhrase = phrases[phraseIndex];

        if (isTyping) {
            if (index < currentPhrase.length) {
                timer = setTimeout(() => {
                    setDisplayText((prev) => prev + currentPhrase[index]);
                    setIndex((prev) => prev + 1);
                }, 20);
            } else {
                // Pause at the end
                timer = setTimeout(() => setIsTyping(false), 2000);
            }
        } else {
            if (index > 0) {
                timer = setTimeout(() => {
                    setDisplayText((prev) => prev.slice(0, -1));
                    setIndex((prev) => prev - 1);
                }, 10);
            } else {
                // Move to next phrase
                setPhraseIndex((prev) => (prev + 1) % phrases.length);
                setIsTyping(true);
            }
        }

        return () => clearTimeout(timer);
    }, [index, isTyping, phraseIndex]);

    return <div className="mb-8 font-semibold text-md md:text-xl lg:text-2xl leading-tight tracking-tight px-4 py-2">
        {displayText}
    </div>;
};