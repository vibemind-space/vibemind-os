import { z } from "zod";
import { db } from "@/app/lib/mongodb";
import { ObjectId } from "mongodb";
import { CreateSchema, IUsersRepository } from "@/src/application/repositories/users.repository.interface";
import { User } from "@/src/entities/models/user";

const DocSchema = User
    .omit({
        id: true,
    });

export class MongoDBUsersRepository implements IUsersRepository {
    private readonly collection = db.collection<z.infer<typeof DocSchema>>("users");

    async create(data: z.infer<typeof CreateSchema>): Promise<z.infer<typeof User>> {
        const now = new Date().toISOString();
        const _id = new ObjectId();

        const doc = {
            ...data,
            createdAt: now,
        };

        await this.collection.insertOne({
            _id,
            ...doc,
        });

        return {
            ...doc,
            id: _id.toString(),
        };
    }

    async fetch(id: string): Promise<z.infer<typeof User> | null> {
        const result = await this.collection.findOne({ _id: new ObjectId(id) });
        if (!result) return null;

        return {
            ...result,
            id: result._id.toString(),
        };
    }

    async fetchByAuth0Id(auth0Id: string): Promise<z.infer<typeof User> | null> {
        const result = await this.collection.findOne({ auth0Id });
        if (!result) return null;

        return {
            ...result,
            id: result._id.toString(),
        };
    }

    async updateEmail(id: string, email: string): Promise<z.infer<typeof User>> {
        const result = await this.collection.findOneAndUpdate(
            { _id: new ObjectId(id) },
            { $set: { email, updatedAt: new Date().toISOString() } }
        );

        if (!result) throw new Error("User not found");

        return {
            ...result,
            id: result._id.toString(),
        };
    }

    async updateBillingCustomerId(id: string, billingCustomerId: string): Promise<z.infer<typeof User>> {
        const result = await this.collection.findOneAndUpdate(
            { _id: new ObjectId(id) },
            { $set: { billingCustomerId, updatedAt: new Date().toISOString() } }
        );

        if (!result) throw new Error("User not found");

        return {
            ...result,
            id: result._id.toString(),
        };
    }
}