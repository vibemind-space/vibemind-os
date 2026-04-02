"use client";
import { Spinner } from "@heroui/react";

export default function Loading() {
    return <div className="flex flex-col gap-4">
        <Spinner size="sm" />
    </div>;
}