import { IndexDescription } from "mongodb";

export const JOBS_COLLECTION = "jobs";

export const JOBS_INDEXES: IndexDescription[] = [
    { key: { status: 1, workerId: 1, createdAt: 1 }, name: "status_workerId_createdAt" },
    { key: { projectId: 1, _id: -1 }, name: "projectId__id_desc" },
    { key: { status: 1, projectId: 1, _id: -1 }, name: "status_projectId__id_desc" },
    { key: { "reason.type": 1, "reason.ruleId": 1, _id: -1 }, name: "reason_rule__id_desc" },
    { key: { "reason.type": 1, "reason.triggerDeploymentId": 1, _id: -1 }, name: "reason_trigger__id_desc" },
];