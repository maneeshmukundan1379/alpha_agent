import type { RequirementsPreviewResponse } from "../types";

interface RequirementsPreviewProps {
  preview: RequirementsPreviewResponse | null;
}

export function RequirementsPreview({ preview }: RequirementsPreviewProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-violet-950/20">
      <div className="mb-5">
        <h3 className="text-lg font-semibold text-white">Requirements Preview</h3>
        <p className="mt-1 text-sm text-slate-300">
          Review the dependencies and files that will be generated for the new agent.
        </p>
      </div>

      {!preview ? (
        <div className="rounded-2xl border border-dashed border-white/10 bg-slate-900/40 px-4 py-5 text-sm text-slate-400">
          Update the form to preview dependencies and generated files.
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <div className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200">
              Python Requirements
            </div>
            <div className="flex flex-wrap gap-2">
              {preview.requirements.map((requirement) => (
                <span
                  key={requirement}
                  className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-100"
                >
                  {requirement}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <div className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-violet-200">
              Generated Files
            </div>
            <ul className="space-y-2 text-sm text-slate-200">
              {preview.generated_files.map((file) => (
                <li key={file} className="rounded-xl bg-white/5 px-3 py-2">
                  {file}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
