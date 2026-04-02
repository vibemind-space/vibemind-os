"use server";

import { container } from "@/di/container";
import { IListJobsController } from "@/src/interface-adapters/controllers/jobs/list-jobs.controller";
import { IFetchJobController } from "@/src/interface-adapters/controllers/jobs/fetch-job.controller";
import { authCheck } from "./auth.actions";
import { JobFiltersSchema } from "@/src/application/repositories/jobs.repository.interface";
import { z } from "zod";

const listJobsController = container.resolve<IListJobsController>('listJobsController');
const fetchJobController = container.resolve<IFetchJobController>('fetchJobController');

export async function listJobs(request: {
    projectId: string,
    filters?: z.infer<typeof JobFiltersSchema>,
    cursor?: string,
    limit?: number,
}) {
    const user = await authCheck();

    return await listJobsController.execute({
        caller: 'user',
        userId: user.id,
        projectId: request.projectId,
        filters: request.filters,
        cursor: request.cursor,
        limit: request.limit,
    });
}

export async function fetchJob(request: {
    jobId: string,
}) {
    const user = await authCheck();

    return await fetchJobController.execute({
        caller: 'user',
        userId: user.id,
        jobId: request.jobId,
    });
}