import { IndexDescription } from "mongodb";

export const RECURRING_JOB_RULES_COLLECTION = "recurring_job_rules";

export const RECURRING_JOB_RULES_INDEXES: IndexDescription[] = [
    { key: { nextRunAt: 1, workerId: 1, disabled: 1 }, name: "nextRunAt_worker_disabled" },
    { key: { projectId: 1, _id: -1 }, name: "projectId__id_desc" },
];