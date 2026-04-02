import { IApiKeysRepository } from "@/src/application/repositories/api-keys.repository.interface";
import { db } from "@/app/lib/mongodb";
import { ApiKey } from "@/src/entities/models/api-key";
import { z } from "zod";
import { ObjectId } from "mongodb";
import { CreateSchema } from "@/src/application/repositories/api-keys.repository.interface";

const DocSchema = ApiKey
    .omit({
        id: true,
    });

export class MongoDBApiKeysRepository implements IApiKeysRepository {
    private readonly collection = db.collection<z.infer<typeof DocSchema>>("api_keys");

    async checkAndConsumeKey(projectId: string, apiKey: string): Promise<boolean> {
        const result = await this.collection.findOneAndUpdate(
            { projectId, key: apiKey },
            { $set: { lastUsedAt: new Date().toISOString() } }
        );
        return !!result;
    }

    async create(data: z.infer<typeof CreateSchema>): Promise<z.infer<typeof ApiKey>> {
        const now = new Date().toISOString();
        const _id = new ObjectId();

        const doc = {
            ...data,
            createdAt: now,
        };

        const result = await this.collection.insertOne({
            _id,
            ...doc,
        });

        return {
            ...doc,
            id: _id.toString(),
        };
    }

    async listAll(projectId: string): Promise<z.infer<typeof ApiKey>[]> {
        const results = await this.collection.find({ projectId }).sort({ createdAt: -1 }).toArray();
        return results.map(doc => {
            const { _id, ...rest } = doc;
            return {
                ...rest,
                id: _id.toString(),
            };
        });
    }

    async delete(projectId: string, id: string): Promise<boolean> {
        const result = await this.collection.deleteOne({ projectId, _id: new ObjectId(id) });
        return result.deletedCount > 0;
    }

    async deleteAll(projectId: string): Promise<void> {
        await this.collection.deleteMany({ projectId });
    }
}