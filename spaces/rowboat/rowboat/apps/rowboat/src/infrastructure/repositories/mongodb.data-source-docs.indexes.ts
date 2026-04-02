import { IndexDescription } from "mongodb";

export const DATA_SOURCE_DOCS_COLLECTION = "source_docs";

export const DATA_SOURCE_DOCS_INDEXES: IndexDescription[] = [
    { key: { sourceId: 1, status: 1, _id: -1 }, name: "sourceId_status__id_desc" },
    { key: { projectId: 1 }, name: "projectId_idx" },
];