import { Icon } from "@/components/ui/Icon";
import type { Archetype } from "@/lib/api";
import { ARCHETYPES } from "@/lib/context";

/** "Dashboard Style Archetypes": five selectable canvas styles with miniature previews. */
export function ArchetypeGrid({ value, onChange }: { value: Archetype; onChange: (a: Archetype) => void }) {
  return (
    <section className="rounded-card bg-surface-container-lowest/75 backdrop-blur-xl p-7 shadow-card mb-10">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
            <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">Dashboard Style Archetypes</h2>
          </div>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Select visual canvas behavior. The layout engine formats card radii, shadow depth, and visualization themes accordingly.
          </p>
        </div>
        <span className="font-code-sm text-code-sm text-on-surface-variant">Adaptive Power BI Theme</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4" role="radiogroup" aria-label="Dashboard style">
        {ARCHETYPES.map((a) => {
          const on = a.id === value;
          const p = a.preview;
          return (
            <button
              key={a.id}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(a.id)}
              className={`relative flex flex-col justify-between p-4 rounded-2xl text-left transition-all duration-200 group ${
                on
                  ? "bg-surface-container-lowest shadow-[0_12px_28px_-6px_rgba(35,35,35,0.12)] ring-2 ring-primary-container"
                  : "bg-surface-container-low/70 hover:bg-surface-container"
              }`}
            >
              {on && (
                <span className="absolute -top-3 right-4 px-3 py-0.5 rounded-full bg-primary-container text-secondary-container font-label-sm text-label-sm font-semibold flex items-center gap-1 shadow-sm">
                  <Icon name="check_circle" className="text-[14px]" />
                  Selected
                </span>
              )}
              <span className="block">
                <span className={`w-full h-24 rounded-xl ${p.canvas} p-2 flex flex-col justify-between mb-3 shadow-inner overflow-hidden`}>
                  <span className="flex items-center justify-between">
                    <span className={`w-9 h-1.5 rounded-full ${p.bar}`} />
                    <span className={`w-2 h-2 rounded-full ${p.dot}`} />
                  </span>
                  <span className="grid grid-cols-3 gap-1">
                    {p.tiles.map((t, i) => (
                      <span key={i} className={`h-6 rounded ${t}`} />
                    ))}
                  </span>
                  <span className={`h-4 rounded w-full ${p.strip}`} />
                </span>
                <span className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-title-lg text-title-lg text-on-surface font-semibold">{a.title}</span>
                  <span
                    className={`font-label-sm text-[10px] px-2 py-0.5 rounded-full shrink-0 ${
                      on ? "bg-secondary-container/40 text-on-surface font-semibold" : "bg-surface-container text-on-surface-variant"
                    }`}
                  >
                    {a.tag}
                  </span>
                </span>
                <span className="block font-body-md text-[13px] text-on-surface-variant leading-snug">{a.description}</span>
              </span>
              <span className="pt-3 mt-2 flex items-center justify-between">
                <span className={`font-code-sm text-[10px] ${on ? "text-secondary font-semibold" : "text-on-surface-variant"}`}>{a.footer}</span>
                <span
                  className={`w-6 h-6 rounded-full flex items-center justify-center ${
                    on ? "bg-secondary-container text-on-secondary-fixed" : "bg-surface-container text-on-surface-variant group-hover:text-on-surface"
                  }`}
                >
                  <Icon name={on ? "check" : "chevron_right"} className="text-[14px]" />
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
