export default async function Layout({
    params,
    children
}: {
    params: Promise<{ projectId: string }>
    children: React.ReactNode
}) {
    return children;
}