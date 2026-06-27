import { cn } from "@/lib/utils";

/**
 * AdGenieHQ brand mark — a stylized "A" monogram on the grape-gradient tile.
 *
 * Used everywhere a small logo appears (marketing nav, dashboard sidebar /
 * topbar, auth layout, footer). When the time comes to replace it with a
 * commissioned brand asset, swap this one component and every surface
 * updates at once.
 *
 * Sizing:
 *   - "sm"  = 28px (compact spots)
 *   - "md"  = 32px (default — header, footer, sidebar)
 *   - "lg"  = 40px (auth-page hero)
 */
export function Logomark({
  size = "md",
  className,
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const dim =
    size === "sm" ? "size-7" : size === "lg" ? "size-10" : "size-8";
  const radius = size === "lg" ? "rounded-xl" : "rounded-lg";
  // Inset for the inner SVG so the strokes don't kiss the gradient edge.
  const innerPad = size === "sm" ? "p-[6px]" : size === "lg" ? "p-[9px]" : "p-[7px]";

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center bg-grape-gradient text-white shadow-sm",
        dim,
        radius,
        innerPad,
        className,
      )}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-full w-full"
      >
        {/* Diagonal strokes forming the apex of the "A" */}
        <path d="M5 19 L12 4.5 L19 19" />
        {/* Crossbar */}
        <path d="M8.2 14.5 H15.8" />
      </svg>
    </span>
  );
}
