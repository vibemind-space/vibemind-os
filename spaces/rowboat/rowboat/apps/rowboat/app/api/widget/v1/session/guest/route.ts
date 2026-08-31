import { NextRequest } from "next/server";
import { clientIdCheck } from "../../utils";
import { SignJWT } from "jose";
import { z } from "zod";
import { Session } from "../../utils";
import { apiV1 } from "rowboat-shared";

export async function POST(req: NextRequest): Promise<Response> {
    return await clientIdCheck(req, async (projectId) => {
        // create a new guest user
        const session: z.infer<typeof Session> = {
            userId: `guest-${crypto.randomUUID()}`,
            userName: 'Guest User',
            projectId: projectId
        };
        
        // Create and sign JWT
        const token = await new SignJWT(session)
            .setProtectedHeader({ alg: 'HS256' })
            .setIssuedAt()
            .setExpirationTime('24h')
            .sign(new TextEncoder().encode(process.env.CHAT_WIDGET_SESSION_JWT_SECRET));

        const response: z.infer<typeof apiV1.ApiCreateGuestSessionResponse> = {
            sessionId: token,
        };

        return Response.json(response);
    });
}
