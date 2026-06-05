/* Jarvis web UI — voice in the browser (Chrome Web Speech API), brain over /api/ask. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const elHint = $("hint"), elStatus = $("statusText"), elText = $("text");
  const elMic = $("mic"), elOrb = $("orb"), elTranscript = $("transcript");
  const elLang = $("langToggle"), elControl = $("controlToggle"), elNew = $("newChat");

  const store = window.localStorage;
  let lang = store.getItem("jv_lang") || "en";          // "en" | "pt" (mic recognition language)
  let control = store.getItem("jv_control") === "1";     // let Jarvis control the Mac
  let conversing = false;                                  // hands-free loop active
  let busy = false;                                        // thinking or speaking
  let recog = null;
  let health = null;                                       // {accessibility, screen_recording} from /api/health

  // Labels for replies that didn't come from the Max-plan brain, so Pietro can tell.
  const SRC_LABEL = {
    ollama:  { en: "offline", pt: "offline" },
    offline: { en: "no brain", pt: "sem cérebro" },
    error:   { en: "error", pt: "erro" },
  };

  const HINTS = {
    idle: { en: "tap the orb to talk — or just type below", pt: "toque na esfera para falar — ou digite abaixo" },
    listening: { en: "listening…", pt: "ouvindo…" },
    thinking: { en: "thinking…", pt: "pensando…" },
    speaking: { en: "", pt: "" },
  };

  // ---- UI state ----------------------------------------------------------------
  function setState(s) {
    body.className = `state-${s}` ;
    elStatus.textContent = s;
    if (s !== "speaking") elHint.textContent = HINTS[s][lang] || HINTS[s].en;
  }

  function addMsg(who, text, placeholder = false) {
    const div = document.createElement("div");
    div.className = `msg ${who === "you" ? "you" : "jv"}${placeholder ? " ph" : ""}`;
    const tag = document.createElement("span");
    tag.className = "who";
    tag.textContent = who === "you" ? "you" : "jarvis";
    const bodyEl = document.createElement("span");
    bodyEl.className = "body";
    bodyEl.textContent = text;
    div.append(tag, bodyEl);
    elTranscript.appendChild(div);
    elTranscript.scrollTop = elTranscript.scrollHeight;
    return div;
  }

  // Tag a Jarvis bubble when the reply came from somewhere other than the Max brain.
  function markSource(div, source) {
    const label = (SRC_LABEL[source] || {})[lang] || (SRC_LABEL[source] || {}).en;
    if (!label) return;  // "max" (or unknown) → no badge
    const b = document.createElement("span");
    b.className = `badge badge-${source}`;
    b.textContent = label;
    div.querySelector(".who").appendChild(b);
  }

  // ---- toggles -----------------------------------------------------------------
  function renderLang() { elLang.textContent = lang === "pt" ? "🇧🇷 PT" : "🇺🇸 EN"; }
  function renderControl() {
    elControl.textContent = `🖥️ Mac control: ${control ? "on" : "off"}`;
    elControl.classList.toggle("on", control);
  }
  elLang.onclick = () => { lang = lang === "pt" ? "en" : "pt"; store.setItem("jv_lang", lang);
    renderLang(); if (recog) recog.lang = lang === "pt" ? "pt-BR" : "en-US";
    if (!busy && !conversing) setState("idle"); };
  elControl.onclick = () => {
    control = !control; store.setItem("jv_control", control ? "1" : "0"); renderControl();
    // If he switches Mac control on but Accessibility isn't granted, it can't click/type.
    if (control && health && !health.accessibility && !busy && !conversing) {
      elHint.textContent = lang === "pt"
        ? "ative Acessibilidade nas Preferências p/ o controle do Mac"
        : "grant Accessibility in System Settings for Mac control";
    }
  };
  renderLang(); renderControl();

  // ---- speech synthesis (the voice) -------------------------------------------
  let voices = [];
  function loadVoices() { voices = window.speechSynthesis ? speechSynthesis.getVoices() : []; }
  if (window.speechSynthesis) {
    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }
  function isPortuguese(t) {
    return /[ãõçáéíóúâêôàü]/i.test(t) ||
      /\b(você|voce|não|nao|está|esta|sim|olá|ola|obrigad|uma|que|por favor|bom dia|tchau)\b/i.test(t);
  }
  function pickVoice(code) { // code: "pt" | "en"
    const want = code === "pt" ? "pt" : "en";
    const byLang = voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith(want));
    return (
      byLang.find((v) => /google/i.test(v.name)) ||  // Google neural voices sound best
      byLang.find((v) => code === "pt" ? /brasil|brazil|BR/i.test(v.lang + v.name) : /US/i.test(v.lang)) ||
      byLang[0] || null
    );
  }
  function speak(text, after) {
    if (!window.speechSynthesis) { after && after(); return; }
    speechSynthesis.cancel();
    const code = isPortuguese(text) ? "pt" : "en";
    const u = new SpeechSynthesisUtterance(text);
    const v = pickVoice(code);
    if (v) u.voice = v;
    u.lang = code === "pt" ? "pt-BR" : "en-US";
    u.rate = 1.0; u.pitch = 1.0;
    setState("speaking");
    u.onend = u.onerror = () => { after && after(); };
    speechSynthesis.speak(u);
  }

  // ---- talking to the brain ----------------------------------------------------
  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true;
    addMsg("you", text);
    elText.value = "";
    setState("thinking");
    // Mac-control turns can take a while (open apps, click, read the screen) — say so.
    if (control) elHint.textContent = lang === "pt" ? "trabalhando no seu Mac…" : "working on your Mac…";
    const ph = addMsg("jarvis", "…", true);
    try {
      const r = await fetch("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, control, lang }),
      });
      const data = await r.json();
      const reply = data.reply || "…";
      ph.classList.remove("ph");
      ph.querySelector(".body").textContent = reply;
      markSource(ph, data.source);
      elTranscript.scrollTop = elTranscript.scrollHeight;
      speak(reply, () => { busy = false; afterTurn(); });
    } catch (e) {
      ph.classList.remove("ph");
      ph.querySelector(".body").textContent =
        lang === "pt" ? "Não consegui falar com o cérebro do Jarvis." : "Couldn't reach Jarvis's brain.";
      markSource(ph, "error");
      busy = false; afterTurn();
    }
  }

  function afterTurn() {
    if (conversing) startRecog();   // hands-free: listen for the next thing
    else setState("idle");
  }

  // ---- speech recognition (the ears, in Chrome) -------------------------------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  function makeRecog() {
    const r = new SR();
    r.lang = lang === "pt" ? "pt-BR" : "en-US";
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      let interim = "", final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t; else interim += t;
      }
      if (interim) elHint.textContent = interim;
      if (final.trim()) { stopRecog(); send(final); }
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        conversing = false;
        elHint.textContent = lang === "pt"
          ? "permita o microfone no Chrome para falar" : "allow the microphone in Chrome to talk";
        setState("idle");
      }
    };
    r.onend = () => {
      // Chrome ends recognition after each phrase; resume if we're still in talk mode.
      if (conversing && !busy) { try { r.start(); } catch (_) {} }
    };
    return r;
  }
  function startRecog() {
    if (!SR) return;
    if (!recog) recog = makeRecog();
    recog.lang = lang === "pt" ? "pt-BR" : "en-US";
    try { recog.start(); setState("listening"); } catch (_) {}
  }
  function stopRecog() { if (recog) { try { recog.abort(); } catch (_) {} } }

  function toggleTalk() {
    // While Jarvis is speaking, a tap silences it (barge-in). speak()'s onend then
    // resumes listening in hands-free mode, or settles to idle for a one-shot.
    if (body.classList.contains("state-speaking")) {
      if (window.speechSynthesis) speechSynthesis.cancel();
      return;
    }
    if (!SR) {
      elHint.textContent = lang === "pt"
        ? "voz funciona no Chrome — por enquanto, digite" : "voice needs Chrome — type for now";
      elText.focus(); return;
    }
    if (conversing) { conversing = false; stopRecog(); setState("idle"); }
    else { conversing = true; if (window.speechSynthesis) speechSynthesis.cancel(); startRecog(); }
  }

  // Start a fresh conversation: forget the brain's session and clear the screen.
  async function newChat() {
    if (busy) return;
    if (window.speechSynthesis) speechSynthesis.cancel();
    conversing = false; stopRecog();
    try { await fetch("/api/reset", { method: "POST" }); } catch (_) {}
    elTranscript.innerHTML = "";
    setState("idle");
    elHint.textContent = HINTS.idle[lang];
  }

  // ---- health ------------------------------------------------------------------
  async function checkHealth() {
    try { health = await (await fetch("/api/health")).json(); }
    catch (_) { health = null; }
  }

  // ---- wiring ------------------------------------------------------------------
  elMic.onclick = toggleTalk;
  elOrb.onclick = toggleTalk;
  elNew.onclick = newChat;
  elOrb.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleTalk(); } };
  elText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && elText.value.trim()) { e.preventDefault(); conversing = false; send(elText.value); }
  });
  // Escape: hush the voice and drop out of hands-free, without touching the transcript.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (conversing) { conversing = false; stopRecog(); if (!busy) setState("idle"); }
  });

  setState("idle");
  checkHealth();
  // a warm first impression
  setTimeout(() => { if (!busy && !conversing) elHint.textContent = HINTS.idle[lang]; }, 50);
})();
