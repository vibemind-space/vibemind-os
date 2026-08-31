import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, Spinner } from "@heroui/react";
import { Button } from "@/components/ui/button";
import { AlertCircle, CheckIcon } from "lucide-react";
import { getPrices, getCustomer, updateSubscriptionPlan } from "@/app/actions/billing.actions";
import { useEffect, useState } from "react";
import { PricesResponse, SubscriptionPlan } from "@/app/lib/types/billing_types";
import { z } from "zod";
import Link from "next/link";

interface BillingUpgradeModalProps {
    isOpen: boolean;
    onClose: () => void;
    errorMessage: string;
}

export function BillingUpgradeModal({ isOpen, onClose, errorMessage }: BillingUpgradeModalProps) {
    const [prices, setPrices] = useState<z.infer<typeof PricesResponse> | null>(null);
    const [loading, setLoading] = useState(false);
    const [currentPlan, setCurrentPlan] = useState<z.infer<typeof SubscriptionPlan> | null>(null);
    const [subscribingPlan, setSubscribingPlan] = useState<z.infer<typeof SubscriptionPlan> | null>(null);
    const [subscribeError, setSubscribeError] = useState<string | null>(null);

    useEffect(() => {
        let ignore = false;

        async function loadData() {
            try {
                setLoading(true);
                const [pricesResponse, customerResponse] = await Promise.all([
                    getPrices(),
                    getCustomer()
                ]);
                if (ignore) return;
                
                setPrices(pricesResponse);
                setCurrentPlan(customerResponse.subscriptionPlan || 'free');
            } catch (error) {
                console.error('Failed to load data:', error);
            } finally {
                setLoading(false);
            }
        }

        if (isOpen) {
            loadData();
        }

        return () => {
            ignore = true;
        }
    }, [isOpen]);

    async function handleSubscribe(plan: z.infer<typeof SubscriptionPlan>) {
        setSubscribingPlan(plan);
        setSubscribeError(null);
        try {
            // construct return url:
            // the return url is /billing/callback?redirect=<current url>
            const returnUrl = new URL('/billing/callback', window.location.origin);
            returnUrl.searchParams.set('redirect', window.location.href);
            console.log('returnUrl', returnUrl.toString());
            const url = await updateSubscriptionPlan(plan, returnUrl.toString());
            window.location.href = url;
        } catch (error) {
            console.error('Failed to upgrade:', error);
            setSubscribeError(error instanceof Error ? error.message : 'An unknown error occurred');
            setSubscribingPlan(null);
        }
    }

    const plans = [
        {
            name: "Starter",
            plan: "starter" as const,
            description: "Great for your personal projects",
            features: [
                "2,000 credits",
                "Latest models like gpt-5, claude-4 and others",
            ]
        },
        {
            name: "Pro",
            plan: "pro" as const,
            description: "Great for power users or teams",
            features: [
                "20,000 credits",
                "Priority support",
            ],
            recommended: true
        }
    ];

    const getVisiblePlans = () => {
        if (!currentPlan) return [];
        switch (currentPlan) {
            case 'free':
                return plans; // Show both starter and pro
            case 'starter':
                return plans.filter(p => p.plan === 'pro'); // Show only pro
            case 'pro':
                return []; // Show no plans
            default:
                return [];
        }
    };

    const getModalTitle = () => {
        if (currentPlan === 'pro') {
            return "You've reached your plan limits";
        }
        return "Upgrade to do more with Rowboat";
    };

    const visiblePlans = getVisiblePlans();

    return (
        <Modal 
            isOpen={isOpen} 
            onOpenChange={onClose}
            size="2xl"
            classNames={{
                base: "bg-white dark:bg-gray-900",
                header: "border-b border-gray-200 dark:border-gray-800",
                footer: "border-t border-gray-200 dark:border-gray-800",
            }}
        >
            <ModalContent>
                <ModalHeader className="flex gap-2 items-center">
                    <AlertCircle className="w-5 h-5 text-red-500" />
                    <span>{getModalTitle()}</span>
                </ModalHeader>
                <ModalBody>
                    <div className="space-y-6">
                        <div className="space-y-2">
                            <p className="text-gray-900 dark:text-gray-100">
                                {errorMessage}
                            </p>
                        </div>
                        
                        {loading ? (
                            <div className="flex justify-center">
                                <Spinner size="lg" />
                            </div>
                        ) : visiblePlans.length > 0 ? (
                            <div className={`grid grid-cols-1 ${visiblePlans.length > 1 ? 'md:grid-cols-2' : ''} gap-6`}>
                                {visiblePlans.map((plan) => (
                                    <div 
                                        key={plan.plan}
                                        className={`relative rounded-lg border p-6 ${
                                            plan.recommended 
                                                ? 'border-blue-500 bg-gray-50 dark:bg-gray-800' 
                                                : 'border-gray-200 dark:border-gray-700'
                                        }`}
                                    >
                                        {plan.recommended && (
                                            <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                                                <span className="px-3 py-1 text-sm font-medium bg-blue-100 text-blue-800 rounded-full">
                                                    Recommended
                                                </span>
                                            </div>
                                        )}
                                        <div className="space-y-4">
                                            <div>
                                                <h3 className="text-lg font-semibold">{plan.name}</h3>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">{plan.description}</p>
                                            </div>
                                            <div className="flex items-baseline">
                                                <span className="text-3xl font-bold">
                                                    ${((prices?.prices[plan.plan]?.monthly ?? 0) / 100)}
                                                </span>
                                                <span className="ml-1 text-gray-500 dark:text-gray-400">
                                                    /month
                                                </span>
                                            </div>
                                            <ul className="space-y-2">
                                                {plan.features.map((feature, index) => (
                                                    <li key={index} className="flex items-center gap-2">
                                                        <CheckIcon className="w-4 h-4 text-green-500" />
                                                        <span className="text-sm">{feature}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                            <Button
                                                className="w-full"
                                                size="lg"
                                                onClick={() => handleSubscribe(plan.plan)}
                                                disabled={subscribingPlan !== null}
                                                isLoading={subscribingPlan === plan.plan}
                                            >
                                                Subscribe
                                            </Button>
                                            {subscribeError && (
                                                <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                                                    {subscribeError}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : null}
                    </div>
                </ModalBody>
                <ModalFooter>
                    <Link 
                        href="/billing"
                        className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                    >
                        View usage
                    </Link>
                </ModalFooter>
            </ModalContent>
        </Modal>
    );
} 