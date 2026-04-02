import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function MarkdownContent({ content }: { content: string }) {
    return <Markdown
        className="overflow-auto break-words"
        remarkPlugins={[remarkGfm]}
        components={{
            strong({ children }) {
                return <span className="font-semibold">{children}</span>
            },
            p({ children }) {
                return <p className="py-1">{children}</p>
            },
            ul({ children }) {
                return <ul className="py-1 pl-5 list-disc">{children}</ul>
            },
            ol({ children }) {
                return <ul className="py-1 pl-5 list-decimal">{children}</ul>
            },
            h3({ children }) {
                return <h3 className="font-semibold">{children}</h3>
            },
            table({ children }) {
                return <table className="my-1 border-collapse border border-gray-400 rounded">{children}</table>
            },
            th({ children }) {
                return <th className="px-2 py-1 border-collapse border border-gray-300 rounded">{children}</th>
            },
            td({ children }) {
                return <td className="px-2 py-1 border-collapse border border-gray-300 rounded">{children}</td>
            },
            blockquote({ children }) {
                return <blockquote className='bg-gray-200 px-1'>{children}</blockquote>;
            },
            a(props) {
                const { children, ...rest } = props
                return <a className="inline-flex items-center gap-1" target="_blank" {...rest} >
                    <span className='underline'>
                        {children}
                    </span>
                    <svg className="w-[16px] h-[16px]" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24">
                        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M18 14v4.833A1.166 1.166 0 0 1 16.833 20H5.167A1.167 1.167 0 0 1 4 18.833V7.167A1.166 1.166 0 0 1 5.167 6h4.618m4.447-2H20v5.768m-7.889 2.121 7.778-7.778" />
                    </svg>
                </a>
            },
        }}
    >
        {content}
    </Markdown>;
}