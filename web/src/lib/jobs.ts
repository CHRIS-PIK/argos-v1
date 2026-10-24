// Exportações criadas por esta sessão do navegador (a API não lista jobs; guardamos os ids).
const STORE = "argos.exports";
const MAX_JOBS = 30;

export interface TrackedJob {
  id: string;
  label: string;
  createdAt: string;
}

export function trackedJobs(): TrackedJob[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORE) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function trackJob(job: TrackedJob) {
  try {
    const next = [job, ...trackedJobs().filter((j) => j.id !== job.id)].slice(0, MAX_JOBS);
    localStorage.setItem(STORE, JSON.stringify(next));
  } catch {
    // armazenamento indisponível: a exportação continua válida, só não aparece na lista
  }
}

export function forgetJob(id: string) {
  try {
    localStorage.setItem(STORE, JSON.stringify(trackedJobs().filter((j) => j.id !== id)));
  } catch {
    // ignorado
  }
}
