export default function WorkspacePage(): React.JSX.Element {
    return (
        <main className="h-dvh">
            <iframe
                title="Hedgebox workspace"
                src="/files"
                allow="clipboard-write 'none'"
                className="block h-full w-full border-0"
            />
        </main>
    )
}
