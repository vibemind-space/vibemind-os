import { App } from "./app";
import { redirect } from "next/navigation";
import { USE_AUTH } from "./lib/feature_flags";

export const dynamic = 'force-dynamic';

export default function Home() {
    if (!USE_AUTH) {
        redirect("/projects");
    }
    return <App />
}