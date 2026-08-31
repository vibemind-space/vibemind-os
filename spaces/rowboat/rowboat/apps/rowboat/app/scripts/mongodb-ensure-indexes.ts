import '../lib/loadenv';
import { db } from '../lib/mongodb';
import { ensureAllIndexes } from "../../src/infrastructure/mongodb/ensure-indexes";

async function main() {
    await ensureAllIndexes(db);
    console.log("Indexes ensured");
}

main().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exit(1);
});