import { SourcePage } from "./source-page";
import { requireActiveBillingSubscription } from '@/app/lib/billing';

export default async function Page(
    props: {
        params: Promise<{
            projectId: string,
            sourceId: string
        }>
    }
) {
    const params = await props.params;
    await requireActiveBillingSubscription();
    return <SourcePage projectId={params.projectId} sourceId={params.sourceId} />;
}