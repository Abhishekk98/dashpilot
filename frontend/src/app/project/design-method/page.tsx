import { StepHeader } from "@/components/layout/StepHeader";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { PillTag } from "@/components/ui/PillTag";

/** The three design methods from spec Module 9. All produce a 1280x720 HTML design for the shared import. */
const METHODS = [
  {
    key: "B",
    icon: "auto_awesome",
    title: "Design with DashPilot (AI)",
    description:
      "AI generates a 1280×720 design from your plan, KPIs, business questions and brand colors in a style preset. Pick one of 2–3 variants, restyle and regenerate.",
    points: ["5 style presets", "Validated layout, template fallback", "2–3 preview variants"],
    plan: "Free · Student · Pro · Agency",
    recommended: true,
  },
  {
    key: "C",
    icon: "image_search",
    title: "Design from Reference Image",
    description:
      "Upload a dashboard you like. AI extracts its style (palette, cards, radius, shadows, fonts, spacing) into an editable profile, then designs your own KPIs in that style.",
    points: ["Editable style profile", "Takes the style, not the layout", "Same validator as AI design"],
    plan: "Pro · Agency",
    recommended: false,
  },
  {
    key: "A",
    icon: "draw",
    title: "Design with Google Stitch",
    description:
      "DashPilot writes a ready-to-paste Google Stitch prompt. Design in Stitch, then upload the HTML export (or an image) back here.",
    points: ["Custom Stitch prompt", "HTML export import", "Image fallback with mapping editor"],
    plan: "Pro · Agency",
    recommended: false,
  },
];

/** Step 7: Choose design method (static for now; each method is built in its own step). */
export default async function DesignMethodPage({ searchParams }: { searchParams: Promise<{ project?: string }> }) {
  const { project } = await searchParams;

  return (
    <div className="flex flex-col w-full">
      <StepHeader step={7} title="Choose Design Method" projectId={project} badge={project ? "Draft" : undefined} />

      <section className="space-y-2 mb-8">
        <h1 className="font-headline-xl text-headline-xl text-on-surface font-light tracking-tight">How should your dashboard be designed?</h1>
        <p className="font-body-lg text-body-lg text-on-surface-variant max-w-3xl">
          Every method produces the same 1280×720 design, which goes through one shared Design Import and Power BI build.
        </p>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10">
        {METHODS.map((m) => (
          <Card key={m.key} interactive className={`flex flex-col gap-5 relative ${m.recommended ? "ring-2 ring-primary-container" : ""}`}>
            {m.recommended && (
              <span className="absolute -top-3 right-6">
                <PillTag tone="dark" dot size="md">
                  Recommended
                </PillTag>
              </span>
            )}
            <div className="flex items-center justify-between gap-3">
              <div className="w-11 h-11 rounded-full bg-secondary-container/40 text-on-surface flex items-center justify-center">
                <Icon name={m.icon} className="text-[22px]" />
              </div>
              <PillTag mono size="md">
                Option {m.key}
              </PillTag>
            </div>
            <div className="space-y-1.5">
              <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">{m.title}</h2>
              <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">{m.description}</p>
            </div>
            <ul className="flex flex-col gap-2">
              {m.points.map((p) => (
                <li key={p} className="flex items-center gap-2 font-body-md text-body-md text-on-surface">
                  <Icon name="check_circle" className="text-[18px] text-secondary" />
                  {p}
                </li>
              ))}
            </ul>
            <div className="mt-auto pt-2 flex items-center justify-between gap-3">
              <span className="font-code-sm text-code-sm text-on-surface-variant">{m.plan}</span>
              <PillTag tone="warning">Coming soon</PillTag>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
