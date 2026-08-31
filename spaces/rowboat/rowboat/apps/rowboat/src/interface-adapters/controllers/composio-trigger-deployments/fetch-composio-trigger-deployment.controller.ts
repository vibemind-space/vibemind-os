import { BadRequestError } from "@/src/entities/errors/common";
import z from "zod";
import { IFetchComposioTriggerDeploymentUseCase } from "@/src/application/use-cases/composio-trigger-deployments/fetch-composio-trigger-deployment.use-case";
import { ComposioTriggerDeployment } from "@/src/entities/models/composio-trigger-deployment";

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    deploymentId: z.string(),
});

export interface IFetchComposioTriggerDeploymentController {
    execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ComposioTriggerDeployment>>;
}

export class FetchComposioTriggerDeploymentController implements IFetchComposioTriggerDeploymentController {
    private readonly fetchComposioTriggerDeploymentUseCase: IFetchComposioTriggerDeploymentUseCase;
    
    constructor({
        fetchComposioTriggerDeploymentUseCase,
    }: {
        fetchComposioTriggerDeploymentUseCase: IFetchComposioTriggerDeploymentUseCase,
    }) {
        this.fetchComposioTriggerDeploymentUseCase = fetchComposioTriggerDeploymentUseCase;
    }

    async execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ComposioTriggerDeployment>> {
        const result = inputSchema.safeParse(request);
        if (!result.success) {
            throw new BadRequestError(`Invalid request: ${JSON.stringify(result.error)}`);
        }
        const { caller, userId, apiKey, deploymentId } = result.data;

        return await this.fetchComposioTriggerDeploymentUseCase.execute({
            caller,
            userId,
            apiKey,
            deploymentId,
        });
    }
}


