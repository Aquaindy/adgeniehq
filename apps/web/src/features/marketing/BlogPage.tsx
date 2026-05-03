import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { MarketingLayout } from "@/features/marketing/MarketingLayout";
import { apiFetch } from "@/lib/api-client";
import type { PublicBlogPostSummary } from "@/types/api";


/**
 * Public blog archive (the marketing /blog route).
 *
 * Pulls from `GET /public/blog`, which is gated behind
 * `MARKETING_WORKSPACE_SLUG`. Two states:
 *   1. Endpoint returns posts → render the grid.
 *   2. Endpoint returns empty (no marketing workspace configured, or no
 *      posts yet) → show the coming-soon explainer + topic preview so the
 *      page is usable from day one.
 */
export function BlogPage() {
  const posts = useQuery<PublicBlogPostSummary[]>({
    queryKey: ["public-blog"],
    queryFn: () => apiFetch("/public/blog", { skipAuth: true }),
    retry: false,
  });

  const hasPosts = !!posts.data && posts.data.length > 0;

  return (
    <MarketingLayout>
      <BlogHero hasPosts={hasPosts} />
      {hasPosts ? (
        <ArchiveGrid posts={posts.data!} />
      ) : (
        <>
          <ComingSoonNotice />
          <UpcomingTopics />
        </>
      )}
      <BlogFooterCta />
    </MarketingLayout>
  );
}


function BlogHero({ hasPosts }: { hasPosts: boolean }) {
  return (
    <section className="relative overflow-hidden bg-grape-soft">
      <div
        aria-hidden
        className="pointer-events-none absolute -left-32 top-[-10rem] h-[24rem] w-[24rem] rounded-full bg-grape-gradient opacity-20 blur-3xl"
      />
      <div className="relative mx-auto max-w-4xl px-4 py-20 sm:px-6 sm:py-24">
        <p className="inline-flex items-center gap-2 rounded-full border border-grape-200 bg-white/70 px-3 py-1 text-xs font-medium uppercase tracking-wider text-grape-700 backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-grape-700" />
          The AdVanta blog
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
          Growth playbooks,
          <br />
          straight from the agents.
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-slate-600">
          Hands-on guides for paid ads, SEO &amp; GEO, conversion, and
          operating an AI growth team.
          {hasPosts ? null : (
            <span> Written from the same data the AdVanta agents read every day.</span>
          )}
        </p>
      </div>
    </section>
  );
}


function ArchiveGrid({ posts }: { posts: PublicBlogPostSummary[] }) {
  return (
    <section className="bg-cloud">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {posts.map((p) => (
            <ArchiveCard key={p.id} post={p} />
          ))}
        </div>
      </div>
    </section>
  );
}


function ArchiveCard({ post }: { post: PublicBlogPostSummary }) {
  const date = post.published_at
    ? new Date(post.published_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;
  return (
    <Link
      to={`/blog/${post.slug}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-card transition hover:shadow-elevate"
    >
      {post.image_url ? (
        <div className="aspect-[16/9] w-full overflow-hidden bg-grape-soft">
          <img
            src={post.image_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition group-hover:scale-[1.02]"
          />
        </div>
      ) : (
        <div className="aspect-[16/9] w-full bg-grape-gradient opacity-90" />
      )}
      <div className="flex flex-1 flex-col gap-2 p-5">
        {post.keywords && post.keywords.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {post.keywords.slice(0, 2).map((k) => (
              <span
                key={k}
                className="rounded-full bg-grape-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-grape-700"
              >
                {k}
              </span>
            ))}
          </div>
        ) : null}
        <h2 className="text-lg font-semibold text-ink group-hover:text-grape-700">
          {post.title}
        </h2>
        {post.excerpt ? (
          <p className="line-clamp-3 text-sm text-slate-600">{post.excerpt}</p>
        ) : null}
        <span className="mt-auto pt-2 text-xs uppercase tracking-wider text-slate-400">
          {date ?? "draft"}
        </span>
      </div>
    </Link>
  );
}


function ComingSoonNotice() {
  return (
    <section className="bg-white">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <div className="rounded-2xl border border-slate-200 bg-cloud px-6 py-8 sm:px-10 sm:py-10">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            Coming soon
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            We're publishing the blog from inside the product.
          </h2>
          <p className="mt-3 text-base text-slate-600">
            The blog you'll read here is the same surface AdVanta workspaces
            use to draft, review, and publish — Content-Drafts in the
            dashboard graduate to public posts on this domain. Once we drop
            the first set of posts, this page becomes the live archive.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link
              to="/register"
              className="rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800"
            >
              Create your workspace
            </Link>
            <Link
              to="/welcome"
              className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              See the platform
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}


function UpcomingTopics() {
  const topics = [
    { tag: "Paid ads", title: "Cutting wasted spend without cutting reach" },
    { tag: "SEO & GEO", title: "Opportunity scoring that survives a redesign" },
    { tag: "Conversion", title: "A/B tests that actually settle arguments" },
    { tag: "Operations", title: "What an AI growth team does on day one" },
    { tag: "Safety", title: "Designing autopilot you can sleep through" },
    { tag: "Reporting", title: "Reports that read in 90 seconds" },
  ];
  return (
    <section className="bg-cloud">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
            Topics on deck
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            What we'll publish first.
          </h2>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {topics.map((t) => (
            <article
              key={t.title}
              className="rounded-2xl border border-slate-100 bg-white p-5 shadow-card"
            >
              <span className="inline-flex w-fit rounded-full bg-grape-100 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-grape-700">
                {t.tag}
              </span>
              <h3 className="mt-3 text-base font-semibold text-ink">
                {t.title}
              </h3>
              <span className="mt-3 block text-xs uppercase tracking-wider text-slate-400">
                Coming soon
              </span>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}


function BlogFooterCta() {
  return (
    <section className="bg-white">
      <div className="mx-auto max-w-4xl px-4 py-16 text-center sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          Want the next post in your inbox?
        </h2>
        <p className="mt-3 text-sm text-slate-600">
          Create a free workspace — every active workspace owner gets a
          heads-up when new posts land. No separate marketing list to opt
          out of later.
        </p>
        <div className="mt-6">
          <Link
            to="/register"
            className="inline-block rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800"
          >
            Create your workspace
          </Link>
        </div>
      </div>
    </section>
  );
}
