"use strict";

const sessionToken = document.querySelector('meta[name="aiql-session"]').content;
const state = {
  overview: null,
  listening: false,
  voiceArmed: false,
  speaking: false,
  restartTimer: null,
  speechSequence: 0,
  selectedAgentKey: null,
};

const AGENT_VOICE_PROFILES = {
  atlas: { rate: 0.90, pitch: 0.82 },
  vega: { rate: 1.00, pitch: 1.08 },
  nova: { rate: 1.06, pitch: 1.20 },
  chronos: { rate: 0.86, pitch: 0.72 },
  iris: { rate: 0.96, pitch: 1.14 },
  sentinel: { rate: 0.90, pitch: 0.76 },
  aegis: { rate: 0.84, pitch: 0.65 },
  oracle: { rate: 0.82, pitch: 0.92 },
  echo: { rate: 1.08, pitch: 1.02 },
  forge: { rate: 0.98, pitch: 0.70 },
};

let speechVoices = [];

function refreshSpeechVoices() {
  if ("speechSynthesis" in window) speechVoices = window.speechSynthesis.getVoices();
}

refreshSpeechVoices();
if ("speechSynthesis" in window) window.speechSynthesis.addEventListener("voiceschanged", refreshSpeechVoices);

async function api(path, options = {}) {
  const config = {
    method: options.method || "GET",
    headers: { "X-AIQL-Session": sessionToken },
  };
  if (options.body !== undefined) {
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, config);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function renderOverview(overview) {
  state.overview = overview;
  renderAccount(overview.mt5);
  renderMarket(overview.scans || []);
  renderAgents(overview.agents || [], overview.team_progress || "");
  renderInstitutional(overview.institutional_research || null);
  renderStrategies(
    overview.strategies || [],
    overview.campaign,
    overview.strategy_blueprints || [],
  );
  document.getElementById("monitor-error").textContent = overview.last_monitor_error || "";
}

function renderAccount(mt5) {
  const badge = document.getElementById("mt5-badge");
  const details = document.getElementById("account-details");
  details.replaceChildren();
  if (!mt5.connected || !mt5.account) {
    badge.textContent = mt5.available ? "جاهز للاتصال" : "MT5 غير متاح";
    badge.className = "badge offline";
    details.className = "metrics-grid muted-box";
    details.textContent = mt5.message;
    return;
  }
  badge.textContent = "Demo موصول";
  badge.className = "badge online";
  details.className = "metrics-grid";
  const account = mt5.account;
  const metrics = [
    ["Balance", `${account.balance.toFixed(2)} ${account.currency}`],
    ["Equity", account.equity.toFixed(2)],
    ["Free margin", account.margin_free.toFixed(2)],
    ["Server", account.server],
    ["Login", `••••${account.login_last_four}`],
    ["Leverage", `1:${account.leverage}`],
  ];
  metrics.forEach(([label, value]) => {
    const card = textElement("div", "metric", "");
    card.append(textElement("span", "", label), textElement("strong", "", value));
    details.append(card);
  });
}

function renderMarket(scans) {
  const box = document.getElementById("market-snapshot");
  const time = document.getElementById("scan-time");
  box.replaceChildren();
  if (!scans.length) {
    box.className = "market-empty";
    box.textContent = "بعد ما في بيانات Live مسجّلة.";
    time.textContent = "لا يوجد فحص";
    return;
  }
  const scan = scans[0];
  const signal = Number(scan.consensus);
  const signalText = signal === 1 ? "شراء" : signal === -1 ? "بيع" : "حياد";
  box.className = "market-grid";
  const cards = [
    ["الإجماع", signalText, signal === 1 ? "signal-long" : signal === -1 ? "signal-short" : "signal-flat"],
    ["حالة السوق", scan.regime.replaceAll("_", " "), ""],
    ["Bid / Ask", `${scan.quote.bid.toFixed(5)} / ${scan.quote.ask.toFixed(5)}`, ""],
    ["أصوات شراء", String(scan.long_votes), "signal-long"],
    ["أصوات بيع", String(scan.short_votes), "signal-short"],
    ["Spread", `${scan.quote.spread_points.toFixed(1)} points`, ""],
  ];
  cards.forEach(([label, value, css]) => {
    const card = textElement("div", `signal-card ${css}`, "");
    card.append(textElement("span", "soft-label", label), textElement("strong", "", value));
    box.append(card);
  });
  time.textContent = new Date(scan.observed_at).toLocaleString("ar-LB");
}

function renderAgents(agents, progress) {
  document.getElementById("team-progress").textContent = progress;
  const grid = document.getElementById("agent-grid");
  grid.replaceChildren();
  agents.forEach((agent) => {
    const button = textElement("button", "agent-card", "");
    button.type = "button";
    const dot = textElement("span", `agent-state ${agent.state === "working" ? "working" : ""}`, "");
    button.append(dot, textElement("strong", "", `${agent.identity.name} · ${agent.state}`));
    button.append(textElement("p", "", agent.current_task || agent.identity.role));
    button.addEventListener("click", () => {
      showAgentDetail(agent, true);
      const input = document.getElementById("chat-input");
      input.value = `يا ${agent.identity.name} شو عم تعمل؟`;
    });
    grid.append(button);
  });
  if (state.selectedAgentKey) {
    const selected = agents.find((agent) => agent.identity.key === state.selectedAgentKey);
    if (selected) showAgentDetail(selected, false);
  }
}

function showAgentDetail(agent, shouldScroll) {
  state.selectedAgentKey = agent.identity.key;
  const detail = document.getElementById("agent-detail");
  const taskBox = document.getElementById("agent-detail-tasks");
  const messageBox = document.getElementById("agent-detail-messages");
  const metrics = document.getElementById("agent-detail-metrics");
  const overview = state.overview || {};
  const agentTasks = (overview.task_history || [])
    .filter((task) => task.assigned_agent_key === agent.identity.key || task.required_agent_key === agent.identity.key);
  const tasks = agentTasks
    .slice(-10)
    .reverse();
  const agentMessages = (overview.messages || [])
    .filter((message) => message.sender_key === agent.identity.key || message.recipient_key === agent.identity.key);
  const messages = agentMessages
    .slice(-10)
    .reverse();
  const research = overview.institutional_research || {};
  const campaigns = [research.active_campaign, ...(research.recent_campaigns || [])].filter(Boolean);
  const stages = campaigns
    .flatMap((campaign) => campaign.stages || [])
    .filter((stage) => stage.agent_key === agent.identity.key);

  document.getElementById("agent-detail-name").textContent = `${agent.identity.name} · ${agent.state}`;
  document.getElementById("agent-detail-role").textContent = agent.identity.role;
  metrics.replaceChildren();
  [
    ["المهمة الحالية", agent.current_task || "لا توجد مهمة ناشطة"],
    ["التقدّم", `${Math.round(agent.progress_percent || 0)}%`],
    ["مهام مسجّلة", String(agentTasks.length)],
    ["رسائل وتسليمات", String(agentMessages.length)],
    ["الحالة", agent.message],
    ["آخر تحديث", new Date(agent.updated_at).toLocaleString("ar-LB")],
  ].forEach(([label, value]) => {
    const card = textElement("div", "metric", "");
    card.append(textElement("span", "", label), textElement("strong", "", value));
    metrics.append(card);
  });

  taskBox.replaceChildren();
  if (!tasks.length && !stages.length) {
    taskBox.append(textElement("div", "muted-box", "ما في مهام مسجّلة لهيدا الـAgent بعد."));
  }
  tasks.forEach((task) => {
    const item = textElement("div", `agent-history-item task-${task.status}`, "");
    item.append(
      textElement("strong", "", `${task.title} · ${task.status} · ${Math.round(task.progress_percent)}%`),
      textElement("span", "", task.result_summary || task.error_message || task.status_note || task.description),
      textElement("small", "", `Task ${task.task_id} · ${(task.tags || []).join(" · ")}`),
    );
    taskBox.append(item);
  });
  stages.slice(-4).reverse().forEach((stage) => {
    const item = textElement("div", `agent-history-item task-${stage.status}`, "");
    item.append(
      textElement("strong", "", `أدوات: ${(stage.tools_used || []).join("، ") || "—"}`),
      textElement("span", "", `Inputs: ${(stage.input_contract || []).join("، ") || "—"}`),
      textElement("span", "", `Outputs: ${(stage.produced_outputs || stage.output_contract || []).join("، ") || "—"}`),
    );
    taskBox.append(item);
  });

  messageBox.replaceChildren();
  if (!messages.length) {
    messageBox.append(textElement("div", "muted-box", "ما في رسائل أو hand-offs مسجّلة بعد."));
  }
  messages.forEach((message) => {
    const direction = message.sender_key === agent.identity.key
      ? `إلى ${message.recipient_key}`
      : `من ${message.sender_key}`;
    const item = textElement("div", "agent-history-item", "");
    item.append(
      textElement("strong", "", `${direction} · ${message.subject}`),
      textElement("span", "", message.body),
      textElement("small", "", new Date(message.created_at).toLocaleString("ar-LB")),
    );
    messageBox.append(item);
  });
  detail.hidden = false;
  if (shouldScroll) detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

const STAGE_LABELS = {
  data_intelligence: "Vega · البيانات والجودة",
  regime_analysis: "Iris · حالة السوق",
  macro_capability_audit: "Oracle · الأدلة الاقتصادية",
  hypothesis_design: "Nova · الفرضية",
  backtest_validation: "Chronos · الاختبارات",
  quant_audit: "Sentinel · التدقيق الكمي",
  risk_review: "Aegis · قرار المخاطر",
  challenger_evolution: "Forge · Champion–Challenger",
  reporting: "Echo · التقرير",
};

function renderInstitutional(research) {
  const badge = document.getElementById("research-state");
  const reason = document.getElementById("research-control-reason");
  const headline = document.getElementById("research-headline");
  const stages = document.getElementById("research-stages");
  const registry = document.getElementById("registry-counts");
  const recent = document.getElementById("recent-campaigns");
  headline.replaceChildren();
  stages.replaceChildren();
  registry.replaceChildren();
  recent.replaceChildren();
  if (!research) {
    badge.textContent = "غير متاح";
    reason.textContent = "محرك البحث المؤسساتي غير محمّل.";
    return;
  }
  const control = research.control || {};
  const active = research.active_campaign;
  if (control.emergency_stop) {
    badge.textContent = "إيقاف طارئ";
    badge.className = "badge danger-badge";
  } else if (!control.loop_enabled) {
    badge.textContent = "متوقف مؤقتاً";
    badge.className = "badge offline";
  } else if (active) {
    badge.textContent = "يعمل الآن";
    badge.className = "badge online";
  } else {
    badge.textContent = "يراقب الشموع";
    badge.className = "badge online";
  }
  reason.textContent = `${control.reason || ""} · ${research.cadence || ""}`;
  let portfolioRisk = null;
  if (active && active.artifacts && active.artifacts.portfolio_risk) {
    try { portfolioRisk = JSON.parse(active.artifacts.portfolio_risk); }
    catch (_error) { portfolioRisk = null; }
  }
  const headlineMetrics = active
    ? [
        ["الحملة", active.campaign_id],
        ["الأصل / الإطار", `${active.pair} ${active.timeframe}`],
        ["الاستراتيجية", active.strategy_name || "بانتظار Nova"],
        ["Quant Score", active.quant_score == null ? "—" : `${Number(active.quant_score).toFixed(1)}/100`],
        ["قرار Aegis", active.risk_decision || "بانتظار التدقيق"],
        ["الحالة", active.status],
        ...(portfolioRisk ? [
          ["Gross leverage", Number(portfolioRisk.gross_leverage).toFixed(2)],
          ["Currency exposure", `${(Number(portfolioRisk.maximum_currency_exposure_fraction) * 100).toFixed(1)}%`],
          ["Portfolio CVaR 95%", `${(Number(portfolioRisk.portfolio_cvar_95_fraction) * 100).toFixed(2)}%`],
        ] : []),
      ]
    : [["الحالة", "ما في حملة ناشطة — أول شمعة جديدة بتنشئ حملة تلقائياً"]];
  headlineMetrics.forEach(([label, value]) => {
    const card = textElement("div", "metric", "");
    card.append(textElement("span", "", label), textElement("strong", "", String(value)));
    headline.append(card);
  });
  if (active) {
    (active.stages || []).forEach((stage) => {
      const row = textElement("div", `stage-row stage-${stage.status}`, "");
      const copy = textElement("div", "", "");
      copy.append(
        textElement("strong", "", STAGE_LABELS[stage.name] || stage.name),
        textElement("span", "", stage.summary || stage.error || "بانتظار دوره"),
      );
      row.append(copy, textElement("b", "", `${Math.round(stage.progress_percent || 0)}%`));
      stages.append(row);
    });
  } else {
    stages.append(textElement("div", "muted-box", "ما في سلسلة ناشطة هلق."));
  }
  const countLabels = {
    research_campaigns: "حملات",
    datasets: "نسخ بيانات",
    regime_assessments: "Regimes",
    hypotheses: "فرضيات",
    institutional_experiments: "تجارب",
    risk_decisions: "قرارات مخاطر",
    strategy_candidates: "Candidates",
  };
  Object.entries(research.registry_counts || {}).forEach(([key, value]) => {
    const item = textElement("div", "registry-item", "");
    item.append(textElement("span", "", countLabels[key] || key), textElement("strong", "", String(value)));
    registry.append(item);
  });
  (research.recent_campaigns || []).slice(0, 5).forEach((campaign) => {
    const item = textElement("div", "recent-campaign", "");
    item.append(
      textElement("strong", "", `${campaign.pair} ${campaign.timeframe} · ${campaign.status}`),
      textElement(
        "span",
        "",
        `${campaign.strategy_name || "—"} · Score ${campaign.quant_score == null ? "—" : Number(campaign.quant_score).toFixed(1)}`,
      ),
    );
    recent.append(item);
  });
}

function renderStrategies(strategies, campaign, blueprints) {
  document.getElementById("strategy-count").textContent = `${strategies.length} استراتيجيات`;
  const list = document.getElementById("strategy-list");
  list.replaceChildren();
  strategies.forEach((strategy) => {
    const advanced = strategy.research_tier === "advanced";
    const chip = textElement(
      "span",
      `strategy-chip${advanced ? " advanced" : ""}`,
      `${strategy.name}${advanced ? " · متقدمة" : ""}`,
    );
    chip.title = `${strategy.description} — ${strategy.family}`;
    list.append(chip);
  });
  document.getElementById("blueprint-count").textContent =
    `${blueprints.length} Blueprint مؤسساتي — الحالة واضحة لكل واحد`;
  const blueprintList = document.getElementById("blueprint-list");
  blueprintList.replaceChildren();
  blueprints.forEach((blueprint) => {
    const card = textElement("div", `blueprint blueprint-${blueprint.availability}`, "");
    card.append(
      textElement("strong", "", blueprint.title),
      textElement("span", "", `${blueprint.family} · ${blueprint.availability}`),
      textElement("small", "", `البيانات: ${(blueprint.required_inputs || []).join(", ")}`),
    );
    blueprintList.append(card);
  });
  const summary = document.getElementById("campaign-summary");
  summary.replaceChildren();
  if (!campaign) {
    summary.textContent = "ما في Research Campaign مسجّلة بعد.";
    return;
  }
  const leader = campaign.entries[0];
  summary.append(
    textElement("span", "", `آخر مقارنة: ${campaign.pair} ${campaign.timeframe} — المتصدر البحثي `),
    textElement("strong", "", campaign.research_leader || "لا يوجد"),
    textElement(
      "span",
      "",
      ` من أصل ${campaign.entries.length}. ثبات الاختبارات: ${leader ? `${leader.robustness_checks_passed}/3` : "—"}.`,
    ),
  );
}

function addMessage(kind, speaker, body) {
  const conversation = document.getElementById("conversation");
  const message = textElement("div", `message ${kind === "user" ? "user-message" : "agent-message"}`, "");
  message.append(textElement("span", "", speaker), document.createTextNode(body));
  conversation.append(message);
  conversation.scrollTop = conversation.scrollHeight;
}

function agentVoice(agentKey) {
  const arabic = speechVoices.filter((voice) => voice.lang.toLowerCase().startsWith("ar"));
  if (!arabic.length) return null;
  const keys = Object.keys(AGENT_VOICE_PROFILES);
  const index = Math.max(0, keys.indexOf(agentKey));
  return arabic[index % arabic.length];
}

function speak(text, agentKey) {
  if (!document.getElementById("speak-replies").checked || !("speechSynthesis" in window)) return;
  const sequence = ++state.speechSequence;
  state.speaking = true;
  if (recognition && state.listening) recognition.abort();
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "ar-LB";
  const profile = AGENT_VOICE_PROFILES[agentKey] || AGENT_VOICE_PROFILES.atlas;
  utterance.rate = profile.rate;
  utterance.pitch = profile.pitch;
  utterance.voice = agentVoice(agentKey);
  const resumeListening = () => {
    if (sequence !== state.speechSequence) return;
    state.speaking = false;
    if (state.voiceArmed && document.getElementById("always-listen").checked) startRecognition();
  };
  utterance.onend = resumeListening;
  utterance.onerror = resumeListening;
  window.speechSynthesis.speak(utterance);
}

async function sendChat(text) {
  const normalized = text.trim();
  if (!normalized) return;
  addMessage("user", "أنت", normalized);
  const input = document.getElementById("chat-input");
  input.value = "";
  try {
    const result = await api("/api/chat", { method: "POST", body: { text: normalized } });
    const speaker = result.matched_agent_key || "الفريق";
    addMessage("agent", speaker, result.reply);
    speak(result.reply, result.matched_agent_key || "atlas");
  } catch (error) {
    addMessage("agent", "النظام", error.message);
  }
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = "ar-LB";
  recognition.interimResults = true;
  recognition.continuous = true;
  document.getElementById("voice-support").textContent = "اضغط 🎙 لتفعيل الاستماع الدائم";
  recognition.onstart = () => {
    state.listening = true;
    document.getElementById("microphone").classList.add("listening");
    document.getElementById("voice-support").textContent = "عم بسمعك — نادِ اسم الـAgent";
  };
  recognition.onresult = (event) => {
    let finalTranscript = "";
    let interimTranscript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0].transcript;
      if (event.results[index].isFinal) finalTranscript += transcript;
      else interimTranscript += transcript;
    }
    const input = document.getElementById("chat-input");
    if (interimTranscript) input.value = interimTranscript;
    if (finalTranscript.trim()) {
      input.value = finalTranscript.trim();
      sendChat(finalTranscript);
      if (!document.getElementById("always-listen").checked) {
        state.voiceArmed = false;
        recognition.stop();
      }
    }
  };
  recognition.onerror = (event) => {
    if (["not-allowed", "service-not-allowed"].includes(event.error)) {
      state.voiceArmed = false;
      document.getElementById("voice-support").textContent = "اسمح للميكروفون من رمز القفل قرب العنوان";
      addMessage("agent", "الصوت", "إذن الميكروفون مرفوض. اسمح به للموقع المحلي ثم اضغط 🎙.");
      return;
    }
    if (event.error === "audio-capture") {
      state.voiceArmed = false;
      document.getElementById("voice-support").textContent = "ما لقيت ميكروفون متاح";
      return;
    }
    if (!["no-speech", "aborted"].includes(event.error)) {
      addMessage("agent", "الصوت", `تعذر التعرّف على الصوت: ${event.error}`);
    }
  };
  recognition.onend = () => {
    state.listening = false;
    document.getElementById("microphone").classList.remove("listening");
    if (state.voiceArmed && !state.speaking && document.getElementById("always-listen").checked) {
      state.restartTimer = window.setTimeout(startRecognition, 350);
    } else if (!state.voiceArmed) {
      document.getElementById("voice-support").textContent = "الاستماع متوقف — اضغط 🎙";
    }
  };
} else {
  document.getElementById("voice-support").textContent = "استخدم Chrome أو Edge للصوت";
}

function startRecognition() {
  if (!recognition || !state.voiceArmed || state.listening || state.speaking) return;
  if (state.restartTimer) window.clearTimeout(state.restartTimer);
  try {
    recognition.start();
  } catch (error) {
    if (error.name !== "InvalidStateError") {
      state.voiceArmed = false;
      addMessage("agent", "الصوت", `تعذر تشغيل الميكروفون: ${error.message}`);
    }
  }
}

document.getElementById("microphone").addEventListener("click", () => {
  if (!recognition) return;
  if (state.voiceArmed) {
    state.voiceArmed = false;
    if (state.restartTimer) window.clearTimeout(state.restartTimer);
    if (state.listening) recognition.stop();
    document.getElementById("voice-support").textContent = "الاستماع متوقف — اضغط 🎙";
  } else {
    state.voiceArmed = true;
    startRecognition();
  }
});

document.getElementById("always-listen").addEventListener("change", (event) => {
  if (!event.currentTarget.checked && state.voiceArmed && !state.listening) {
    state.voiceArmed = false;
    document.getElementById("voice-support").textContent = "وضع ضغطة واحدة جاهز";
  }
});

document.getElementById("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  sendChat(document.getElementById("chat-input").value);
});

async function action(path, button) {
  button.disabled = true;
  try {
    await api(path, { method: "POST", body: {} });
    await refresh();
  } catch (error) {
    document.getElementById("monitor-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

document.getElementById("connect-mt5").addEventListener("click", (event) => action("/api/mt5/connect", event.currentTarget));
document.getElementById("disconnect-mt5").addEventListener("click", (event) => action("/api/mt5/disconnect", event.currentTarget));
document.getElementById("scan-market").addEventListener("click", (event) => action("/api/monitor/scan", event.currentTarget));
document.getElementById("runtime-tick").addEventListener("click", (event) => action("/api/runtime/tick", event.currentTarget));
document.getElementById("research-start").addEventListener("click", (event) => action("/api/research/start", event.currentTarget));
document.getElementById("research-pause").addEventListener("click", (event) => action("/api/research/pause", event.currentTarget));
document.getElementById("research-reset").addEventListener("click", (event) => action("/api/research/reset-emergency", event.currentTarget));
document.getElementById("agent-detail-close").addEventListener("click", () => {
  state.selectedAgentKey = null;
  document.getElementById("agent-detail").hidden = true;
});
document.getElementById("research-emergency").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await api("/api/research/emergency-stop", {
      method: "POST",
      body: { reason: "Emergency stop requested from the local dashboard." },
    });
    await refresh();
  } catch (error) {
    document.getElementById("monitor-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.getElementById("order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    pair: form.get("pair"), side: form.get("side"),
    volume_lots: Number(form.get("volume_lots")),
    stop_loss_points: Number(form.get("stop_loss_points")),
    take_profit_points: Number(form.get("take_profit_points")),
    confirmation: form.get("confirmation"),
  };
  const resultBox = document.getElementById("order-result");
  try {
    const receipt = await api("/api/mt5/order", { method: "POST", body: payload });
    resultBox.textContent = `تم قبول أمر الـDemo رقم ${receipt.order_id}.`;
    await refresh();
  } catch (error) {
    resultBox.textContent = error.message;
  }
});

async function refresh() {
  try { renderOverview(await api("/api/overview")); }
  catch (error) { document.getElementById("monitor-error").textContent = error.message; }
}

refresh();
window.setInterval(refresh, 4000);
