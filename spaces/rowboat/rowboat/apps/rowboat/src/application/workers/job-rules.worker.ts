import { IScheduledJobRulesRepository } from "@/src/application/repositories/scheduled-job-rules.repository.interface";
import { IRecurringJobRulesRepository } from "@/src/application/repositories/recurring-job-rules.repository.interface";
import { IJobsRepository } from "@/src/application/repositories/jobs.repository.interface";
import { IProjectsRepository } from "@/src/application/repositories/projects.repository.interface";
import { IPubSubService } from "@/src/application/services/pub-sub.service.interface";
import { ScheduledJobRule } from "@/src/entities/models/scheduled-job-rule";
import { z } from "zod";
import { nanoid } from "nanoid";
import { PrefixLogger } from "@/app/lib/utils";
import { RecurringJobRule } from "@/src/entities/models/recurring-job-rule";
import { secondsToNextMinute } from "../lib/utils/time-to-next-minute";

export interface IJobRulesWorker {
    run(): Promise<void>;
    stop(): Promise<void>;
}

export class JobRulesWorker implements IJobRulesWorker {
    private readonly scheduledJobRulesRepository: IScheduledJobRulesRepository;
    private readonly recurringJobRulesRepository: IRecurringJobRulesRepository;
    private readonly jobsRepository: IJobsRepository;
    private readonly projectsRepository: IProjectsRepository;
    private readonly pubSubService: IPubSubService;
    private workerId: string;
    private logger: PrefixLogger;
    private isRunning: boolean = false;
    private pollTimeoutId: NodeJS.Timeout | null = null;

    constructor({
        scheduledJobRulesRepository,
        recurringJobRulesRepository,
        jobsRepository,
        projectsRepository,
        pubSubService,
    }: {
        scheduledJobRulesRepository: IScheduledJobRulesRepository;
        recurringJobRulesRepository: IRecurringJobRulesRepository;
        jobsRepository: IJobsRepository;
        projectsRepository: IProjectsRepository;
        pubSubService: IPubSubService;
    }) {
        this.scheduledJobRulesRepository = scheduledJobRulesRepository;
        this.recurringJobRulesRepository = recurringJobRulesRepository;
        this.jobsRepository = jobsRepository;
        this.projectsRepository = projectsRepository;
        this.pubSubService = pubSubService;
        this.workerId = nanoid();
        this.logger = new PrefixLogger(`scheduled-job-rules-worker-[${this.workerId}]`);
    }

    private async processScheduledRule(rule: z.infer<typeof ScheduledJobRule>): Promise<void> {
        const logger = this.logger.child(`rule-${rule.id}`);
        logger.log("Processing scheduled job rule");

        try {
            // create job
            const job = await this.jobsRepository.create({
                reason: {
                    type: "scheduled_job_rule",
                    ruleId: rule.id,
                },
                projectId: rule.projectId,
                input: {
                    messages: rule.input.messages,
                },
            });

            // notify job workers
            await this.pubSubService.publish("new_jobs", job.id);

            logger.log(`Created job ${job.id} from rule ${rule.id}`);

            // update data
            await this.scheduledJobRulesRepository.update(rule.id, {
                output: {
                    jobId: job.id,
                },
                status: "triggered",
            });

            // release
            await this.scheduledJobRulesRepository.release(rule.id);

            logger.log(`Published job ${job.id} to new_jobs`);
        } catch (error) {
            logger.log(`Failed to process rule: ${error instanceof Error ? error.message : "Unknown error"}`);
            // Always release the rule to avoid deadlocks but do not attach a jobId
            try {
                await this.scheduledJobRulesRepository.release(rule.id);
            } catch (releaseError) {
                logger.log(`Failed to release rule: ${releaseError instanceof Error ? releaseError.message : "Unknown error"}`);
            }
        }
    }

    private async processRecurringRule(rule: z.infer<typeof RecurringJobRule>): Promise<void> {
        const logger = this.logger.child(`rule-${rule.id}`);
        logger.log("Processing recurring job rule");

        try {
            // create job
            const job = await this.jobsRepository.create({
                reason: {
                    type: "recurring_job_rule",
                    ruleId: rule.id,
                },
                projectId: rule.projectId,
                input: {
                    messages: rule.input.messages,
                },
            });

            // notify job workers
            await this.pubSubService.publish("new_jobs", job.id);

            logger.log(`Created job ${job.id} from rule ${rule.id}`);

            // release
            await this.recurringJobRulesRepository.release(rule.id);

            logger.log(`Published job ${job.id} to new_jobs`);
        } catch (error) {
            logger.log(`Failed to process rule: ${error instanceof Error ? error.message : "Unknown error"}`);
            // Always release the rule to avoid deadlocks
            try {
                await this.recurringJobRulesRepository.release(rule.id);
            } catch (releaseError) {
                logger.log(`Failed to release rule: ${releaseError instanceof Error ? releaseError.message : "Unknown error"}`);
            }
        }
    }

    private async pollScheduled(): Promise<void> {
        const logger = this.logger.child(`poll-scheduled`);
        logger.log("Polling...");
        let rule: z.infer<typeof ScheduledJobRule> | null = null;
        try {
            do {
                rule = await this.scheduledJobRulesRepository.poll(this.workerId);
                if (!rule) {
                    logger.log("No rules to process");
                    return;
                }
                await this.processScheduledRule(rule);
            } while (rule);
        } catch (error) {
            logger.log(`Error while polling rules: ${error instanceof Error ? error.message : "Unknown error"}`);
        }
    }

    private async pollRecurring(): Promise<void> {
        const logger = this.logger.child(`poll-recurring`);
        logger.log("Polling...");
        let rule: z.infer<typeof RecurringJobRule> | null = null;
        try {
            do {
                rule = await this.recurringJobRulesRepository.poll(this.workerId);
                if (!rule) {
                    logger.log("No rules to process");
                    return;
                }
                await this.processRecurringRule(rule);
            } while (rule);
        } catch (error) {
            logger.log(`Error while polling rules: ${error instanceof Error ? error.message : "Unknown error"}`);
        }
    }

    private scheduleNextPoll(): void {
        // schedule next poll for 2 s past the minute mark
        const delayMs = (secondsToNextMinute() + 2) * 1000;
        this.logger.log(`Scheduling next poll in ${delayMs} ms`);
        this.pollTimeoutId = setTimeout(async () => {
            if (!this.isRunning) return;
            await Promise.all([
                this.pollScheduled(),
                this.pollRecurring(),
            ]);
            this.scheduleNextPoll();
        }, delayMs);
    }

    async run(): Promise<void> {
        if (this.isRunning) {
            this.logger.log("Worker already running");
            return;
        }
        this.isRunning = true;
        this.logger.log(`Starting worker ${this.workerId}`);
        this.scheduleNextPoll();
    }

    async stop(): Promise<void> {
        this.logger.log(`Stopping worker ${this.workerId}`);
        this.isRunning = false;
        if (this.pollTimeoutId) {
            clearTimeout(this.pollTimeoutId);
            this.pollTimeoutId = null;
        }
    }
}
