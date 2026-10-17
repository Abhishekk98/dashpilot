import { Card } from "./Card";
import { Icon } from "./Icon";
import { PillTag } from "./PillTag";

/** Glass card used for screens that are scaffolded but not built yet. */
export function PlaceholderCard({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <Card padding="px-7 py-16" className="flex flex-col items-center text-center gap-3">
      <div className="w-14 h-14 rounded-full bg-surface-container flex items-center justify-center">
        <Icon name={icon} className="text-[28px] text-on-surface" />
      </div>
      <h2 className="font-headline-lg text-headline-lg text-on-surface tracking-tight">{title}</h2>
      <p className="font-body-md text-body-md text-on-surface-variant max-w-md">{description}</p>
      <PillTag tone="accent" size="md" className="mt-2">
        Coming soon
      </PillTag>
    </Card>
  );
}
