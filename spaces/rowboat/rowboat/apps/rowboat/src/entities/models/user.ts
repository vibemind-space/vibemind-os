import { z } from "zod";

export const User = z.object({
    id: z.string(),
    auth0Id: z.string(),
    billingCustomerId: z.string().optional(),
    name: z.string().optional(),
    email: z.string().optional(),
    createdAt: z.string().datetime(),
    updatedAt: z.string().datetime().optional(),
});