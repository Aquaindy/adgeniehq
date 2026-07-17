import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { Logomark } from "@/components/Logomark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { APP_NAME } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-cloud">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-surface/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <Logomark />
            <span className="text-sm font-semibold text-ink">{APP_NAME}</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <MarketingLink to="/pricing">Pricing</MarketingLink>
            <MarketingLink to="/about">About</MarketingLink>
            <MarketingLink to="/blog">Blog</MarketingLink>
            <ThemeToggle className="ml-1" />
            <Link
              to="/login"
              className="ml-1 rounded-xl px-3 py-1.5 text-sm font-medium text-grape-700 hover:bg-grape-50"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="rounded-xl bg-grape px-3 py-1.5 text-sm font-medium text-white hover:bg-grape-800"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <SiteFooter />
    </div>
  );
}


/**
 * Three-column footer with real internal routes only — no fake socials, no
 * stub anchors, no "Press" / "Careers" pages we don't actually have. As we
 * add more public pages (changelog, status, docs), drop them into the
 * matching column here.
 */
function SiteFooter() {
  return (
    <footer className="border-t border-slate-200 bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <Link to="/" className="flex items-center gap-2">
              <Logomark />
              <span className="text-sm font-semibold text-ink">{APP_NAME}</span>
            </Link>
            <p className="mt-3 max-w-xs text-sm text-slate-500">
              The AI ad-creation platform. Build, launch, and optimize campaigns
              across Google, Meta &amp; LinkedIn — with specialized agents for
              SEO, content, and conversion behind every move.
            </p>
          </div>

          <FooterColumn title="Product">
            <FooterLink to="/">Overview</FooterLink>
            <FooterLink to="/pricing">Pricing</FooterLink>
            <FooterLink to="/about">About us</FooterLink>
            <FooterLink to="/blog">Blog</FooterLink>
          </FooterColumn>

          {/* Module guides are static HTML in public/ (served by the CDN
              before the SPA rewrite), so they MUST use real <a> anchors —
              a React Router <Link> would client-side route and 404. */}
          <FooterColumn title="Guides">
            <FooterAnchor href="/guides.html">All guides</FooterAnchor>
            <FooterAnchor href="/ads-module.html">Ads module</FooterAnchor>
            <FooterAnchor href="/traffic-module.html">Traffic module</FooterAnchor>
            <FooterAnchor href="/email-marketing-module.html">Email module</FooterAnchor>
            <FooterAnchor href="/seo-module.html">SEO &amp; GEO module</FooterAnchor>
            <FooterAnchor href="/website-module.html">Website module</FooterAnchor>
          </FooterColumn>

          <FooterColumn title="Get started">
            <FooterLink to="/register">Create your workspace</FooterLink>
            <FooterLink to="/login">Sign in</FooterLink>
            <FooterLink to="/forgot-password">Forgot password</FooterLink>
          </FooterColumn>

          <FooterColumn title="Legal">
            <FooterLink to="/terms">Terms of service</FooterLink>
            <FooterLink to="/privacy">Privacy policy</FooterLink>
            <FooterLink to="/refund">Refund &amp; cancellation</FooterLink>
          </FooterColumn>
        </div>

        <div className="mt-10 flex flex-col items-start justify-between gap-3 border-t border-slate-100 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center">
          <span>
            © {new Date().getFullYear()} {APP_NAME}. All rights reserved.
          </span>
          <span className="text-slate-400">
            Connected via real OAuth flows. Tokens encrypted at rest.
          </span>
        </div>
      </div>
    </footer>
  );
}


function FooterColumn({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </h4>
      <ul className="mt-3 flex flex-col gap-2 text-sm">{children}</ul>
    </div>
  );
}


function FooterLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <li>
      <Link to={to} className="text-slate-600 transition hover:text-grape-700">
        {children}
      </Link>
    </li>
  );
}


// Plain anchor (full-page navigation) for static files outside the SPA router.
function FooterAnchor({ href, children }: { href: string; children: ReactNode }) {
  return (
    <li>
      <a href={href} className="text-slate-600 transition hover:text-grape-700">
        {children}
      </a>
    </li>
  );
}


function MarketingLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        cn(
          "rounded-xl px-3 py-1.5 transition",
          isActive
            ? "text-grape-700"
            : "text-slate-600 hover:bg-slate-100 hover:text-ink",
        )
      }
    >
      {children}
    </NavLink>
  );
}
