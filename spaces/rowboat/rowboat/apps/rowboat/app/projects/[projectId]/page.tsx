import { redirect } from "next/navigation";
import { requireActiveBillingSubscription } from '@/app/lib/billing';

export default async function Page(
    props: {
        params: Promise<{ projectId: string }>
    }
) {
    const params = await props.params;
    await requireActiveBillingSubscription();
    redirect(`/projects/${params.projectId}/workflow`);
}