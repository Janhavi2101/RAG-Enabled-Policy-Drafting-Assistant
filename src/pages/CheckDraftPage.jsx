import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowLeft, FileCheck2, FileText, RotateCcw, ShieldAlert, UploadCloud } from "lucide-react";
import { cn } from "@/lib/utils";

const riskStyles = {
  Low: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  Moderate: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
  High: "bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-300",
};

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

const severityStyles = {
  high: "bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-300",
  medium: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
  low: "bg-sky-500/10 text-sky-700 border-sky-500/30 dark:text-sky-300",
};

export default function CheckDraftPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const fileMeta = useMemo(() => {
    if (!selectedFile) return null;
    return `${selectedFile.name} • ${formatBytes(selectedFile.size)}`;
  }, [selectedFile]);

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setResult(null);
    setError("");
  };

  const handleReset = () => {
    setSelectedFile(null);
    setResult(null);
    setError("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!selectedFile) {
      setError("Please select a PDF draft before running validation.");
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".pdf") || selectedFile.type && selectedFile.type !== "application/pdf") {
      setError("Only PDF files are supported for draft validation.");
      return;
    }

    setLoading(true);
    setResult(null);
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch("/api/validate-policy-pdf", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Draft validation failed.");
      }

      setResult(data);
    } catch (requestError) {
      setError(requestError.message || "Could not validate the uploaded draft.");
    } finally {
      setLoading(false);
    }
  };

  const riskClassName = riskStyles[result?.risk_level] || "bg-muted text-muted-foreground border-border";

  return (
    <div className="h-full overflow-y-auto bg-background">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-primary">Draft Validation</p>
            <h1 className="mt-2 text-3xl font-semibold text-foreground">Check Draft Policy</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Upload a drafted policy PDF to run a structural anomaly check. This validation layer compares the draft
              against learned policy patterns and flags unusual structure before manual review.
            </p>
          </div>

          <Link
            to="/draft"
            className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ArrowLeft size={16} />
            Back to Draft
          </Link>
        </div>

        <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-primary/10 p-3 text-primary shrink-0">
                <UploadCloud size={24} />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-card-foreground">Upload Draft PDF</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Only text-based PDF policies are supported. OCR is not used in this flow.
                </p>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="w-full max-w-3xl space-y-4">
              <label
                htmlFor="check-draft-file"
                className="flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border bg-background/60 px-6 text-center transition-colors hover:border-primary/40 hover:bg-muted/40"
              >
                <UploadCloud className="mb-4 text-muted-foreground" size={34} />
                <span className="text-sm font-medium text-foreground">Click to choose a drafted policy PDF</span>
                <span className="mt-1 text-xs text-muted-foreground">PDF only • validation-ready upload</span>
                <input
                  id="check-draft-file"
                  type="file"
                  accept=".pdf,application/pdf"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </label>

              {fileMeta && (
                <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
                  <FileText size={16} className="text-primary" />
                  <span className="font-medium text-foreground">{fileMeta}</span>
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  <AlertCircle size={16} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="flex flex-wrap gap-3">
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <FileCheck2 size={16} />
                  {loading ? "Checking..." : "Upload and Check"}
                </button>

                <button
                  type="button"
                  onClick={handleReset}
                  className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <RotateCcw size={16} />
                  Check Another File
                </button>
              </div>
            </form>
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-amber-500/10 p-3 text-amber-600 dark:text-amber-300 shrink-0">
              <ShieldAlert size={22} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-card-foreground">Policy Validation Results</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Review based on anomaly scoring, reference-policy comparison, and legal/policy conflict checks.
              </p>
            </div>
          </div>

          {!result ? (
            <div className="mt-6 rounded-2xl border border-dashed border-border bg-background/50 px-5 py-12 text-center">
              <p className="text-sm font-medium text-foreground">No validation result yet</p>
              <p className="mt-2 text-sm text-muted-foreground">
                Upload a PDF draft to view anomaly score, risk level, validation findings, and recommended actions here.
              </p>
            </div>
          ) : (
            <div className="mt-6 space-y-5">
              <div className="rounded-2xl border border-border bg-background/50 p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Validation Status</p>
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <span className={cn("rounded-full border px-3 py-1 text-xs font-semibold", riskClassName)}>
                        {result.risk_level} Risk
                      </span>
                      <span className="text-sm text-muted-foreground">{result.message}</span>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <MetricPill label="Anomaly Score" value={typeof result.anomaly_score === "number" ? result.anomaly_score.toFixed(6) : "N/A"} />
                    <MetricPill label="Policy Similarity" value={typeof result.reference_similarity === "number" ? result.reference_similarity.toFixed(6) : "N/A"} />
                    <MetricPill label="Compliance Status" value={result.compliance_status || "N/A"} />
                  </div>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <ResultItem label="File Name" value={result.filename || "Unknown"} />
                <ResultItem label="Risk Level" value={result.risk_level || "N/A"} />
                <ResultItem
                  label="Extracted Text Length"
                  value={Number.isFinite(result.text_length) ? `${result.text_length} characters` : "N/A"}
                />
                <ResultItem
                  label="Conflict Count"
                  value={Number.isFinite(result.conflict_count) ? String(result.conflict_count) : "0"}
                />
                <ResultItem
                  label="Embedding Model"
                  value={result.embedding_model || "N/A"}
                />
              </div>

              {result.recommendation && (
                <div className="rounded-2xl border border-border bg-muted/30 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Recommendation</p>
                  <p className="mt-2 text-sm text-foreground">{result.recommendation}</p>
                </div>
              )}

              {Array.isArray(result.recommendations) && result.recommendations.length > 1 && (
                <div className="rounded-2xl border border-border bg-background/50 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Recommended Actions</p>
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    {result.recommendations.slice(1).map((item, index) => (
                      <div key={`${item}-${index}`} className="rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground">
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {Array.isArray(result.reference_policy_matches) && result.reference_policy_matches.length > 0 && (
                <div className="rounded-2xl border border-border bg-background/50 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Reference PDFs Used For Comparison</p>
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {result.reference_policy_matches.map((match, index) => (
                      <div key={`${match.name}-${index}`} className="rounded-xl border border-border bg-card p-4">
                        <p className="text-sm font-medium text-foreground">{match.name}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Similarity: {typeof match.similarity === "number" ? match.similarity.toFixed(6) : "N/A"}
                        </p>
                        {Array.isArray(match.section_groups) && match.section_groups.length > 0 && (
                          <p className="mt-2 text-sm text-muted-foreground">
                            Structure cues: {match.section_groups.join(", ").replaceAll("_", " ")}
                          </p>
                        )}
                        {Array.isArray(match.headings) && match.headings.length > 0 && (
                          <p className="mt-2 text-sm text-muted-foreground">
                            Sample headings: {match.headings.slice(0, 4).join(" • ")}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {Array.isArray(result.section_reviews) && result.section_reviews.length > 0 && (
                <div className="rounded-2xl border border-border bg-background/50 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Section-Wise Review</p>
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {result.section_reviews.map((section, index) => {
                      const status = section.status === "needs_attention" ? "medium" : "low";
                      const statusClassName = severityStyles[status] || "bg-muted text-muted-foreground border-border";
                      return (
                        <div key={`${section.title}-${index}`} className="rounded-xl border border-border bg-card p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={cn("rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase", statusClassName)}>
                              {section.status === "needs_attention" ? "needs attention" : "aligned"}
                            </span>
                            {section.group && (
                              <span className="text-xs text-muted-foreground">{String(section.group).replaceAll("_", " ")}</span>
                            )}
                          </div>
                          <p className="mt-3 text-sm font-medium text-foreground">{section.title}</p>
                          {section.summary && <p className="mt-2 text-sm text-muted-foreground">{section.summary}</p>}
                          {section.reference_policy && (
                            <p className="mt-2 text-xs text-muted-foreground">
                              Closest reference: {section.reference_policy}
                              {section.reference_section ? ` • ${section.reference_section}` : ""}
                            </p>
                          )}
                          {typeof section.similarity === "number" && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              Section similarity: {section.similarity.toFixed(6)}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="rounded-2xl border border-border bg-background/50 p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Potential Policy Conflicts with Existing Documents</p>
                {Array.isArray(result.existing_policy_conflicts) && result.existing_policy_conflicts.length > 0 ? (
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {result.existing_policy_conflicts.map((conflict, index) => {
                      const severity = String(conflict.severity || "medium").toLowerCase();
                      const severityClassName = severityStyles[severity] || "bg-muted text-muted-foreground border-border";
                      return (
                        <div key={`${conflict.policy_title}-${index}`} className="rounded-xl border border-border bg-card p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={cn("rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase", severityClassName)}>
                              {severity}
                            </span>
                            <span className="text-xs text-muted-foreground">Policy inconsistency</span>
                          </div>
                          <p className="mt-3 text-sm font-medium text-foreground">{conflict.policy_title || "Existing policy"}</p>
                          {conflict.issue && <p className="mt-2 text-sm text-foreground">{conflict.issue}</p>}
                          {conflict.why_it_matters && <p className="mt-2 text-sm text-muted-foreground">{conflict.why_it_matters}</p>}
                          {conflict.recommendation && <p className="mt-2 text-sm text-muted-foreground">Recommendation: {conflict.recommendation}</p>}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
                    {result.existing_policy_status === "no_precedents"
                      ? "No existing policy excerpts were available in the current document memory, so policy-level comparison could not be completed."
                      : result.existing_policy_status === "analysis_unavailable"
                        ? "Existing policy comparison is currently unavailable."
                        : Number.isFinite(result.existing_policy_precedent_count) && result.existing_policy_precedent_count > 0
                          ? `Retrieved ${result.existing_policy_precedent_count} existing policy excerpt(s), but no implementation-level inconsistency was detected against them. This does not guarantee the draft is fully policy-aligned.`
                          : "No existing policy excerpts were retrieved for comparison, so no policy-level conflict result could be produced."}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-border bg-background/50 p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Potential Legal Conflicts if Implemented</p>
                {Array.isArray(result.legal_conflicts) && result.legal_conflicts.length > 0 ? (
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {result.legal_conflicts.map((conflict, index) => {
                      const severity = String(conflict.severity || "medium").toLowerCase();
                      const severityClassName = severityStyles[severity] || "bg-muted text-muted-foreground border-border";
                      return (
                        <div key={`${conflict.citation || conflict.law}-${index}`} className="rounded-xl border border-border bg-card p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={cn("rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase", severityClassName)}>
                              {severity}
                            </span>
                            <span className="text-xs text-muted-foreground">Legal contradiction risk</span>
                          </div>
                          <p className="mt-3 text-sm font-medium text-foreground">{conflict.law || "Applicable law/guideline"}</p>
                          {conflict.citation && <p className="mt-1 text-xs text-muted-foreground">{conflict.citation}</p>}
                          {conflict.issue && <p className="mt-2 text-sm text-foreground">{conflict.issue}</p>}
                          {conflict.why_it_matters && <p className="mt-2 text-sm text-muted-foreground">{conflict.why_it_matters}</p>}
                          {conflict.requirement && <p className="mt-2 text-sm text-muted-foreground">Required: {conflict.requirement}</p>}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
                    {Number.isFinite(result.matched_rule_count) && result.matched_rule_count > 0
                      ? `Matched ${result.matched_rule_count} law/guideline excerpt(s), but no high-confidence implementation-level legal contradiction was detected. This does not guarantee the draft is fully compliant.`
                      : "No sufficiently matched laws or guideline excerpts were available for legal contradiction checking on this draft."}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-border bg-background/50 p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Compliance Gaps</p>
                {Array.isArray(result.compliance_gaps) && result.compliance_gaps.length > 0 ? (
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {result.compliance_gaps.map((gap, index) => {
                      const severity = String(gap.severity || "medium").toLowerCase();
                      const severityClassName = severityStyles[severity] || "bg-muted text-muted-foreground border-border";
                      return (
                        <div key={`${gap.citation || gap.issue}-${index}`} className="rounded-xl border border-border bg-card p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={cn("rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase", severityClassName)}>
                              {severity}
                            </span>
                            <span className="text-xs text-muted-foreground">Compliance gap</span>
                          </div>
                          <p className="mt-3 text-sm font-medium text-foreground">{gap.issue}</p>
                          {gap.law && <p className="mt-2 text-xs text-muted-foreground">{gap.law}</p>}
                          {gap.citation && <p className="mt-1 text-xs text-muted-foreground">{gap.citation}</p>}
                          {gap.requirement && <p className="mt-2 text-sm text-muted-foreground">Required: {gap.requirement}</p>}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
                    {Number.isFinite(result.matched_rule_count) && result.matched_rule_count > 0
                      ? "No major compliance gaps were identified against the matched legal and policy materials."
                      : "No sufficiently matched legal or policy materials were available to assess compliance gaps for this draft."}
                  </div>
                )}
              </div>

              {Array.isArray(result.matched_rules) && result.matched_rules.length > 0 && (
                <div className="rounded-2xl border border-border bg-background/50 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Relevant Laws and Guidelines</p>
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {result.matched_rules.map((rule, index) => (
                      <div key={`${rule.citation}-${index}`} className="rounded-xl border border-border bg-card p-4">
                        <p className="text-sm font-medium text-foreground">{rule.law || "Matched rule"}</p>
                        {rule.citation && <p className="mt-1 text-xs text-muted-foreground">{rule.citation}</p>}
                        {rule.summary && <p className="mt-2 text-sm text-muted-foreground">{rule.summary}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ResultItem({ label, value }) {
  return (
    <div className="rounded-2xl border border-border bg-background/50 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium text-foreground break-words">{value}</p>
    </div>
  );
}

function MetricPill({ label, value }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}
