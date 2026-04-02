import { PaginatedList } from "@/src/entities/common/paginated-list";
import { ApiKey } from "@/src/entities/models/api-key";
import { z } from "zod";

export const CreateSchema = ApiKey.pick({
    projectId: true,
    key: true,
});

// Interface for repository operations related to API keys.
export interface IApiKeysRepository {
    /**
     * Creates a new API key for a given project.
     * @param data - The data required to create an API key (projectId and key).
     * @returns The created ApiKey object.
     */
    create(data: z.infer<typeof CreateSchema>): Promise<z.infer<typeof ApiKey>>;

    /**
     * Lists all API keys for a given project.
     * @param projectId - The ID of the project whose API keys are to be listed.
     * @returns A list of ApiKey objects.
     */
    listAll(projectId: string): Promise<z.infer<typeof ApiKey>[]>;

    /**
     * Deletes an API key by its ID for a given project.
     * @param projectId - The ID of the project.
     * @param id - The ID of the API key to delete.
     * @returns True if the key was deleted, false if not found.
     */
    delete(projectId: string, id: string): Promise<boolean>;

    /**
     * Deletes all API keys for a given project.
     * @param projectId - The ID of the project.
     */
    deleteAll(projectId: string): Promise<void>;

    /**
     * Checks if an API key is valid for a project and consumes it (e.g., for rate limiting or one-time use).
     * @param projectId - The ID of the project.
     * @param apiKey - The API key to check and consume.
     * @returns True if the key is valid and was consumed, false otherwise.
     */
    checkAndConsumeKey(projectId: string, apiKey: string): Promise<boolean>;
}