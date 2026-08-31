import { Metadata } from "next";
import { requireActiveBillingSubscription } from '@/app/lib/billing';
import { ComposioTriggerDeploymentView } from "../../components/composio-trigger-deployment-view";

export const metadata: Metadata = {
    title: "External Trigger",
};

export default async function Page(
    props: {
        params: Promise<{ projectId: string; deploymentId: string }>
    }
) {
    const params = await props.params;
    await requireActiveBillingSubscription();
    return <ComposioTriggerDeploymentView projectId={params.projectId} deploymentId={params.deploymentId} />;
}


