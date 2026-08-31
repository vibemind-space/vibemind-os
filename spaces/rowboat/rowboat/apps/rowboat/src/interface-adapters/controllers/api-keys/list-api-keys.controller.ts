import { BadRequestError } from "@/src/entities/errors/common";
import z from "zod";
import { ApiKey } from "@/src/entities/models/api-key";
import { IListApiKeysUseCase } from "@/src/application/use-cases/api-keys/list-api-keys.use-case";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    projectId: z.string(),
});

export interface IListApiKeysController {
    execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>[]>;
}

export class ListApiKeysController implements IListApiKeysController {
    private readonly listApiKeysUseCase: IListApiKeysUseCase;
    constructor({ listApiKeysUseCase }: { listApiKeysUseCase: IListApiKeysUseCase }) {
        this.listApiKeysUseCase = listApiKeysUseCase;
    }
    async execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ApiKey>[]> {
        const result = inputSchema.safeParse(request);
        if (!result.success) {
            throw new BadRequestError(`Invalid request: ${JSON.stringify(result.error)}`);
        }
        return await this.listApiKeysUseCase.execute(result.data);
    }
}
export { inputSchema as listApiKeysInputSchema };
