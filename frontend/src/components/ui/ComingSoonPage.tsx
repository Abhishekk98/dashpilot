import { PlaceholderCard } from "./PlaceholderCard";

/** Top-nav sections that appear in the designs but are outside V1 scope. */
export function ComingSoonPage({ title }: { title: string }) {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="font-headline-xl text-headline-xl text-on-surface">{title}</h1>
      <PlaceholderCard icon="schedule" title={title} description="This section is planned after the V1 MVP." />
    </div>
  );
}
