import { Db } from "mongodb";
import { API_KEYS_COLLECTION } from "../repositories/mongodb.api-keys.indexes";
import { PROJECTS_COLLECTION } from "../repositories/mongodb.projects.indexes";
import { JOBS_COLLECTION } from "../repositories/mongodb.jobs.indexes";
import { CONVERSATIONS_COLLECTION } from "../repositories/mongodb.conversations.indexes";
import { DATA_SOURCES_COLLECTION } from "../repositories/mongodb.data-sources.indexes";
import { DATA_SOURCE_DOCS_COLLECTION } from "../repositories/mongodb.data-source-docs.indexes";
import { PROJECT_MEMBERS_COLLECTION } from "../repositories/mongodb.project-members.indexes";
import { RECURRING_JOB_RULES_COLLECTION } from "../repositories/mongodb.recurring-job-rules.indexes";
import { SCHEDULED_JOB_RULES_COLLECTION } from "../repositories/mongodb.scheduled-job-rules.indexes";
import { COMPOSIO_TRIGGER_DEPLOYMENTS_COLLECTION } from "../repositories/mongodb.composio-trigger-deployments.indexes";
import { USERS_COLLECTION } from "../repositories/mongodb.users.indexes";

export async function dropAllIndexes(database: Db): Promise<void> {
    const collections: string[] = [
        API_KEYS_COLLECTION,
        PROJECTS_COLLECTION,
        JOBS_COLLECTION,
        CONVERSATIONS_COLLECTION,
        DATA_SOURCES_COLLECTION,
        DATA_SOURCE_DOCS_COLLECTION,
        PROJECT_MEMBERS_COLLECTION,
        RECURRING_JOB_RULES_COLLECTION,
        SCHEDULED_JOB_RULES_COLLECTION,
        COMPOSIO_TRIGGER_DEPLOYMENTS_COLLECTION,
        USERS_COLLECTION,
    ];

    for (const collectionName of collections) {
        try {
            // Drops all non-_id indexes for the collection
            await database.collection(collectionName).dropIndexes();
        } catch (err: any) {
            // Ignore errors for non-existent collections or missing indexes
            const codeName = err?.codeName;
            const code = err?.code;
            const message: string | undefined = err?.message;

            if (
                codeName === "NamespaceNotFound" ||
                code === 26 || // NamespaceNotFound
                codeName === "IndexNotFound" ||
                (message && (message.includes("ns not found") || message.includes("index not found")))
            ) {
                continue;
            }

            throw err;
        }
    }
}