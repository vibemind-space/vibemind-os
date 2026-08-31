import { z } from 'zod';
import { Customer, AuthorizeRequest, AuthorizeResponse, LogUsageRequest, UsageResponse, CustomerPortalSessionResponse, PricesResponse, UpdateSubscriptionPlanRequest, UpdateSubscriptionPlanResponse, ModelsResponse, UsageItem } from './types/billing_types';
import { redirect } from 'next/navigation';
import { getUserFromSessionId, requireAuth } from './auth';
import { USE_BILLING } from './feature_flags';
import { container } from '@/di/container';
import { IProjectsRepository } from '@/src/application/repositories/projects.repository.interface';
import { IUsersRepository } from '@/src/application/repositories/users.repository.interface';

const BILLING_API_URL = process.env.BILLING_API_URL || 'http://billing';
const BILLING_API_KEY = process.env.BILLING_API_KEY || 'test';

let logCounter = 1;

const GUEST_BILLING_CUSTOMER = {
    id: "guest-user",
    userId: "guest-user",
    name: "Guest",
    email: "guest@rowboatlabs.com",
    stripeCustomerId: "guest",
    stripeSubscriptionId: "test",
    subscriptionPlan: "free" as const,
    subscriptionStatus: "active" as const,
    createdAt: new Date().toISOString(),
};


export class UsageTracker{
    private items: z.infer<typeof UsageItem>[] = [];

    track(item: z.infer<typeof UsageItem>) {
        this.items.push(item);
    }

    flush(): z.infer<typeof UsageItem>[] {
        const items = this.items;
        this.items = [];
        return items;
    }
}

export async function getCustomerForUserId(userId: string): Promise<z.infer<typeof Customer> | null> {
    const usersRepository = container.resolve<IUsersRepository>("usersRepository");

    const user = await usersRepository.fetch(userId);
    if (!user) {
        throw new Error("User not found");
    }
    if (!user.billingCustomerId) {
        return null;
    }
    return await getBillingCustomer(user.billingCustomerId);
}

export async function getCustomerIdForProject(projectId: string): Promise<string> {
    const projectsRepository = container.resolve<IProjectsRepository>('projectsRepository');
    const project = await projectsRepository.fetch(projectId);
    if (!project) {
        throw new Error("Project not found");
    }
    const customer = await getCustomerForUserId(project.createdByUserId);
    if (!customer) {
        throw new Error("User has no billing customer id");
    }
    return customer.id;
}

export async function getBillingCustomer(id: string): Promise<z.infer<typeof Customer> | null> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${id}`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        }
    });
    if (!response.ok) {
        throw new Error(`Failed to fetch billing customer: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = Customer.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse billing customer: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data;
}

async function createBillingCustomer(userId: string, email: string): Promise<z.infer<typeof Customer>> {
    const response = await fetch(`${BILLING_API_URL}/api/customers`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ userId, email })
    });
    if (!response.ok) {
        throw new Error(`Failed to create billing customer: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = Customer.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse billing customer: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data as z.infer<typeof Customer>;
}

export async function syncWithStripe(customerId: string): Promise<void> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/sync-with-stripe`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        }
    });
    if (!response.ok) {
        throw new Error(`Failed to sync with stripe: ${response.status} ${response.statusText} ${await response.text()}`);
    }
}

export async function authorize(customerId: string, request: z.infer<typeof AuthorizeRequest>): Promise<z.infer<typeof AuthorizeResponse>> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/authorize`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
    });
    if (!response.ok) {
        throw new Error(`Failed to authorize billing: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = AuthorizeResponse.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse authorize billing response: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data as z.infer<typeof AuthorizeResponse>;
}

export async function logUsage(customerId: string, request: z.infer<typeof LogUsageRequest>) {
    const reqId = logCounter++;
    console.log(`[${reqId}] logging billing usage for customer ${customerId} to ${BILLING_API_URL}`, reqId, JSON.stringify(request));
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/log-usage`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
    });
    console.log(`[${reqId}] completed logging billing usage for customer ${customerId}`, reqId, response.status, response.statusText);
    if (!response.ok) {
        throw new Error(`Failed to log usage: ${response.status} ${response.statusText} ${await response.text()}`);
    }
}

export async function getUsage(customerId: string): Promise<z.infer<typeof UsageResponse>> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/usage`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        }
    });
    if (!response.ok) {
        throw new Error(`Failed to get usage: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = UsageResponse.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse usage response: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data as z.infer<typeof UsageResponse>;
}

export async function createCustomerPortalSession(customerId: string, returnUrl: string): Promise<string> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/customer-portal-session`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ returnUrl })
    });
    if (!response.ok) {
        throw new Error(`Failed to get customer portal url: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = CustomerPortalSessionResponse.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse customer portal session response: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data.url;
}

export async function getPrices(): Promise<z.infer<typeof PricesResponse>> {
    const response = await fetch(`${BILLING_API_URL}/api/prices`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        }
    });
    if (!response.ok) {
        throw new Error(`Failed to get prices: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = PricesResponse.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse prices response: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data as z.infer<typeof PricesResponse>;
}

export async function updateSubscriptionPlan(customerId: string, request: z.infer<typeof UpdateSubscriptionPlanRequest>): Promise<string> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/update-sub-session`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
    });
    if (!response.ok) {
        throw new Error(`Failed to update subscription plan: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = UpdateSubscriptionPlanResponse.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse update subscription plan response: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data.url;
}

export async function getEligibleModels(customerId: string): Promise<z.infer<typeof ModelsResponse>> {
    const response = await fetch(`${BILLING_API_URL}/api/customers/${customerId}/models`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${BILLING_API_KEY}`,
            'Content-Type': 'application/json'
        }
    });
    if (!response.ok) {
        throw new Error(`Failed to get eligible models: ${response.status} ${response.statusText} ${await response.text()}`);
    }
    const json = await response.json();
    const parseResult = ModelsResponse.safeParse(json);
    if (!parseResult.success) {
        throw new Error(`Failed to parse eligible models response: ${JSON.stringify(parseResult.error)}`);
    }
    return parseResult.data as z.infer<typeof ModelsResponse>;
}

/**
 * This function should be used as an initial check in server page components to ensure
 * the user has a valid billing customer record. It will:
 * 1. Return a guest customer if billing is disabled
 * 2. Verify user authentication
 * 3. Create/update the user record if needed
 * 4. Redirect to onboarding if no billing customer exists
 *
 * Usage in server components:
 * ```ts
 * const billingCustomer = await requireBillingCustomer();
 * ```
 */
export async function requireBillingCustomer(): Promise<z.infer<typeof Customer>> {
    const user = await requireAuth();
    const usersRepository = container.resolve<IUsersRepository>("usersRepository");

    if (!USE_BILLING) {
        return {
            ...GUEST_BILLING_CUSTOMER,
            userId: user.id,
        };
    }

    // if user does not have an email, redirect to onboarding
    if (!user.email) {
        redirect('/onboarding');
    }

    // fetch or create customer
    let customer: z.infer<typeof Customer> | null;
    if (user.billingCustomerId) {
        customer = await getBillingCustomer(user.billingCustomerId);
    } else {
        customer = await createBillingCustomer(user.id, user.email);
        console.log("created billing customer", JSON.stringify({ userId: user.id, customer }));

        // update customer id in db
        await usersRepository.updateBillingCustomerId(user.id, customer.id);
    }
    if (!customer) {
        throw new Error("Failed to fetch or create billing customer");
    }

    return customer;
}

/**
 * This function should be used in server page components to ensure the user has an active
 * billing subscription. It will:
 * 1. Return a guest customer if billing is disabled
 * 2. Verify the user has a valid billing customer record
 * 3. Redirect to checkout if the subscription is not active
 *
 * Usage in server components:
 * ```ts
 * const billingCustomer = await requireActiveBillingSubscription();
 * ```
 */
export async function requireActiveBillingSubscription(): Promise<z.infer<typeof Customer>> {
    const billingCustomer = await requireBillingCustomer();

    if (USE_BILLING && billingCustomer.subscriptionStatus !== "active" && billingCustomer.subscriptionStatus !== "past_due") {
        redirect('/billing');
    }
    return billingCustomer;
}