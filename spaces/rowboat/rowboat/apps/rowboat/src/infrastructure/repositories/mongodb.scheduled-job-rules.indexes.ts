import { IndexDescription } from "mongodb";

export const SCHEDULED_JOB_RULES_COLLECTION = "scheduled_job_rules";

export const SCHEDULED_JOB_RULES_INDEXES: IndexDescription[] = [
    { key: { nextRunAt: 1, status: 1, workerId: 1 }, name: "nextRunAt_status_worker" },
    { key: { projectId: 1, _id: -1 }, name: "projectId__id_desc" },
];