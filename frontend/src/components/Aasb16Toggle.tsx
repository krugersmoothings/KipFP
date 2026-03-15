import { useAppStore } from "@/stores/app";

export default function Aasb16Toggle() {
  const { includeAasb16, toggleAasb16 } = useAppStore();

  return (
    <div className="relative ml-1 border-l pl-3">
      <button
        onClick={toggleAasb16}
        className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
          includeAasb16
            ? "text-muted-foreground hover:bg-accent hover:text-foreground"
            : "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400"
        }`}
        title={includeAasb16 ? "AASB16 included (statutory view)" : "AASB16 excluded (ex-lease view)"}
      >
        <span
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
            includeAasb16 ? "bg-primary" : "bg-amber-500"
          }`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
              includeAasb16 ? "translate-x-[18px]" : "translate-x-[3px]"
            }`}
          />
        </span>
        <span>{includeAasb16 ? "AASB16" : "Ex-lease"}</span>
      </button>
    </div>
  );
}
