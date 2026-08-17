export type Tab = { key: string; label: string };

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex gap-4 border-b border-slate-200" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={t.key === active}
          onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-1 pb-2 text-sm font-medium ${
            t.key === active
              ? "border-sky-500 text-sky-600"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
