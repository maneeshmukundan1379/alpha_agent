import type { SecretInput } from "../types";

interface SecretsEditorProps {
  secrets: SecretInput[];
  onChange: (nextSecrets: SecretInput[]) => void;
  suggestedKeys: string[];
  heading?: string;
  description?: string;
}

export function SecretsEditor({
  secrets,
  onChange,
  suggestedKeys,
  heading = "Secrets",
  description = "Save provider keys and runtime credentials for the generated agent.",
}: SecretsEditorProps) {
  const updateSecret = (index: number, field: keyof SecretInput, value: string) => {
    const nextSecrets = secrets.map((secret, secretIndex) =>
      secretIndex === index ? { ...secret, [field]: value } : secret,
    );
    onChange(nextSecrets);
  };

  const addSecret = (key = "", value = "") => {
    onChange([...secrets, { key, value }]);
  };

  const removeSecret = (index: number) => {
    onChange(secrets.filter((_, secretIndex) => secretIndex !== index));
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-cyan-950/20">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-white">{heading}</h3>
          <p className="mt-1 text-sm text-slate-300">{description}</p>
        </div>
        <button
          className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-200 transition hover:bg-cyan-400/20"
          onClick={() => addSecret()}
          type="button"
        >
          Add secret
        </button>
      </div>

      {suggestedKeys.length > 0 ? (
        <div className="mb-4 flex flex-wrap gap-2">
          {suggestedKeys.map((key) => (
            <button
              key={key}
              className="rounded-full border border-violet-400/30 bg-violet-400/10 px-3 py-1 text-xs font-medium text-violet-100 transition hover:bg-violet-400/20"
              onClick={() => {
                if (!secrets.some((secret) => secret.key === key)) {
                  addSecret(key, "");
                }
              }}
              type="button"
            >
              Add {key}
            </button>
          ))}
        </div>
      ) : null}

      <div className="space-y-4">
        {secrets.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 bg-slate-900/40 px-4 py-5 text-sm text-slate-400">
            No secrets added yet.
          </div>
        ) : null}

        {secrets.map((secret, index) => (
          <div
            key={`${secret.key}-${index}`}
            className="grid gap-3 rounded-2xl border border-white/10 bg-slate-900/50 p-4 md:grid-cols-[1fr_1fr_auto]"
          >
            <input
              className="rounded-xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none ring-0 placeholder:text-slate-500 focus:border-cyan-400/60"
              onChange={(event) => updateSecret(index, "key", event.target.value.toUpperCase())}
              placeholder="OPENAI_API_KEY"
              value={secret.key}
            />
            <input
              className="rounded-xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none ring-0 placeholder:text-slate-500 focus:border-cyan-400/60"
              onChange={(event) => updateSecret(index, "value", event.target.value)}
              placeholder="Paste secret value"
              type="password"
              value={secret.value}
            />
            <button
              className="rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm font-medium text-rose-100 transition hover:bg-rose-400/20"
              onClick={() => removeSecret(index)}
              type="button"
            >
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
