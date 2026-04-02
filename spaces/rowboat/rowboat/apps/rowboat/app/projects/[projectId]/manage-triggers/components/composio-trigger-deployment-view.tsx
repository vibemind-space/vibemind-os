'use client';

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Spinner } from "@heroui/react";
import { Panel } from "@/components/common/panel-common";
import { Button } from "@/components/ui/button";
import { ArrowLeftIcon, Trash2Icon } from "lucide-react";
import { z } from "zod";
import { ComposioTriggerDeployment } from "@/src/entities/models/composio-trigger-deployment";
import { deleteComposioTriggerDeployment, fetchComposioTriggerDeployment } from "@/app/actions/composio.actions";
import { JobsList } from "@/app/projects/[projectId]/jobs/components/jobs-list";
import { JobFiltersSchema } from "@/src/application/repositories/jobs.repository.interface";

export function ComposioTriggerDeploymentView({ projectId, deploymentId }: { projectId: string; deploymentId: string; }) {
    const [deployment, setDeployment] = useState<z.infer<typeof ComposioTriggerDeployment> | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [deleting, setDeleting] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

    const jobsFilters = useMemo(() => ({ composioTriggerDeploymentId: deploymentId } satisfies z.infer<typeof JobFiltersSchema>), [deploymentId]);

    useEffect(() => {
        let ignore = false;
        (async () => {
            setLoading(true);
            try {
                const res = await fetchComposioTriggerDeployment({ deploymentId });
                if (ignore) return;
                setDeployment(res);
            } finally {
                if (!ignore) setLoading(false);
            }
        })();
        return () => { ignore = true; };
    }, [deploymentId]);

    const title = useMemo(() => {
        if (!deployment) return 'External Trigger';
        return `External Trigger ${deployment.id}`;
    }, [deployment]);

    const formatDate = (iso: string) => new Date(iso).toLocaleString();

    const handleDelete = async () => {
        if (!deployment) return;
        setDeleting(true);
        try {
            await deleteComposioTriggerDeployment({ projectId, deploymentId: deployment.id });
            window.location.href = `/projects/${projectId}/manage-triggers?tab=triggers`;
        } catch (e) {
            console.error(e);
            alert('Failed to delete trigger');
        } finally {
            setDeleting(false);
            setShowDeleteConfirm(false);
        }
    };

    return (
        <>
            <Panel
                title={
                    <div className="flex items-center gap-3">
                        <Link href={`/projects/${projectId}/manage-triggers?tab=triggers`}>
                            <Button variant="secondary" size="sm" startContent={<ArrowLeftIcon className="w-4 h-4" />} className="whitespace-nowrap">
                                Back
                            </Button>
                        </Link>
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}</div>
                    </div>
                }
                rightActions={
                    <div className="flex items-center gap-3">
                        <Button
                            onClick={() => setShowDeleteConfirm(true)}
                            variant="secondary"
                            size="sm"
                            startContent={<Trash2Icon className="w-4 h-4" />}
                            className="bg-red-50 hover:bg-red-100 text-red-700 dark:bg-red-950 dark:hover:bg-red-900 dark:text-red-400 border border-red-200 dark:border-red-800 whitespace-nowrap"
                        >
                            Delete
                        </Button>
                    </div>
                }
            >
                <div className="h-full overflow-auto px-4 py-4">
                    <div className="max-w-[1024px] mx-auto">
                        {loading && (
                            <div className="flex items-center gap-2">
                                <Spinner size="sm" />
                                <div>Loading...</div>
                            </div>
                        )}
                        {!loading && deployment && (
                            <div className="flex flex-col gap-6">
                                <div className="bg-gray-50 dark:bg-gray-800/50 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                                    <div className="grid grid-cols-2 gap-4 text-sm">
                                        <div>
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Deployment ID:</span>
                                            <span className="ml-2 font-mono text-gray-600 dark:text-gray-400">{deployment.id}</span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Trigger Type:</span>
                                            <span className="ml-2 font-mono text-gray-600 dark:text-gray-400">{deployment.triggerTypeSlug}</span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Toolkit:</span>
                                            <span className="ml-2 font-mono text-gray-600 dark:text-gray-400">{deployment.toolkitSlug}</span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Connected Account:</span>
                                            <span className="ml-2 font-mono text-gray-600 dark:text-gray-400">{deployment.connectedAccountId}</span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Created:</span>
                                            <span className="ml-2 font-mono text-gray-600 dark:text-gray-400">{formatDate(deployment.createdAt)}</span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Updated:</span>
                                            <span className="ml-2 font-mono text-gray-600 dark:text-gray-400">{formatDate(deployment.updatedAt)}</span>
                                        </div>
                                        <div className="col-span-2">
                                            <span className="font-semibold text-gray-700 dark:text-gray-300">Trigger Config:</span>
                                            <pre className="mt-2 bg-gray-100 dark:bg-gray-900 p-3 rounded text-xs overflow-x-auto border border-gray-200 dark:border-gray-700 font-mono">
{JSON.stringify(deployment.triggerConfig, null, 2)}
                                            </pre>
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                                    <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-3">Jobs Created by This Trigger</h3>
                                    <JobsList projectId={projectId} filters={jobsFilters} showTitle={false} />
                                </div>
                            </div>
                        )}
                        {!loading && !deployment && (
                            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                                <div className="text-sm font-mono">Trigger deployment not found.</div>
                            </div>
                        )}
                    </div>
                </div>
            </Panel>

            {showDeleteConfirm && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md mx-4">
                        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">Delete External Trigger</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Are you sure you want to delete this external trigger? This will remove the linked webhook in Composio and delete this deployment.</p>
                        <div className="flex gap-3 justify-end">
                            <Button variant="secondary" onClick={() => setShowDeleteConfirm(false)} disabled={deleting} className="whitespace-nowrap">Cancel</Button>
                            <Button
                                variant="secondary"
                                onClick={handleDelete}
                                isLoading={deleting}
                                startContent={<Trash2Icon className="w-4 h-4" />}
                                className="bg-red-50 hover:bg-red-100 text-red-700 dark:bg-red-950 dark:hover:bg-red-900 dark:text-red-400 border border-red-200 dark:border-red-800 whitespace-nowrap"
                            >
                                {deleting ? 'Deleting...' : 'Delete'}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}


