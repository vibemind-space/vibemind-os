import { XIcon } from "lucide-react";

export function List({
    items,
    onRemove,
}: {
    items: {
        id: string;
        node: React.ReactNode;
    }[];
    onRemove: (id: string) => void;
}) {
    return <div className="ml-4 flex flex-col gap-2 items-start">
        {items.map((item) => (
            <ListItem key={item.id} onRemove={() => onRemove(item.id)}>
                {item.node}
            </ListItem>
        ))}
    </div>;
}

export function ListItem({
    children,
    onRemove,
}: {
    children: React.ReactNode;
    onRemove: () => void;
}) {
    return <div className="flex items-center gap-2">
        <div className="bg-gray-400 rounded-full w-1 h-1"></div>
        <div className="flex items-center gap-2 bg-gray-100 rounded-md px-2 py-1 group">
            <div className="grow text-sm">{children}</div>
            <button onClick={onRemove} className="hidden rounded-md hover:bg-gray-500 text-gray-500 hover:text-white group-hover:block">
                <XIcon size={16} />
            </button>
        </div>
    </div>
}