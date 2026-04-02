import {QdrantClient} from '@qdrant/js-client-rest';

// TO connect to Qdrant running locally
export const qdrantClient = new QdrantClient({
    url: process.env.QDRANT_URL,
    ...(process.env.QDRANT_API_KEY ? { apiKey: process.env.QDRANT_API_KEY } : {}),
});