import { CreateProjectMemberSchema, IProjectMembersRepository } from "@/src/application/repositories/project-members.repository.interface";
import { ProjectMember } from "@/src/entities/models/project-member";
import { db } from "@/app/lib/mongodb";
import { z } from "zod";
import { Filter, ObjectId } from "mongodb";
import { PaginatedList } from "@/src/entities/common/paginated-list";

const docSchema = ProjectMember.omit({
    id: true,
});

export class MongoDBProjectMembersRepository implements IProjectMembersRepository {
    private collection = db.collection<z.infer<typeof docSchema>>('project_members');

    async create(data: z.infer<typeof CreateProjectMemberSchema>): Promise<z.infer<typeof ProjectMember>> {
        // this has to be an upsert operation
        const result = await this.collection.findOneAndUpdate(
            {
                userId: data.userId,
                projectId: data.projectId,
            },
            {
                $set: {
                    ...data,
                    createdAt: new Date().toISOString(),
                    lastUpdatedAt: new Date().toISOString(),
                }
            },
            {
                upsert: true,
                returnDocument: 'after',
            }
        );

        if (!result) {
            throw new Error('Failed to create project member');
        }

        const { _id, ...rest } = result;

        return {
            ...rest,
            id: _id.toString(),
        };
    }

    async findByUserId(userId: string, cursor?: string, limit: number = 50): Promise<z.infer<ReturnType<typeof PaginatedList<typeof ProjectMember>>>> {
        const query: Filter<z.infer<typeof docSchema>> = { userId };

        if (cursor) {
            query._id = { $lt: new ObjectId(cursor) };
        }

        const results = await this.collection
            .find(query)
            .sort({ _id: -1 })
            .limit(limit + 1) // Fetch one extra to determine if there's a next page
            .toArray();

        const hasNextPage = results.length > limit;
        const items = results.slice(0, limit).map(doc => {
            const { _id, ...rest } = doc;
            return {
                ...rest,
                id: _id.toString(),
            };
        });

        return {
            items,
            nextCursor: hasNextPage ? results[limit - 1]._id.toString() : null,
        };
    }

    async exists(projectId: string, userId: string): Promise<boolean> {
        const membership = await this.collection.findOne({
            projectId,
            userId,
        });
        return !!membership;
    }

    async deleteByProjectId(projectId: string): Promise<void> {
        await this.collection.deleteMany({ projectId });
    }
}