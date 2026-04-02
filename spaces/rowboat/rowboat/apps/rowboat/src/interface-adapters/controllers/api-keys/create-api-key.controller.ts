import { BadRequestError } from "@/src/entities/errors/common";
import z from "zod";
import { ApiKey } from "@/src/entities/models/api-key";
import { ICreateApiKeyUseCase } from "@/src/application/use-cases/api-keys/create-api-key.use-case";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    projectId: z.string(),
});

export interface ICreateApiKeyController {
    execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>>;
}

export class CreateApiKeyController implements ICreateApiKeyController {
    private readonly createApiKeyUseCase: ICreateApiKeyUseCase;
    constructor({ createApiKeyUseCase }: { createApiKeyUseCase: ICreateApiKeyUseCase }) {
        this.createApiKeyUseCase = createApiKeyUseCase;
    }
    async execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>> {
        const result = inputSchema.safeParse(request);
        if (!result.success) {
            throw new BadRequestError(`Invalid request: ${JSON.stringify(result.error)}`);
        }
        return await this.createApiKeyUseCase.execute(result.data);
    }
}
export { inputSchema as createApiKeyInputSchema };
