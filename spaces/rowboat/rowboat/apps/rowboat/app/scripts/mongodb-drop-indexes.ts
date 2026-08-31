import '../lib/loadenv';
import { db } from '../lib/mongodb';
import { dropAllIndexes } from "../../src/infrastructure/mongodb/drop-indexes";

async function main() {
    await dropAllIndexes(db);
    console.log("Indexes dropped (non-_id)");
}

main().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exit(1);
});