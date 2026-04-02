import { NextRequest } from "next/server";
import { db } from "../../../../lib/mongodb";
import { z } from "zod";
import { ObjectId } from "mongodb";
import { apiV1 } from "rowboat-shared";
import { authCheck } from "../utils";

const chatsCollection = db.collection<z.infer<typeof apiV1.Chat>>("chats");

// create a chat
export async function POST(
    req: NextRequest,
): Promise<Response> {
    return await authCheck(req, async (session) => {
        // parse and validate the request body
        let body;
        try {
            body = await req.json();
        } catch (e) {
            return Response.json({ error: "Invalid JSON in request body" }, { status: 400 });
        }
        const result = apiV1.ApiCreateChatRequest.safeParse(body);
        if (!result.success) {
            return new Response(JSON.stringify({ error: `Invalid request body: ${result.error.message}` }), { status: 400 });
        }

        // insert the chat into the database
        const id = new ObjectId();
        const chat: z.infer<typeof apiV1.Chat> = {
            version: "v1",
            projectId: session.projectId,
            userId: session.userId,
            createdAt: new Date().toISOString(),
            userData: {
                userId: session.userId,
                userName: session.userName,
            },
        }
        await chatsCollection.insertOne({
            ...chat,
            _id: id,
        });

        // return response
        const response: z.infer<typeof apiV1.ApiCreateChatResponse> = {
            ...chat,
            id: id.toString(),
        };
        return Response.json(response);
    });
}

// list chats
export async function GET(
    req: NextRequest,
): Promise<Response> {
    return await authCheck(req, async (session) => {
        // Parse query parameters
        const searchParams = req.nextUrl.searchParams;
        const limit = 10; // Hardcoded limit
        const next = searchParams.get('next');
        const previous = searchParams.get('previous');

        // Add userId to query to only show chats for current user
        const query: { projectId: string; userId: string; _id?: { $lt?: ObjectId; $gt?: ObjectId } } = { 
            projectId: session.projectId,
            userId: session.userId 
        };

        // Add cursor condition to the query
        if (next) {
            query._id = { $lt: new ObjectId(next) };
        } else if (previous) {
            query._id = { $gt: new ObjectId(previous) };
        }

        // Fetch chats from the database
        let chats = await chatsCollection
            .find(query)
            .sort({ _id: -1 })  // Sort in descending order
            .limit(limit + 1)  // Fetch one extra to determine if there are more results
            .toArray();

        // Determine if there are more results
        const hasMore = chats.length > limit;
        if (hasMore) {
            chats.pop();
        }
        let nextCursor: string | undefined;
        let previousCursor: string | undefined;
        if (chats.length > 0) {
            if (hasMore || previous) {
                nextCursor = chats[chats.length - 1]._id.toString();
            }
            if (next || (previous && hasMore)) {
                previousCursor = chats[0]._id.toString();
            }
        }

        // Prepare the response
        const response: z.infer<typeof apiV1.ApiGetChatsResponse> = {
            chats: chats
                .slice(0, limit)
                .map(chat => ({
                    ...chat,
                    id: chat._id.toString(),
                    _id: undefined
                })),
            next: nextCursor,
            previous: previousCursor,
        };

        // Return response
        return Response.json(response);
    });
}
