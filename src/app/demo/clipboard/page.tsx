import Link from 'next/link'

export default function ClipboardDemoPage(): React.JSX.Element {
    return (
        <main className="p-4 space-y-4">
            <h1 className="text-2xl font-bold">Clipboard permission scenario</h1>
            <p>In the workspace below, choose Share, then Copy. Clipboard writes are blocked by the frame's permissions policy.</p>
            <Link className="link" href="/demo">Back to exception demos</Link>
            <iframe
                title="Hedgebox workspace with clipboard access denied"
                src="/files/file1"
                allow="clipboard-write 'none'"
                className="w-full h-[80vh] border border-base-300 rounded-lg"
            />
        </main>
    )
}
