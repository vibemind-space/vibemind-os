import { IndexDescription } from "mongodb";

export const PROJECT_MEMBERS_COLLECTION = "project_members";

export const PROJECT_MEMBERS_INDEXES: IndexDescription[] = [
    { key: { userId: 1, _id: -1 }, name: "userId__id_desc" },
    { key: { userId: 1, projectId: 1 }, name: "userId_projectId" },
];