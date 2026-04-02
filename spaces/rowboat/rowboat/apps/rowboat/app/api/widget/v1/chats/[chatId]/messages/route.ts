import { NextRequest } from "next/server";
import { apiV1 } from "rowboat-shared";
import { chatsCollection, chatMessagesCollection } from "../../../../../../lib/mongodb";
import { z } from "zod";
import { Filter, ObjectId } from "mongodb";
import { authCheck } from "../../../utils";

// list messages
export async function GET(req: NextRequest, props: { params: Promise<{ chatId: string }> }): Promise<Response> {
    const params = await props.params;
    return await authCheck(req, async (session) => {
        const { chatId } = params;

        // Check if chat exists
        const chat = await chatsCollection.findOne({ 
            _id: new ObjectId(chatId), 
            projectId: session.projectId, 
            userId: session.userId 
        });
        if (!chat) {
            return Response.json({ error: "Chat not found" }, { status: 404 });
        }

        // Parse query parameters
        const searchParams = req.nextUrl.searchParams;
        const limit = 10; // Hardcoded limit
        const next = searchParams.get('next');
        const previous = searchParams.get('previous');

        // Construct the query
        const query: Filter<z.infer<typeof apiV1.ChatMessage>> = {
            chatId,
            $or: [
                { role: 'user' },
                { role: 'assistant', agenticResponseType: { $eq: 'external' } }
            ],
        };

        // Add cursor condition to the query
        if (previous) {
            query._id = { $lt: new ObjectId(previous) };
        } else if (next) {
            query._id = { $gt: new ObjectId(next) };
        }

        // Fetch messages from the database
        let messages = await chatMessagesCollection
            .find(query)
            .sort({ _id: previous ? -1 : 1 })  // Sort based on direction
            .limit(limit + 1)  // Fetch one extra to determine if there are more results
            .toArray();

        // Determine if there are more results
        const hasMore = messages.length > limit;
        if (hasMore) {
            messages.pop();
        }

        // Reverse the array if we're paginating backwards
        if (previous) {
            messages.reverse();
        }

        let nextCursor: string | undefined;
        let previousCursor: string | undefined;
        if (messages.length > 0) {
            if (hasMore || previous) {
                nextCursor = messages[messages.length - 1]._id.toString();
            }
            if (next || (previous && hasMore)) {
                previousCursor = messages[0]._id.toString();
            }
        }

        // Prepare the response
        const response: z.infer<typeof apiV1.ApiGetChatMessagesResponse> = {
            messages: messages.map(message => ({
                ...message,
                id: message._id.toString(),
                _id: undefined
            })),
            next: nextCursor,
            previous: previousCursor,
        };

        // Return response
        return Response.json(response);
    });
}
