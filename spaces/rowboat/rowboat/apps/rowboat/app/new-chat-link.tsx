import Link from "next/link";

export function NewChatLink({demo}: {demo: string}) { 
    return <Link
        className="mt-2 text-black flex rounded-lg border border-gray-400 px-4 py-2 disabled:text-gray-400"
        href={`/new/${demo}`}
    >
        Start new chat &rarr;
    </Link>
}