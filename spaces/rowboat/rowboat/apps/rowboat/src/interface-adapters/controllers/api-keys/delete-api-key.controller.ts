import { BadRequestError } from "@/src/entities/errors/common";
import z from "zod";
import { IDeleteApiKeyUseCase } from "@/src/application/use-cases/api-keys/delete-api-key.use-case";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    projectId: z.string(),
    id: z.string(),
});

export interface IDeleteApiKeyController {
    execute(request: z.infer<typeof inputSchema>): Promise<boolean>;
}

export class DeleteApiKeyController implements IDeleteApiKeyController {
    private readonly deleteApiKeyUseCase: IDeleteApiKeyUseCase;
    constructor({ deleteApiKeyUseCase }: { deleteApiKeyUseCase: IDeleteApiKeyUseCase }) {
        this.deleteApiKeyUseCase = deleteApiKeyUseCase;
    }
    async execute(request: z.infer<typeof inputSchema>): Promise<boolean> {
        const result = inputSchema.safeParse(request);
        if (!result.success) {
            throw new BadRequestError(`Invalid request: ${JSON.stringify(result.error)}`);
        }
        return await this.deleteApiKeyUseCase.execute(result.data);
    }
}
export { inputSchema as deleteApiKeyInputSchema };
