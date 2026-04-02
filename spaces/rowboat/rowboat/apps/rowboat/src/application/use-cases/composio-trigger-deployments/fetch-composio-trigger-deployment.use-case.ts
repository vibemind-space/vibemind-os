import { NotFoundError } from '@/src/entities/errors/common';
import { z } from "zod";
import { IUsageQuotaPolicy } from '../../policies/usage-quota.policy.interface';
import { IProjectActionAuthorizationPolicy } from '../../policies/project-action-authorization.policy';
import { IComposioTriggerDeploymentsRepository } from '../../repositories/composio-trigger-deployments.repository.interface';
import { ComposioTriggerDeployment } from '@/src/entities/models/composio-trigger-deployment';

const inputSchema = z.object({
    caller: z.enum(["user", "api"]),
    userId: z.string().optional(),
    apiKey: z.string().optional(),
    deploymentId: z.string(),
});

export interface IFetchComposioTriggerDeploymentUseCase {
    execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ComposioTriggerDeployment>>;
}

export class FetchComposioTriggerDeploymentUseCase implements IFetchComposioTriggerDeploymentUseCase {
    private readonly composioTriggerDeploymentsRepository: IComposioTriggerDeploymentsRepository;   
    private readonly usageQuotaPolicy: IUsageQuotaPolicy;
    private readonly projectActionAuthorizationPolicy: IProjectActionAuthorizationPolicy;

    constructor({
        composioTriggerDeploymentsRepository,
        usageQuotaPolicy,
        projectActionAuthorizationPolicy,
    }: {
        composioTriggerDeploymentsRepository: IComposioTriggerDeploymentsRepository,
        usageQuotaPolicy: IUsageQuotaPolicy,
        projectActionAuthorizationPolicy: IProjectActionAuthorizationPolicy,
    }) {
        this.composioTriggerDeploymentsRepository = composioTriggerDeploymentsRepository;
        this.usageQuotaPolicy = usageQuotaPolicy;
        this.projectActionAuthorizationPolicy = projectActionAuthorizationPolicy;
    }

    async execute(request: z.infer<typeof inputSchema>): Promise<z.infer<typeof ComposioTriggerDeployment>> {
        // fetch deployment first to get projectId
        const deployment = await this.composioTriggerDeploymentsRepository.fetch(request.deploymentId);
        if (!deployment) {
            throw new NotFoundError(`Composio trigger deployment ${request.deploymentId} not found`);
        }

        const { projectId } = deployment;

        // authz check
        await this.projectActionAuthorizationPolicy.authorize({
            caller: request.caller,
            userId: request.userId,
            apiKey: request.apiKey,
            projectId,
        });

        // assert and consume quota
        await this.usageQuotaPolicy.assertAndConsumeProjectAction(projectId);

        return deployment;
    }
}


