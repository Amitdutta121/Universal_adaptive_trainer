/** The heading block every section page opens with. */

import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

export function PageHeader({
  title,
  summary,
  actions,
}: {
  title: string;
  summary?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="app-page-header">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1 text-muted-foreground" />
        <Separator orientation="vertical" className="mr-1 h-4 bg-border" />
        <h1>{title}</h1>
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
      </div>
      {summary ? <p className="app-page-summary">{summary}</p> : null}
    </header>
  );
}
