import { IndexDescription } from "mongodb";

export const CONVERSATIONS_COLLECTION = "conversations";

export const CONVERSATIONS_INDEXES: IndexDescription[] = [
    { key: { projectId: 1, _id: -1 }, name: "projectId__id_desc" },
];