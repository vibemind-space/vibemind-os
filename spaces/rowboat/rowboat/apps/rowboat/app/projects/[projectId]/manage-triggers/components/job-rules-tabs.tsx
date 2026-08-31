'use client';

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs, Tab } from "@/components/ui/tabs";
import { ScheduledJobRulesList } from "../scheduled/components/scheduled-job-rules-list";
import { RecurringJobRulesList } from "./recurring-job-rules-list";
import { TriggersTab } from "./triggers-tab";

export function JobRulesTabs({ projectId }: { projectId: string }) {
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const initialTab = (searchParams.get('tab') ?? 'triggers');
    const [activeTab, setActiveTab] = useState<string>(initialTab);

    const handleTabChange = (key: React.Key) => {
        const nextTab = key.toString();
        setActiveTab(nextTab);
        const params = new URLSearchParams(searchParams.toString());
        params.set('tab', nextTab);
        router.replace(`${pathname}?${params.toString()}`);
    };

    useEffect(() => {
        const current = searchParams.get('tab') ?? 'triggers';
        if (current !== activeTab) {
            setActiveTab(current);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchParams]);

    return (
        <div className="h-full flex flex-col">
            <Tabs
                selectedKey={activeTab}
                onSelectionChange={handleTabChange}
                aria-label="Job Rules"
                fullWidth
            >
                <Tab key="triggers" title="External Triggers">
                    <TriggersTab projectId={projectId} />
                </Tab>
                <Tab key="scheduled" title="One-Time Triggers">
                    <ScheduledJobRulesList projectId={projectId} />
                </Tab>
                <Tab key="recurring" title="Recurring Triggers">
                    <RecurringJobRulesList projectId={projectId} />
                </Tab>
            </Tabs>
        </div>
    );
}
