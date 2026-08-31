"use client";
import { Alert } from "@heroui/react";

export default function Error(props: { error: Error }) {
    return <Alert
        color="danger"
        title="Error loading workflow"
    >
        There was an error loading the workflow: {props.error.message}
    </Alert>;
}