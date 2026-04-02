import '../lib/loadenv';
import { container } from "@/di/container";
import { IJobsWorker } from "@/src/application/workers/jobs.worker";
import { IJobRulesWorker } from "@/src/application/workers/job-rules.worker";

// this is the old script which just launches job-worker
// ------------------------------------------------------------
// (async () => {
//     try {
//         const jobsWorker = container.resolve<IJobsWorker>('jobsWorker');
//         await jobsWorker.run();
//     } catch (error) {
//         console.error(`Unable to run jobs worker: ${error}`);
//     }
// })();

(async () => {
    try {
        const jobsWorker = container.resolve<IJobsWorker>('jobsWorker');
        const rulesWorker = container.resolve<IJobRulesWorker>('jobRulesWorker');

        // Start jobs worker first so subscription is ready before rules publish
        await jobsWorker.run();
        await rulesWorker.run();

        const shutdown = async (signal: string) => {
            console.log(`[worker] ${signal} received, shutting down...`);
            try {
                await Promise.allSettled([
                    jobsWorker.stop(),
                    rulesWorker.stop(),
                ]);
            } finally {
                process.exit(0);
            }
        };

        process.on('SIGINT', () => shutdown('SIGINT'));
        process.on('SIGTERM', () => shutdown('SIGTERM'));
        process.on('uncaughtException', (err) => {
            console.error('[worker] uncaughtException', err);
            shutdown('uncaughtException');
        });
        process.on('unhandledRejection', (reason) => {
            console.error('[worker] unhandledRejection', reason);
            shutdown('unhandledRejection');
        });
    } catch (error) {
        console.error('Unable to start combined worker:', error);
        process.exit(1);
    }
})();