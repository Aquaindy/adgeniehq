import { API_BASE_URL } from "@/lib/constants";

export function GoogleSignInButton({
  label = "Continue with Google",
  redirectTo,
}: {
  label?: string;
  redirectTo?: string;
}) {
  // Hand the browser straight to the backend's /auth/google/start route. The
  // backend sets a state cookie and 307s to Google. We can't fetch() it ourselves
  // because the Set-Cookie + 3xx + cross-origin redirect dance has to happen at
  // the document level.
  const params = new URLSearchParams();
  if (redirectTo) params.set("redirect_to", redirectTo);
  const href = `${API_BASE_URL.replace(/\/$/, "")}/auth/google/start${
    params.toString() ? `?${params.toString()}` : ""
  }`;

  return (
    <a
      href={href}
      className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-ink shadow-sm outline-none transition hover:border-slate-300 hover:bg-slate-50 focus:ring-2 focus:ring-grape-200"
    >
      <GoogleGlyph />
      {label}
    </a>
  );
}


function GoogleGlyph() {
  // Google "G" logo, inline SVG so we don't ship an extra asset.
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 18 18"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="#4285F4"
        d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.614z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.467-.806 5.956-2.181l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
      />
    </svg>
  );
}
