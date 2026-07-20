const GITHUB_API = "https://api.github.com";

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(dispatchDueWorkflows(new Date(), env));
  },
};

export async function dispatchDueWorkflows(now, env) {
  const beijing = beijingParts(now);
  const jobs = dueJobs(beijing);
  const results = [];
  for (const job of jobs) {
    const runKey = `${beijing.date}:${job.key}`;
    if (await env.SCHEDULER_STATE.get(runKey)) {
      results.push({ run_key: runKey, status: "SKIPPED_ALREADY_DISPATCHED" });
      continue;
    }
    const response = await dispatchWorkflow(env, job, now.toISOString(), runKey);
    if (!response.ok) {
      const body = (await response.text()).slice(0, 500);
      console.error(JSON.stringify({ run_key: runKey, status: "GITHUB_DISPATCH_FAILED", http_status: response.status, error: body }));
      results.push({ run_key: runKey, status: "FAILED", http_status: response.status });
      continue;
    }
    await env.SCHEDULER_STATE.put(runKey, now.toISOString(), { expirationTtl: 172800 });
    console.log(JSON.stringify({ run_key: runKey, status: "DISPATCHED", triggered_at: now.toISOString(), workflow: job.workflow }));
    results.push({ run_key: runKey, status: "DISPATCHED" });
  }
  return results;
}

function dueJobs(beijing) {
  const jobs = [];
  if (beijing.minute === 15) {
    jobs.push({ key: `${String(beijing.hour).padStart(2, "0")}:budget-alert`, workflow: "check_budget.yml", inputs: {} });
  }
  if (beijing.hour === 9 && beijing.minute === 0) {
    jobs.push(reportJob("morning"));
  }
  if (beijing.hour === 15 && beijing.minute === 30) {
    jobs.push(reportJob("daily-close"));
  }
  if (beijing.hour === 18 && beijing.minute === 0) {
    jobs.push(reportJob("early-pulse"));
  }
  return jobs;
}

function reportJob(mode) {
  return { key: mode, workflow: "scheduled_reports.yml", inputs: { report_mode: mode } };
}

async function dispatchWorkflow(env, job, triggeredAt, runKey) {
  const inputs = { ...job.inputs, triggered_at: triggeredAt };
  if (job.workflow === "check_budget.yml") inputs.run_key = runKey;
  return fetch(`${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${job.workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "meta-budget-alert-cloudflare-scheduler-v1",
    },
    body: JSON.stringify({ ref: env.GITHUB_REF || "main", inputs }),
  });
}

function beijingParts(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return { date: `${value.year}-${value.month}-${value.day}`, hour: Number(value.hour), minute: Number(value.minute) };
}

export const __test = { beijingParts, dueJobs };
