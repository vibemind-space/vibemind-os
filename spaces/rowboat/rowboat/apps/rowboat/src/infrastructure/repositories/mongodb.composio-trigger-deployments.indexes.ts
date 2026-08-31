import { IndexDescription } from "mongodb";

export const COMPOSIO_TRIGGER_DEPLOYMENTS_COLLECTION = "composio_trigger_deployments";

export const COMPOSIO_TRIGGER_DEPLOYMENTS_INDEXES: IndexDescription[] = [
    { key: { projectId: 1 }, name: "projectId_idx" },
    { key: { triggerId: 1 }, name: "triggerId_idx" },
    { key: { triggerTypeSlug: 1, connectedAccountId: 1 }, name: "triggerTypeSlug_connectedAccountId" },
];