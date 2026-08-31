import { IApiKeysRepository } from "@/src/application/repositories/api-keys.repository.interface";
import { z } from "zod";
import { ApiKey } from "@/src/entities/models/api-key";
import { IProjectActionAuthorizationPolicy } from "@/src/application/policies/project-action-authorization.policy";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    projectId: z.string(),
});

export interface IListApiKeysUseCase {
    execute(data: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>[]>;
}

export class ListApiKeysUseCase implements IListApiKeysUseCase {
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

    async execute(data: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>[]> {
        const { caller, userId, apiKey, projectId } = data;
        await this.projectActionAuthorizationPolicy.authorize({
            caller,
            userId,
            apiKey,
            projectId,
        });
        return await this.apiKeysRepository.listAll(projectId);
    }
}
