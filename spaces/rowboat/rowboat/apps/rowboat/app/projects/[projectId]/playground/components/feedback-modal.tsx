'use client';
import { useState } from "react";
import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, Button, Textarea } from "@heroui/react";

interface FeedbackModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (feedback: string) => void;
    title?: string;
}

export function FeedbackModal({ isOpen, onClose, onSubmit, title = "Provide Feedback" }: FeedbackModalProps) {
    const [feedback, setFeedback] = useState("");

    const handleSubmit = () => {
        onSubmit(feedback);
        setFeedback("");
        onClose();
    };

    const handleCancel = () => {
        setFeedback("");
        onClose();
    };

    return (
        <Modal isOpen={isOpen} onClose={handleCancel} size="md">
            <ModalContent className="feedback-modal">
                <ModalHeader className="flex flex-col gap-1">
                    {title}
                </ModalHeader>
                <p className="text-xs text-gray-600 dark:text-gray-400 px-6 pt-1 pb-0">
                    Tell Skipper what needs to be fixed
                </p>
                <ModalBody>
                    <div className="space-y-3">
                        <Textarea
                            placeholder="Describe the issue..."
                            value={feedback}
                            onChange={(e) => setFeedback(e.target.value)}
                            minRows={3}
                            maxRows={6}
                            className="w-full !text-xs focus:ring-0 focus:shadow-none focus:border-gray-300"
                        />
                    </div>
                </ModalBody>
                <ModalFooter>
                    <Button variant="bordered" onPress={handleCancel}>
                        Cancel
                    </Button>
                    <Button color="primary" onPress={handleSubmit}>
                        Submit
                    </Button>
                </ModalFooter>
            </ModalContent>
        </Modal>
    );
} 