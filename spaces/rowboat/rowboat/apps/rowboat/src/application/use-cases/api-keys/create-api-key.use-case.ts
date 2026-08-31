import { IApiKeysRepository } from "@/src/application/repositories/api-keys.repository.interface";
import { z } from "zod";
import { ApiKey } from "@/src/entities/models/api-key";
import { IProjectActionAuthorizationPolicy } from "@/src/application/policies/project-action-authorization.policy";
import crypto from "crypto";
import { BadRequestError } from "@/src/entities/errors/common";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    projectId: z.string(),
});

export class MaxKeysReachedError extends BadRequestError {
    constructor(message?: string, options?: ErrorOptions) {
        super(message, options);
    }
}

export interface ICreateApiKeyUseCase {
    execute(data: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>>;
}

export class CreateApiKeyUseCase implements ICreateApiKeyUseCase {
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

    async execute(data: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>> {
        const { caller, userId, apiKey, projectId } = data;
        await this.projectActionAuthorizationPolicy.authorize({
            caller,
            userId,
            apiKey,
            projectId,
        });

        // count existing keys
        const keys = await this.apiKeysRepository.listAll(projectId);
        if (keys.length >= 3) {
            throw new MaxKeysReachedError("You can only have up to 3 API keys per project.");
        }

        // Generate a random key using crypto
        const key = crypto.randomBytes(32).toString('hex');
        return await this.apiKeysRepository.create({ projectId, key });
    }
}
