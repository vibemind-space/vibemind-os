import { QuotaExceededError } from "@/src/entities/errors/common";

export interface IUsageQuotaPolicy {
    /**
     * Asserts that the project has not exceeded its usage quota and consumes the action.
     * Used for general project actions.
     * 
     * @param projectId - The ID of the project to assert and consume.
     * @throws QuotaExceededError if the quota is exceeded.
     */
    assertAndConsumeProjectAction(projectId: string): Promise<void>;


    /**
     * Asserts that the project has not exceeded its usage quota for running jobs.
     * 
     * @param projectId - The ID of the project to assert and consume.
     * @throws QuotaExceededError if the quota is exceeded.
     */
    assertAndConsumeRunJobAction(projectId: string): Promise<void>;
}