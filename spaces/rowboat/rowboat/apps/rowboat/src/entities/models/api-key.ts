import { z } from "zod";

export const ApiKey = z.object({
    id: z.string(),
    projectId: z.string(),
    key: z.string(),
    createdAt: z.string().datetime(),
    lastUsedAt: z.string().datetime().optional(),
});