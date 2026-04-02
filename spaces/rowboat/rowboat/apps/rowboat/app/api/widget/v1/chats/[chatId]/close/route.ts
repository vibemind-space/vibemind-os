import { NextRequest } from "next/server";
import { chatsCollection } from "../../../../../../lib/mongodb";
import { ObjectId } from "mongodb";
import { authCheck } from "../../../utils";

export async function POST(request: NextRequest, props: { params: Promise<{ chatId: string }> }): Promise<Response> {
    const params = await props.params;
    return await authCheck(request, async (session) => {
        const { chatId } = params;

        const result = await chatsCollection.findOneAndUpdate(
            {
                _id: new ObjectId(chatId),
                projectId: session.projectId,
                userId: session.userId,
                closed: { $exists: false },
            },
            {
                $set: {
                    closed: true,
                    closedAt: new Date().toISOString(),
                    closeReason: "user-closed-chat",
                },
            },
            { returnDocument: 'after' }
        );

        if (!result) {
            return Response.json({ error: "Chat not found" }, { status: 404 });
        }

        return Response.json(result);
    });
}
