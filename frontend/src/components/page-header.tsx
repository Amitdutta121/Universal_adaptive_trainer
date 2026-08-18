/** The heading block every section page opens with. */

import { TaxonomySelector } from "@/components/taxonomy-selector";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

export function PageHeader({
  title,
  summary,
  actions,
  showSidebarTrigger = true,
  showTaxonomySelector = true,
}: {
  title: string;
  summary?: string;
  actions?: React.ReactNode;
  showSidebarTrigger?: boolean;
  showTaxonomySelector?: boolean;
}) {
  return (
    <header className="app-page-header">
      <div className="flex items-center gap-2">
        {showSidebarTrigger ? (
          <>
            <SidebarTrigger className="-ml-1 text-muted-foreground" />
            <Separator orientation="vertical" className="mr-1 h-4 bg-border" />
          </>
        ) : null}
        <h1>{title}</h1>
        <div className="ml-auto flex items-center gap-2">
          {showTaxonomySelector ? <TaxonomySelector /> : null}
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      </div>
      {summary ? <p className="app-page-summary">{summary}</p> : null}
    </header>
  );
}
