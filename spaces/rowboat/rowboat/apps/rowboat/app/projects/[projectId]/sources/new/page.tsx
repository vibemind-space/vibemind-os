import { Metadata } from "next";
import { Form } from "./form";
import { redirect } from "next/navigation";
import { USE_RAG, USE_RAG_UPLOADS, USE_RAG_S3_UPLOADS, USE_RAG_SCRAPING } from "../../../../lib/feature_flags";
import { requireActiveBillingSubscription } from '@/app/lib/billing';

export const metadata: Metadata = {
    title: "Add data source"
}

export default async function Page(
    props: {
        params: Promise<{ projectId: string }>
    }
) {
    const params = await props.params;
    await requireActiveBillingSubscription();
    if (!USE_RAG) {
        redirect(`/projects/${params.projectId}`);
    }

    return (
        <Form
            projectId={params.projectId}
            useRagUploads={USE_RAG_UPLOADS}
            useRagS3Uploads={USE_RAG_S3_UPLOADS}
            useRagScraping={USE_RAG_SCRAPING}
        />
    );
}