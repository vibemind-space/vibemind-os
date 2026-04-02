'use client';

import { Progress, Badge, Chip, Spinner } from "@heroui/react";
import { Button } from "@/components/ui/button";
import { Label } from "@/app/lib/components/label";
import { Customer, UsageResponse } from "@/app/lib/types/billing_types";
import { z } from "zod";
import { tokens } from "@/app/styles/design-tokens";
import { SectionHeading } from "@/components/ui/section-heading";
import { HorizontalDivider } from "@/components/ui/horizontal-divider";
import clsx from 'clsx';
import { getCustomerPortalUrl } from "../actions/billing.actions";
import { useState } from "react";
import { ArrowUpCircle } from "lucide-react";
import { BillingUpgradeModal } from "@/components/common/billing-upgrade-modal";

const planDetails = {
    free: {
        name: "Free Plan",
        color: "default"
    },
    starter: {
        name: "Starter Plan",
        color: "primary"
    },
    pro: {
        name: "Pro Plan",
        color: "secondary"
    }
};

interface BillingPageProps {
    customer: z.infer<typeof Customer>;
    usage: z.infer<typeof UsageResponse>;
}

function getDisplayStatus(status: string | undefined) {
    if (status === "active") {
        return "Active";
    } else if (status === "past_due") {
        return "Past Due!";
    } else {
        return "Inactive";
    }
}

export function BillingPage({ customer, usage }: BillingPageProps) {
    const plan = customer.subscriptionPlan || "free";
    const displayStatus = getDisplayStatus(customer.subscriptionStatus);
    const planInfo = planDetails[plan];
    const [loading, setLoading] = useState(false);
    const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
    const [upgradeError, setUpgradeError] = useState("");

    // show friendly values for credits
    const sanctionedCredits = Math.floor(usage.sanctionedCredits / (10 ** 6));
    const availableCredits = Math.floor(usage.availableCredits / (10 ** 6));
    const usedCredits = Math.ceil((usage.sanctionedCredits - usage.availableCredits) / (10 ** 6));

    // Prepare usage metrics data
    const usageData = Object.entries(usage.usage)
        .map(([type, credits]) => ({
            type,
            credits,
            totalUsedCredits: usage.sanctionedCredits - usage.availableCredits
        }))
        .sort((a, b) => b.credits - a.credits);

    async function handleManageSubscription() {
        setLoading(true);
        const returnUrl = new URL('/billing/callback', window.location.origin);
        returnUrl.searchParams.set('redirect', window.location.href);
        const url = await getCustomerPortalUrl(returnUrl.toString());
        window.location.href = url;
    }

    return (
        <div className="max-w-4xl mx-auto px-8 py-8 space-y-8">
            <div className="px-4">
                <h1 className={clsx(
                    tokens.typography.sizes.xl,
                    tokens.typography.weights.semibold,
                    tokens.colors.light.text.primary,
                    tokens.colors.dark.text.primary
                )}>
                    Billing
                </h1>
            </div>

            {/* Subscription Status Panel */}
            <section className="card">
                <div className="px-4 pt-4 pb-6">
                    <SectionHeading>
                        Current Plan
                    </SectionHeading>
                </div>
                <HorizontalDivider />
                <div className="p-6 space-y-6">
                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <div className="flex items-center gap-2">
                                <h3 className={clsx(
                                    tokens.typography.sizes.lg,
                                    tokens.typography.weights.semibold,
                                    tokens.colors.light.text.primary,
                                    tokens.colors.dark.text.primary
                                )}>
                                    {planInfo.name}
                                </h3>
                                <Chip
                                    color={customer.subscriptionStatus === "active" ? "success" : "danger"}
                                    variant="flat"
                                    className="text-xs"
                                >
                                    {displayStatus}
                                </Chip>
                            </div>
                        </div>
                        <div className="flex flex-col items-end gap-2 min-w-[200px]">
                            {(plan === "free" || plan === "starter") && (
                                <Button
                                    variant="primary"
                                    size="lg"
                                    className="bg-gradient-to-r from-indigo-200 via-purple-200 to-pink-100 text-indigo-700 dark:text-indigo-200 shadow hover:from-indigo-300 hover:to-pink-200 rounded-md border border-indigo-200 dark:border-indigo-700"
                                    startContent={<ArrowUpCircle className="w-5 h-5" />}
                                    onClick={() => setUpgradeModalOpen(true)}
                                >
                                    Upgrade Now
                                </Button>
                            )}
                            {!loading && <a
                                href="#"
                                className="text-xs text-gray-500 underline hover:text-indigo-600 mt-1"
                                onClick={async (e) => {
                                    e.preventDefault();
                                    try {
                                        await handleManageSubscription();
                                    } catch (err) {
                                        setUpgradeError("Failed to open subscription portal");
                                    }
                                }}
                            >
                                Manage Subscription
                            </a>}
                            {loading && <Spinner size="sm" />}
                        </div>
                    </div>
                </div>
            </section>

            {/* Credits Overview Panel */}
            <section className="card">
                <div className="px-4 pt-4 pb-6">
                    <SectionHeading>
                        Credits Overview
                    </SectionHeading>
                </div>
                <HorizontalDivider />
                <div className="p-6 space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="space-y-2">
                            <Label label="Sanctioned Credits" />
                            <p className={clsx(
                                tokens.typography.sizes.lg,
                                tokens.typography.weights.semibold,
                                tokens.colors.light.text.primary,
                                tokens.colors.dark.text.primary
                            )}>
                                {sanctionedCredits.toLocaleString()}
                            </p>
                            <p className={clsx(
                                tokens.typography.sizes.sm,
                                tokens.colors.light.text.secondary,
                                tokens.colors.dark.text.secondary
                            )}>
                                Total credits allocated to your plan
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label label="Used Credits" />
                            <p className={clsx(
                                tokens.typography.sizes.lg,
                                tokens.typography.weights.semibold,
                                tokens.colors.light.text.primary,
                                tokens.colors.dark.text.primary
                            )}>
                                {usedCredits.toLocaleString()}
                            </p>
                            <p className={clsx(
                                tokens.typography.sizes.sm,
                                tokens.colors.light.text.secondary,
                                tokens.colors.dark.text.secondary
                            )}>
                                Credits consumed so far
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label label="Available Credits" />
                            <p className={clsx(
                                tokens.typography.sizes.lg,
                                tokens.typography.weights.semibold,
                                usage.availableCredits < 0 ? "text-red-500" : clsx(
                                    tokens.colors.light.text.primary,
                                    tokens.colors.dark.text.primary
                                )
                            )}>
                                {availableCredits.toLocaleString()}
                            </p>
                            <p className={clsx(
                                tokens.typography.sizes.sm,
                                tokens.colors.light.text.secondary,
                                tokens.colors.dark.text.secondary
                            )}>
                                Credits remaining for use
                            </p>
                        </div>
                    </div>
                    
                    {/* Warning for negative credits */}
                    {usage.availableCredits < 0 && (
                        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                            <p className={clsx(
                                tokens.typography.sizes.sm,
                                "text-red-700 dark:text-red-300"
                            )}>
                                ⚠️ You have exceeded your credit limit. Please upgrade your plan or contact support to avoid service interruptions.
                            </p>
                        </div>
                    )}
                    
                    {/* Warning for high credit usage (>80%) */}
                    {usage.availableCredits >= 0 && ((usage.sanctionedCredits - usage.availableCredits) / usage.sanctionedCredits) > 0.8 && (
                        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                            <p className={clsx(
                                tokens.typography.sizes.sm,
                                "text-yellow-700 dark:text-yellow-300"
                            )}>
                                ⚠️ You have used more than 80% of your credits. Consider upgrading your plan to avoid interruptions.
                            </p>
                        </div>
                    )}
                    
                    {/* Credits Progress Bar */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <Label label="Credits Usage" />
                            <span className={clsx(
                                tokens.typography.sizes.sm,
                                tokens.colors.light.text.secondary,
                                tokens.colors.dark.text.secondary
                            )}>
                                {Math.round(((usage.sanctionedCredits - usage.availableCredits) / usage.sanctionedCredits) * 100)}%
                            </span>
                        </div>
                        <Progress 
                            size="lg"
                            value={((usage.sanctionedCredits - usage.availableCredits) / usage.sanctionedCredits) * 100}
                            color={usage.availableCredits < 0 ? "danger" : "primary"}
                            className="h-4"
                            aria-label="Credits usage"
                        />
                    </div>
                </div>
            </section>

            {/* Usage Metrics Panel */}
            <section className="card">
                <div className="px-4 pt-4 pb-6">
                    <SectionHeading>
                        Usage split
                    </SectionHeading>
                </div>
                <HorizontalDivider />
                <div className="p-6 space-y-6">
                    {usageData.length === 0 ? (
                        <div className="text-center py-8">
                            <p className={clsx(
                                tokens.typography.sizes.sm,
                                tokens.colors.light.text.secondary,
                                tokens.colors.dark.text.secondary
                            )}>
                                No usage data yet
                            </p>
                        </div>
                    ) : (
                        usageData.map(({ type, credits, totalUsedCredits }) => {
                            const percentage = totalUsedCredits > 0 ? (credits / totalUsedCredits) * 100 : 0;

                            return (
                                <div key={type} className="space-y-2">
                                    <div className="flex justify-between items-center">
                                        <div className="space-y-1">
                                            <Label label={type.replace(/_/g, ' ')} />
                                            {/* <p className={clsx(
                                                tokens.typography.sizes.sm,
                                                tokens.colors.light.text.secondary,
                                                tokens.colors.dark.text.secondary
                                            )}>
                                                {credits.toLocaleString()} credits
                                            </p> */}
                                        </div>
                                        <span className={clsx(
                                            tokens.typography.sizes.sm,
                                            tokens.colors.light.text.secondary,
                                            tokens.colors.dark.text.secondary
                                        )}>
                                            {Math.round(percentage)}%
                                        </span>
                                    </div>
                                    <Progress 
                                        value={percentage}
                                        color="default"
                                        className="h-2"
                                        aria-label={`${type} credits usage`}
                                    />
                                </div>
                            );
                        })
                    )}
                </div>
            </section>
            <BillingUpgradeModal
                isOpen={upgradeModalOpen}
                onClose={() => setUpgradeModalOpen(false)}
                errorMessage={upgradeError}
            />
        </div>
    );
} 