import { IApiKeysRepository } from "@/src/application/repositories/api-keys.repository.interface";
import { z } from "zod";
import { IProjectActionAuthorizationPolicy } from "@/src/application/policies/project-action-authorization.policy";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    projectId: z.string(),
    id: z.string(),
});

export interface IDeleteApiKeyUseCase {
    execute(data: z.infer<typeof inputSchema>): Promise<boolean>;
}

export class DeleteApiKeyUseCase implements IDeleteApiKeyUseCase {
    private readonly apiKeysRepository: IApiKeysRepository;
    private readonly projectActionAuthorizationPolicy: IProjectActionAuthorizationPolicy;

    constructor({
        apiKeysRepository,
        projectActionAuthorizationPolicy,
    }: {
        apiKeysRepository: IApiKeysRepository,
        projectActionAuthorizationPolicy: IProjectActionAuthorizationPolicy,
    }) {
        this.apiKeysRepository = apiKeysRepository;
        this.projectActionAuthorizationPolicy = projectActionAuthorizationPolicy;
    }

    async execute(data: z.infer<typeof inputSchema>): Promise<boolean> {
        const { caller, userId, apiKey, projectId, id } = data;
        await this.projectActionAuthorizationPolicy.authorize({
            caller,
            userId,
            apiKey,
            projectId,
        });
        return await this.apiKeysRepository.delete(projectId, id);
    }
}
