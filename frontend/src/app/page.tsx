import { PillButton } from "@/components/ui/PillButton";
import { PlaceholderCard } from "@/components/ui/PlaceholderCard";

/** Home dashboard. Step 1 only provides the shell; the full design is built in a later step. */
export default function HomePage() {
  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-2">
        <h1 className="font-display-lg text-display-lg text-on-surface">Welcome to DashPilot</h1>
        <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl">
          Your AI co-analyst for Power BI. Upload data and DashPilot takes it all the way to a finished PBIP project.
        </p>
      </section>
      <PlaceholderCard
        icon="dashboard"
        title="Home dashboard"
        description="Project overview, dataset health and pipeline status will appear here."
      />
      <div>
        <PillButton href="/project/upload" arrow>
          Start New Project
        </PillButton>
      </div>
    </div>
  );
}
