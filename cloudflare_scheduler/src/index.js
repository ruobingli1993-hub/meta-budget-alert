const GITHUB_API = "https://api.github.com";

export default {
  async scheduled(controller, env) {
    await dispatchDueWorkflows(new Date(controller.scheduledTime), env);
  },
};

export async function dispatchDueWorkflows(now, env) {
  const beijing = beijingParts(now);
  const jobs = dueJobs(beijing, env.MANUAL_TEST_JOB);
  await env.SCHEDULER_STATE.put("cron:last_event", JSON.stringify({
    scheduled_at: now.toISOString(),
    beijing,
    due_jobs: jobs.map((job) => job.key),
  }), { expirationTtl: 172800 });
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
      const authProbe = await fetch(`${GITHUB_API}/user`, {
        headers: {
          Authorization: `token ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "meta-budget-alert-cloudflare-scheduler-v1",
        },
      });
      await env.SCHEDULER_STATE.put(`${runKey}:error`, JSON.stringify({
        status: "GITHUB_DISPATCH_FAILED",
        http_status: response.status,
        auth_probe_http_status: authProbe.status,
        token_format: {
          length: String(env.GITHUB_TOKEN || "").length,
          expected_prefix: String(env.GITHUB_TOKEN || "").startsWith("github_pat_"),
          contains_whitespace: /\s/.test(String(env.GITHUB_TOKEN || "")),
        },
        error: body,
        triggered_at: now.toISOString(),
      }), { expirationTtl: 172800 });
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

function dueJobs(beijing, manualTestJob = "") {
  const jobs = [];
  if (manualTestJob === "budget-alert") {
    return [{ key: "manual-budget-alert", workflow: "check_budget.yml", inputs: {} }];
  }
  if (["morning", "daily-close", "early-pulse"].includes(manualTestJob)) {
    return [reportJob(manualTestJob)];
  }
  if (beijing.minute === 15) {
    jobs.push({ key: `${String(beijing.hour).padStart(2, "0")}:budget-alert`, workflow: "check_budget.yml", inputs: {} });
  }
  // A Cron event can be delayed or briefly unavailable. Keep each report slot
  // eligible for a bounded recovery window; the existing KV run key means a
  // successful on-time dispatch is never dispatched again.
  for (const window of reportRecoveryWindows()) {
    const nowMinutes = beijing.hour * 60 + beijing.minute;
    if (nowMinutes >= window.startMinutes && nowMinutes < window.endMinutes) {
      jobs.push(reportJob(window.mode));
    }
  }
  return jobs;
}

function reportRecoveryWindows() {
  return [
    { mode: "morning", startMinutes: 9 * 60, endMinutes: 12 * 60 },
    { mode: "daily-close", startMinutes: 15 * 60 + 30, endMinutes: 18 * 60 },
    { mode: "early-pulse", startMinutes: 18 * 60, endMinutes: 21 * 60 },
  ];
}

function reportJob(mode) {
  return { key: mode, workflow: "scheduled_reports.yml", inputs: { report_mode: mode } };
}

async function dispatchWorkflow(env, job, triggeredAt, runKey) {
  const inputs = { ...job.inputs, triggered_at: triggeredAt };
  if (job.workflow === "check_budget.yml") inputs.run_key = runKey;
  const url = `${GITHUB_API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${job.workflow}/dispatches`;
  const request = (requestInputs) => {
    const payload = { ref: env.GITHUB_REF || "main" };
    if (Object.keys(requestInputs).length > 0) payload.inputs = requestInputs;
    return fetch(url, {
    method: "POST",
    headers: {
      Authorization: `token ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "meta-budget-alert-cloudflare-scheduler-v1",
    },
      body: JSON.stringify(payload),
    });
  };
  const response = await request(inputs);
  if (response.status === 400) {
    return request(job.inputs);
  }
  return response;
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

export const __test = { beijingParts, dueJobs, reportRecoveryWindows };
