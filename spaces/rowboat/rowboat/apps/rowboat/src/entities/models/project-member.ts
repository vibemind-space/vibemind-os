import { z } from "zod";

export const ProjectMember = z.object({
    id: z.string(),
    userId: z.string(),
    projectId: z.string(),
    createdAt: z.string().datetime(),
    lastUpdatedAt: z.string().datetime(),
});