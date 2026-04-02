import { z } from "zod";
import { IProjectsRepository } from "../../repositories/projects.repository.interface";
import { IProjectMembersRepository } from "../../repositories/project-members.repository.interface";
import { IProjectActionAuthorizationPolicy } from "../../policies/project-action-authorization.policy";
import { IApiKeysRepository } from "../../repositories/api-keys.repository.interface";
import { IDataSourceDocsRepository } from "../../repositories/data-source-docs.repository.interface";
import { IDataSourcesRepository } from "../../repositories/data-sources.repository.interface";
import { qdrantClient } from "@/app/lib/qdrant";
import { IComposioTriggerDeploymentsRepository } from "../../repositories/composio-trigger-deployments.repository.interface";
import { IConversationsRepository } from "../../repositories/conversations.repository.interface";
import { IJobsRepository } from "../../repositories/jobs.repository.interface";
import { IRecurringJobRulesRepository } from "../../repositories/recurring-job-rules.repository.interface";
import { IScheduledJobRulesRepository } from "../../repositories/scheduled-job-rules.repository.interface";
import { NotFoundError } from "@/src/entities/errors/common";
import { deleteConnectedAccount } from "../../lib/composio/composio";

export const InputSchema = z.object({
    projectId: z.string(),
    userId: z.string(),
    caller: z.enum(["user", "api"]),
    apiKey: z.string().optional(),
});

export interface IDeleteProjectUseCase {
    execute(request: z.infer<typeof InputSchema>): Promise<void>;
}

export class DeleteProjectUseCase implements IDeleteProjectUseCase {
    private readonly projectsRepository: IProjectsRepository;
    private readonly projectMembersRepository: IProjectMembersRepository;
    private readonly projectActionAuthorizationPolicy: IProjectActionAuthorizationPolicy;
    private readonly apiKeysRepository: IApiKeysRepository;
    private readonly dataSourceDocsRepository: IDataSourceDocsRepository;
    private readonly dataSourcesRepository: IDataSourcesRepository;
    private readonly composioTriggerDeploymentsRepository: IComposioTriggerDeploymentsRepository;
    private readonly conversationsRepository: IConversationsRepository;
    private readonly jobsRepository: IJobsRepository;
    private readonly recurringJobRulesRepository: IRecurringJobRulesRepository;
    private readonly scheduledJobRulesRepository: IScheduledJobRulesRepository;

    constructor({ projectsRepository, projectMembersRepository, projectActionAuthorizationPolicy, apiKeysRepository, dataSourceDocsRepository, dataSourcesRepository, composioTriggerDeploymentsRepository, conversationsRepository, jobsRepository, recurringJobRulesRepository, scheduledJobRulesRepository }: {
        projectsRepository: IProjectsRepository,
        projectMembersRepository: IProjectMembersRepository,
        projectActionAuthorizationPolicy: IProjectActionAuthorizationPolicy,
        apiKeysRepository: IApiKeysRepository,
        dataSourceDocsRepository: IDataSourceDocsRepository,
        dataSourcesRepository: IDataSourcesRepository,
        composioTriggerDeploymentsRepository: IComposioTriggerDeploymentsRepository,
        conversationsRepository: IConversationsRepository,
        jobsRepository: IJobsRepository,
        recurringJobRulesRepository: IRecurringJobRulesRepository,
        scheduledJobRulesRepository: IScheduledJobRulesRepository,
    }) {
        this.projectsRepository = projectsRepository;
        this.projectMembersRepository = projectMembersRepository;
        this.projectActionAuthorizationPolicy = projectActionAuthorizationPolicy;
        this.apiKeysRepository = apiKeysRepository;
        this.dataSourceDocsRepository = dataSourceDocsRepository;
        this.dataSourcesRepository = dataSourcesRepository;
        this.composioTriggerDeploymentsRepository = composioTriggerDeploymentsRepository;
        this.conversationsRepository = conversationsRepository;
        this.jobsRepository = jobsRepository;
        this.recurringJobRulesRepository = recurringJobRulesRepository;
        this.scheduledJobRulesRepository = scheduledJobRulesRepository;
    }

    async execute(request: z.infer<typeof InputSchema>): Promise<void> {
        const { projectId, userId, caller, apiKey } = request;
        await this.projectActionAuthorizationPolicy.authorize({
            caller,
            userId,
            apiKey,
            projectId,
        });

        const project = await this.projectsRepository.fetch(projectId);
        if (!project) {
            throw new NotFoundError('Project not found');
        }

        // delete connected accounts
        await Promise.all(
            Object.values(project.composioConnectedAccounts || {}).map(account =>
                deleteConnectedAccount(account.id)
            )
        );

        // delete memberships
        await this.projectMembersRepository.deleteByProjectId(projectId);

        // delete api keys
        await this.apiKeysRepository.deleteAll(projectId);

        // delete composio trigger deployments
        await this.composioTriggerDeploymentsRepository.deleteByProjectId(projectId);

        // delete conversations
        await this.conversationsRepository.deleteByProjectId(projectId);

        // delete jobs
        await this.jobsRepository.deleteByProjectId(projectId);

        // delete recurring job rules
        await this.recurringJobRulesRepository.deleteByProjectId(projectId);

        // delete scheduled job rules
        await this.scheduledJobRulesRepository.deleteByProjectId(projectId);

        // delete data sources data
        await this.dataSourceDocsRepository.deleteByProjectId(projectId);
        await this.dataSourcesRepository.deleteByProjectId(projectId);
        await qdrantClient.delete("embeddings", {
            filter: {
                must: [
                    { key: "projectId", match: { value: projectId } },
                ],
            },
        });

        // delete project
        await this.projectsRepository.delete(projectId);
    }
}
