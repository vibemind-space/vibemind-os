import { IndexDescription } from "mongodb";

export const PROJECTS_COLLECTION = "projects";

export const PROJECTS_INDEXES: IndexDescription[] = [
    { key: { createdByUserId: 1 }, name: "createdByUserId_idx" },
];