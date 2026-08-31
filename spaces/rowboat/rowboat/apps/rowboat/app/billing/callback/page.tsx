import { syncWithStripe } from "@/app/lib/billing";
import { requireBillingCustomer } from '@/app/lib/billing';
import { redirect } from "next/navigation";

export const dynamic = 'force-dynamic';

export default async function Page(
    props: {
        searchParams: Promise<{
            redirect: string;
        }>
    }
) {
    const searchParams = await props.searchParams;
    const customer = await requireBillingCustomer();
    await syncWithStripe(customer.id);
    const redirectUrl = searchParams.redirect as string;
    redirect(redirectUrl || '/projects');
}