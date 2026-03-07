import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-12 flex items-center border-b border-border px-2 shrink-0 bg-card/50 backdrop-blur-sm">
            <SidebarTrigger className="ml-1" />
            <div className="ml-auto flex items-center gap-2 pr-2">
              <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Connected</span>
            </div>
          </header>
          <main className="flex-1 flex flex-col overflow-hidden">
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
