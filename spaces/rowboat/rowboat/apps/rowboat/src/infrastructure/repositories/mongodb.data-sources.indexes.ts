import { IndexDescription } from "mongodb";

export const DATA_SOURCES_COLLECTION = "sources";

export const DATA_SOURCES_INDEXES: IndexDescription[] = [
    { key: { projectId: 1, _id: -1 }, name: "projectId__id_desc" },
    { key: { status: 1, createdAt: 1 }, name: "status_createdAt" },
    { key: { status: 1, lastAttemptAt: 1, attempts: 1, createdAt: 1 }, name: "status_attempts_createdAt" },
];