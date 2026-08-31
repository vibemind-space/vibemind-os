import { IUsageQuotaPolicy } from "@/src/application/policies/usage-quota.policy.interface";
import { redisClient } from "@/app/lib/redis";
import { QuotaExceededError } from "@/src/entities/errors/common";
import { secondsToNextMinute, minutesToNextHour } from "@/src/application/lib/utils/time-to-next-minute";

const MAX_QUERIES_PER_MINUTE = Number(process.env.MAX_QUERIES_PER_MINUTE) || 0;
const MAX_JOBS_PER_HOUR = Number(process.env.MAX_JOBS_PER_HOUR) || 0;

export class RedisUsageQuotaPolicy implements IUsageQuotaPolicy {
    async assertAndConsumeProjectAction(projectId: string): Promise<void> {
        if (MAX_QUERIES_PER_MINUTE === 0) {
            return;
        }

        const minutes_since_epoch = Math.floor(Date.now() / 1000 / 60); // 60 second window
        const key = `rate_limit:${projectId}:${minutes_since_epoch}`;

        const count = await redisClient.incr(key);
        if (count === 1) {
            await redisClient.expire(key, secondsToNextMinute()); // Set TTL to clean up automatically
        }

        if (count > MAX_QUERIES_PER_MINUTE) {
            throw new QuotaExceededError(`Quota exceeded for project ${projectId}`);
        }
    }

    async assertAndConsumeRunJobAction(projectId: string): Promise<void> {
        if (MAX_JOBS_PER_HOUR === 0) {
            return;
        }

        const hour_of_the_day = new Date().getHours();
        const key = `jobs_limit:${projectId}:${hour_of_the_day}`;

        const count = await redisClient.incr(key);
        if (count === 1) {
            await redisClient.expire(key, minutesToNextHour() * 60); // Set TTL to clean up automatically
        }

        if (count > MAX_JOBS_PER_HOUR) {
            throw new QuotaExceededError(`Jobs quota exceeded for project ${projectId}`);
        }
    }
}