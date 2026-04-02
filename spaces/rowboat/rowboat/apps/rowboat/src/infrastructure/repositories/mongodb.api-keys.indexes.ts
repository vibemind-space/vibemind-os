import { IndexDescription } from "mongodb";

export const API_KEYS_COLLECTION = "api_keys";

export const API_KEYS_INDEXES: IndexDescription[] = [
    { key: { projectId: 1, key: 1 }, name: "projectId_key" },
    { key: { projectId: 1, createdAt: -1 }, name: "projectId_createdAt_desc" },
];