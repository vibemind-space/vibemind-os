import { IndexDescription } from "mongodb";

export const USERS_COLLECTION = "users";

export const USERS_INDEXES: IndexDescription[] = [
    { key: { auth0Id: 1 }, name: "auth0Id_unique", unique: true },
];