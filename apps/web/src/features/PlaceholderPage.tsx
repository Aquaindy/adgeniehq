import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

type PlaceholderProps = {
  title: string;
  milestone: string;
  description: string;
};

export function PlaceholderPage({ title, milestone, description }: PlaceholderProps) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">{milestone}</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{title}</h1>
      </header>
      <EmptyState
        title="Not yet available"
        description={description}
        action={<Button variant="secondary" disabled>Pending build</Button>}
      />
    </div>
  );
}
