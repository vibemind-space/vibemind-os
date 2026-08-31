'use client';

import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, Button } from "@heroui/react";
import { AlertTriangle } from "lucide-react";

export interface ProjectWideChangeConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  confirmationQuestion: string;
  confirmButtonText?: string;
  isLoading?: boolean;
  disabled?: boolean;
}

export function ProjectWideChangeConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  confirmationQuestion,
  confirmButtonText = "Confirm",
  isLoading = false,
  disabled = false,
}: ProjectWideChangeConfirmationModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <ModalContent>
        <ModalHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-orange-600" />
            <span>{title}</span>
          </div>
        </ModalHeader>
        <ModalBody>
          <div className="space-y-4">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {confirmationQuestion}
            </p>
            
            <div className="bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <div className="w-5 h-5 rounded-full bg-orange-500 flex items-center justify-center text-xs font-medium text-white mt-0.5">
                  ⚠️
                </div>
                <div className="text-sm">
                  <p className="font-medium text-orange-800 dark:text-orange-200 mb-1">
                    This change will affect the deployed (Live) workflow as well!
                  </p>
                </div>
              </div>
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="light"
            onPress={onClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            color="primary"
            onPress={onConfirm}
            disabled={disabled || isLoading}
            isLoading={isLoading}
          >
            {confirmButtonText}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
} 