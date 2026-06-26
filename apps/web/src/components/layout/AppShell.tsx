import { Outlet } from "react-router-dom";

import { MobileNav } from "@/components/layout/MobileNav";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { EmailVerificationBanner } from "@/features/auth/EmailVerificationBanner";

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <EmailVerificationBanner />
        <Topbar />
        <main className="flex-1 px-4 pb-24 pt-4 sm:px-6 sm:pt-6 lg:pb-8">
          <Outlet />
        </main>
        <MobileNav />
      </div>
    </div>
  );
}
