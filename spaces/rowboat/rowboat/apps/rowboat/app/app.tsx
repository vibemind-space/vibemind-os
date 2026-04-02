'use client';
import Image from 'next/image';
import logo from "@/public/logo.png";
import { useUser } from "@auth0/nextjs-auth0";
import { useRouter } from "next/navigation";
import { Spinner } from "@heroui/react";

export function App() {
    const router = useRouter();
    const { user, isLoading } = useUser();

    if (user) {
        router.push("/projects");
    }

    // Add auto-redirect for non-authenticated users
    if (!isLoading && !user) {
        router.push("/auth/login");
    }

    return (
        <div className="min-h-screen w-full bg-[url('/landing-bg.jpg')] bg-cover bg-center flex flex-col items-center justify-between py-10">
            {/* Main content box */}
            <div className="flex-1 flex items-center justify-center">
                <div className="bg-white/70 backdrop-blur-sm rounded-xl p-10 flex flex-col items-center gap-8 shadow-lg">
                    <Image
                        src={logo}
                        alt="RowBoat Logo"
                        height={40}
                    />
                    {(isLoading || !user) && <Spinner size="sm" />}
                    {user && <div className="flex items-center gap-2">
                        <Spinner size="sm" />
                        <div className="text-sm text-gray-400">Welcome, {user.name}</div>
                    </div>}
                </div>
            </div>

            {/* Footer */}
            <div className="flex flex-col items-center gap-2 text-xs text-white/70">
                <div>&copy; 2025 RowBoat Labs</div>
            </div>
        </div>
    );
}
