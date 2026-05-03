import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { MarketingLayout } from "@/features/marketing/MarketingLayout";
import { ApiError, apiFetch } from "@/lib/api-client";
import { renderMarkdown } from "@/lib/markdown";
import type { PublicBlogPost } from "@/types/api";


/**
 * Public blog detail page (route: /blog/:slug).
 *
 * Pulls the post body via `GET /public/blog/{slug}` and renders it with the
 * tiny in-house markdown renderer. 404 → friendly empty state with a link
 * back to the archive. We deliberately don't ship a full `react-markdown`
 * dep — the editor produces a narrow subset and renderMarkdown covers it.
 */
export function BlogPostPage() {
  const { slug } = useParams<{ slug: string }>();
  const post = useQuery<PublicBlogPost>({
    queryKey: ["public-blog", slug],
    queryFn: () =>
      apiFetch(`/public/blog/${encodeURIComponent(slug ?? "")}`, {
        skipAuth: true,
      }),
    enabled: !!slug,
    retry: false,
  });

  if (post.isLoading) {
    return (
      <MarketingLayout>
        <div className="mx-auto max-w-3xl px-4 py-20 text-sm text-slate-400 sm:px-6">
          Loading…
        </div>
      </MarketingLayout>
    );
  }

  if (post.error || !post.data) {
    const isNotFound =
      post.error instanceof ApiError && post.error.code === "blog_post_not_found";
    return (
      <MarketingLayout>
        <NotFoundState notFound={!!isNotFound} />
      </MarketingLayout>
    );
  }

  return (
    <MarketingLayout>
      <PostHeader post={post.data} />
      <PostBody body={post.data.body} />
      <PostFooter post={post.data} />
    </MarketingLayout>
  );
}


function PostHeader({ post }: { post: PublicBlogPost }) {
  const date = post.published_at
    ? new Date(post.published_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  return (
    <section className="border-b border-slate-100 bg-white">
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <Link
          to="/blog"
          className="inline-flex items-center gap-1 text-sm font-medium text-grape-700 hover:text-grape-800"
        >
          ← The blog
        </Link>
        {post.keywords && post.keywords.length > 0 ? (
          <div className="mt-6 flex flex-wrap gap-1.5">
            {post.keywords.slice(0, 4).map((k) => (
              <span
                key={k}
                className="rounded-full bg-grape-100 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-grape-700"
              >
                {k}
              </span>
            ))}
          </div>
        ) : null}
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl lg:text-5xl">
          {post.title}
        </h1>
        {post.excerpt ? (
          <p className="mt-4 max-w-2xl text-lg text-slate-600">{post.excerpt}</p>
        ) : null}
        {date ? (
          <p className="mt-4 text-xs uppercase tracking-wider text-slate-400">
            {date}
          </p>
        ) : null}
      </div>

      {post.image_url ? (
        <div className="mx-auto max-w-5xl px-4 pb-12 sm:px-6">
          <img
            src={post.image_url}
            alt=""
            className="h-auto w-full rounded-2xl border border-slate-100 shadow-elevate"
            loading="eager"
          />
        </div>
      ) : null}
    </section>
  );
}


function PostBody({ body }: { body: string }) {
  return (
    <article className="bg-white">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
        {renderMarkdown(body)}
      </div>
    </article>
  );
}


function PostFooter({ post }: { post: PublicBlogPost }) {
  return (
    <section className="border-t border-slate-100 bg-cloud">
      <div className="mx-auto max-w-3xl px-4 py-12 text-center sm:px-6">
        <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
          Keep reading
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink">
          More from the AdVanta blog
        </h2>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/blog"
            className="rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800"
          >
            Back to all posts
          </Link>
          <Link
            to="/register"
            className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Try AdVanta free
          </Link>
        </div>
        {post.keywords && post.keywords.length > 0 ? (
          <p className="mt-6 text-xs text-slate-400">
            Tagged: {post.keywords.join(" · ")}
          </p>
        ) : null}
      </div>
    </section>
  );
}


function NotFoundState({ notFound }: { notFound: boolean }) {
  return (
    <section className="bg-white">
      <div className="mx-auto max-w-2xl px-4 py-24 text-center sm:px-6">
        <p className="text-xs font-medium uppercase tracking-wider text-grape-700">
          {notFound ? "Post not found" : "Couldn't load this post"}
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink">
          {notFound
            ? "That post doesn't exist (or hasn't been published)."
            : "Something went wrong."}
        </h1>
        <p className="mt-3 text-sm text-slate-600">
          {notFound
            ? "Check the URL, or browse the archive — every published post lives there."
            : "Refresh the page; if the problem persists, we're on it."}
        </p>
        <div className="mt-8">
          <Link
            to="/blog"
            className="inline-block rounded-xl bg-grape px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-grape-800"
          >
            Browse the archive
          </Link>
        </div>
      </div>
    </section>
  );
}
