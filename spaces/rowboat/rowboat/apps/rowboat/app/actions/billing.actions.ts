"use server";
import {
    authorize,
    logUsage as libLogUsage,
    getBillingCustomer,
    createCustomerPortalSession,
    getPrices as libGetPrices,
    updateSubscriptionPlan as libUpdateSubscriptionPlan,
    getEligibleModels as libGetEligibleModels
} from "../lib/billing";
import { authCheck } from "./auth.actions";
import { USE_BILLING } from "../lib/feature_flags";
import {
    AuthorizeRequest,
    AuthorizeResponse,
    LogUsageRequest,
    Customer,
    PricesResponse,
    SubscriptionPlan,
    UpdateSubscriptionPlanRequest,
    ModelsResponse
} from "../lib/types/billing_types";
import { z } from "zod";

export async function getCustomer(): Promise<z.infer<typeof Customer>> {
    const user = await authCheck();
    if (!user.billingCustomerId) {
        throw new Error("Customer not found");
    }
    const customer = await getBillingCustomer(user.billingCustomerId);
    if (!customer) {
        throw new Error("Customer not found");
    }
    return customer;
}

export async function authorizeUserAction(request: z.infer<typeof AuthorizeRequest>): Promise<z.infer<typeof AuthorizeResponse>> {
    if (!USE_BILLING) {
        return { success: true };
    }

    const customer = await getCustomer();
    const response = await authorize(customer.id, request);
    return response;
}

export async function logUsage(request: z.infer<typeof LogUsageRequest>) {
    if (!USE_BILLING) {
        return;
    }

    const customer = await getCustomer();
    await libLogUsage(customer.id, request);
    return;
}

export async function getCustomerPortalUrl(returnUrl: string): Promise<string> {
    if (!USE_BILLING) {
        throw new Error("Billing is not enabled")
    }

    const customer = await getCustomer();
    return await createCustomerPortalSession(customer.id, returnUrl);
}

export async function getPrices(): Promise<z.infer<typeof PricesResponse>> {
    if (!USE_BILLING) {
        throw new Error("Billing is not enabled");
    }

    const response = await libGetPrices();
    return response;
}

export async function updateSubscriptionPlan(plan: z.infer<typeof SubscriptionPlan>, returnUrl: string): Promise<string> {
    if (!USE_BILLING) {
        throw new Error("Billing is not enabled");
    }

    const customer = await getCustomer();
    const request: z.infer<typeof UpdateSubscriptionPlanRequest> = { plan, returnUrl };
    const url = await libUpdateSubscriptionPlan(customer.id, request);
    return url;
}

export async function getEligibleModels(): Promise<z.infer<typeof ModelsResponse> | "*"> {
    if (!USE_BILLING) {
        return "*";
    }

    const customer = await getCustomer();
    const response = await libGetEligibleModels(customer.id);
    return response;
}