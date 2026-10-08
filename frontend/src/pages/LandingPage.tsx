import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

// ─── Design tokens (from vero-landing.html reference) ─────────────────────────
const C = {
  blue: '#1C55BB',
  blueDk: '#1441a0',
  blueLt: '#2563EB',
  bluePale: '#EFF4FF',
  border: '#e2e8f0',
  text: '#1a2332',
  muted: '#64748b',
  faint: '#94a3b8',
  green: '#10b981',
  purple: '#7c3aed',
  orange: '#f59e0b',
  shadow: '0 4px 16px rgba(0,0,0,.08), 0 2px 6px rgba(0,0,0,.04)',
}

// ─── Data ─────────────────────────────────────────────────────────────────────
const STEPS = [
  { icon: '📋', num: 'Step 01', title: 'Load a Skill Pack', desc: 'The host configures Vero with a Skill Pack — a YAML file that defines the agent persona, question bank, scoring rubric, and report template. Invite Vero to a Teams meeting or schedule a phone call.' },
  { icon: '🤝', num: 'Step 02', title: 'Vero Joins the Meeting', desc: 'Vero joins via Recall.ai as a named participant — "Alex (Vero)" appears in the Teams participant list. For phone, Twilio bridges the PSTN call into a LiveKit room. Vero opens with the skill-defined greeting.' },
  { icon: '🎧', num: 'Step 03', title: 'Audio Capture & Transcription', desc: 'Recall.ai streams PCM audio to the pipeline. Sarvam Saaras v3 transcribes every utterance with speaker diarisation — each turn labelled as Vero or Participant with timestamps.' },
  { icon: '⚡', num: 'Step 04', title: 'Real-time Agent Loop', desc: 'On each turn, the Node.js agent evaluates the response against the rubric, decides the next action — follow up, clarify, advance, or close — and returns structured JSON: next utterance + score update. All within 4 seconds.' },
  { icon: '🗣️', num: 'Step 05', title: 'Vero Responds', desc: 'The LLM utterance is sent to Sarvam Bulbul v3 TTS (30+ natural voices). Audio is injected back into the Teams meeting or phone call in real time. The participant hears Vero speak naturally.' },
  { icon: '📊', num: 'Step 06', title: 'Live Session Monitoring', desc: 'Every turn is persisted to the database. The History page auto-refreshes every 3 seconds. Recruiters and managers watch the live transcript panel as the conversation unfolds — no WebSockets required.' },
  { icon: '📧', num: 'Step 07', title: 'Report in 60 Seconds', desc: 'Within 60 seconds of call end, a structured report is generated using the Skill Pack report template: per-question scores, competency ratings, verbatim excerpts, and a hire/no-hire recommendation. Delivered by email.' },
  { icon: '🔄', num: 'Step 08', title: 'Swap Skill, New Expert', desc: 'Change the active Skill Pack YAML and restart the service. Vero becomes a Sales Manager, Pre-sales Consultant, or Compliance Officer with zero code changes. One platform, every structured conversation.' },
]

const SKILL_PACKS = [
  { icon: '🎤', name: 'Technical Interviewer', output: 'Candidate scorecard + hire/no-hire', tag: 'interviewer-v1' },
  { icon: '🏆', name: 'Sales Coach', output: 'Rep performance scorecard + gaps', tag: 'sales-coach-v1' },
  { icon: '🏗️', name: 'Solutions Architect', output: 'Requirements brief + gap analysis', tag: 'architect-v1' },
  { icon: '🔍', name: 'Discovery Agent', output: 'Qualified opportunity brief + next steps', tag: 'discovery-v1' },
  { icon: '📋', name: 'Compliance Auditor', output: 'Audit response log + risk flags', tag: 'audit-v1' },
  { icon: '👋', name: 'Onboarding Buddy', output: 'Onboarding completion record', tag: 'onboarding-v1' },
  { icon: '🎧', name: 'Complaint Investigator', output: 'Complaint investigation report', tag: 'complaint-v1' },
  { icon: '⚙️', name: 'Custom Skill Pack', output: 'Your rubric, your report format', tag: 'custom-yaml' },
]

const CHANNELS = [
  {
    icon: '💼',
    title: 'Microsoft Teams Channel',
    desc: 'Vero joins as a named participant via Recall.ai bot. Azure AD authenticated. Streams PCM audio, transcribes with Sarvam Saaras v3, speaks back via Bulbul v3 TTS.',
    tags: ['Recall.ai Bot', 'Sarvam Saaras v3 STT', 'Bulbul v3 TTS', 'Azure AD Auth', 'Node.js Agent', 'EOU Detection'],
  },
  {
    icon: '📞',
    title: 'Phone Channel (PSTN)',
    desc: 'Vero dials any phone number via Twilio SIP trunk into a LiveKit room. Sarvam AI Realtime handles speech-to-speech with sub-second latency. Call recording included.',
    tags: ['Twilio SIP', 'LiveKit', 'Sarvam Realtime', 'Call Recording', 'E.164 Numbers', 'MCP Architecture'],
  },
  {
    icon: '🤖',
    title: 'Sarvam AI Engine',
    desc: 'Unified AI stack across both channels. Saaras v3 for STT, Bulbul v3 for TTS, Sarvam-30B / 105B for conversation intelligence. Supports 23 languages including all major Indian languages.',
    tags: ['Saaras v3 STT', 'Bulbul v3 TTS', 'Sarvam-30B LLM', '23 Languages', 'Hindi/Tamil/Telugu', 'en-IN Default'],
  },
  {
    icon: '📄',
    title: 'Skill Pack Config',
    desc: 'YAML-driven conversation blueprints. Two modes: Guided (fixed question sequence) and Intelligent (objectives-based adaptive). One config change, completely new agent behaviour.',
    tags: ['YAML Schema', 'Guided Mode', 'Intelligent Mode', 'Scoring Rubric', 'Report Template', 'No Code Change'],
  },
]

const TECH = ['Sarvam AI (STT · TTS · LLM)', 'Recall.ai', 'LiveKit SIP', 'Twilio', 'FastAPI Python', 'Node.js TypeScript', 'PostgreSQL', 'Redis', 'React + Vite', 'Docker Compose', 'Resend Email', 'Azure AD']

const NAV_SECTIONS = [
  { label: 'Home', target: 'lp-hero' },
  { label: 'How It Works', target: 'lp-how' },
  { label: 'Skill Packs', target: 'lp-skillpacks' },
  { label: 'Channels', target: 'lp-channels' },
]

const TRUST_ITEMS = [
  { color: C.blue, label: 'Microsoft Teams Native' },
  { color: C.purple, label: 'Sarvam AI · 23 Languages' },
  { color: C.green, label: '60s Report Delivery' },
  { color: C.orange, label: 'Skill Pack Architecture' },
  { color: '#ef4444', label: 'Zero Human in Loop' },
  { color: '#06b6d4', label: 'LiveKit SIP · Phone Channel' },
]

const WAVE_DELAYS = [0, 0.1, 0.2, 0.3, 0.4, 0.15, 0.25, 0.35, 0.05, 0.45, 0.2, 0.3]
const WAVE_HEIGHTS = [8, 16, 22, 14, 20, 10, 18, 12, 24, 8, 16, 20]

// ─── LandingPage ──────────────────────────────────────────────────────────────
export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false)
  const [activeSection, setActiveSection] = useState('lp-hero')
  const [curStep, setCurStep] = useState(0)
  const [modalOpen, setModalOpen] = useState(false)
  const [waveActive, setWaveActive] = useState(true)

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 10)
      const ids = ['lp-hero', 'lp-how', 'lp-skillpacks', 'lp-channels']
      let cur = 'lp-hero'
      ids.forEach(id => {
        const el = document.getElementById(id)
        if (el && window.scrollY >= el.offsetTop - 100) cur = id
      })
      setActiveSection(cur)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const t = setInterval(() => setCurStep(s => (s + 1) % STEPS.length), 4000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const t = setInterval(() => setWaveActive(a => !a), 3000)
    return () => clearInterval(t)
  }, [])

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      {/* Scoped styles for animations + hover effects */}
      <style>{`
@keyframes lp-pulse { 0%,100%{ opacity:1; transform:scale(1); } 50%{ opacity:.4; transform:scale(.75); } }
        @keyframes lp-float { from{ opacity:0; transform:translateY(18px); } to{ opacity:1; transform:translateY(0); } }
        @keyframes lp-wave { 0%,100%{ height:6px; } 50%{ height:22px; } }
        .lp-live-dot { width:7px; height:7px; border-radius:50%; background:${C.green}; animation:lp-pulse 2s infinite; flex-shrink:0; display:inline-block; }
        .lp-voice-card { animation:lp-float .6s ease both; }
        .lp-wave-bar { width:4px; border-radius:2px; background:${C.blue}; }
        .lp-skill-cell:hover { background:rgba(28,85,187,.03); }
        .lp-skill-cell:hover .lp-skill-bar { height:44px !important; }
        .lp-skill-cell:hover .lp-skill-name { color:${C.blue} !important; transform:translateX(4px); }
        .lp-skill-cell:hover .lp-skill-icon { transform:translateX(4px); }
        .lp-channel-card { transition:all .22s; }
        .lp-channel-card:hover { box-shadow:${C.shadow}; border-color:rgba(28,85,187,.22) !important; transform:translateY(-2px); }
        .lp-tech-tag:hover { border-color:${C.blue} !important; color:${C.blue} !important; background:${C.bluePale} !important; }
        .lp-nav-link { padding:8px 16px; border-radius:8px; font-size:13px; font-weight:500; color:${C.muted}; cursor:pointer; transition:all .15s; user-select:none; }
        .lp-nav-link:hover, .lp-nav-link.active { background:${C.bluePale}; color:${C.blue}; font-weight:600; }
        .lp-btn-primary { background:${C.blue}; color:#fff; box-shadow:0 2px 8px rgba(28,85,187,.28); transition:all .2s; border:none; }
        .lp-btn-primary:hover { background:${C.blueDk}; box-shadow:0 6px 20px rgba(28,85,187,.38); transform:translateY(-1px); }
        .lp-btn-outline { background:#fff; color:${C.text}; border:1.5px solid ${C.border}; transition:all .2s; }
        .lp-btn-outline:hover { border-color:${C.blue}; color:${C.blue}; background:${C.bluePale}; }
        .lp-s-btn { width:38px; height:38px; border-radius:50%; border:1.5px solid ${C.border}; background:#fff; display:flex; align-items:center; justify-content:center; cursor:pointer; color:${C.muted}; transition:all .2s; }
        .lp-s-btn:hover { background:${C.blue} !important; color:#fff !important; border-color:${C.blue} !important; }
        .lp-s-dot { width:6px; height:6px; border-radius:50%; background:${C.border}; cursor:pointer; transition:all .2s; flex-shrink:0; }
        .lp-s-dot.on { background:${C.blue}; width:18px; border-radius:3px; }
        .lp-footer-link { display:block; font-size:13px; color:${C.muted}; padding:3px 0; transition:color .15s; cursor:pointer; }
        .lp-footer-link:hover { color:${C.blue}; }
        .lp-input { width:100%; padding:10px 13px; border:1.5px solid ${C.border}; border-radius:8px; font-size:14px; color:${C.text}; outline:none; background:#fff; transition:border-color .2s, box-shadow .2s; }
        .lp-input:focus { border-color:${C.blue}; box-shadow:0 0 0 3px rgba(28,85,187,.1); }
        .lp-step-card { transition:all .4s cubic-bezier(.22,1,.36,1); }
      `}</style>

      <div style={{ color: C.text, background: '#fff', fontSize: 15, lineHeight: 1.6 }}>

        {/* ── NAVBAR ────────────────────────────────────────────────────────── */}
        <nav style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 999, height: 64,
          background: 'rgba(255,255,255,.96)', backdropFilter: 'blur(14px)',
          borderBottom: '1px solid rgba(226,232,240,.8)',
          display: 'flex', alignItems: 'center', padding: '0 40px', justifyContent: 'space-between',
          transition: 'box-shadow .25s',
          boxShadow: scrolled ? '0 2px 24px rgba(0,0,0,.09)' : 'none',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, flexShrink: 0 }}>
            <div style={{ width: 40, height: 40, background: `linear-gradient(135deg,${C.blue},${C.blueLt})`, borderRadius: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 19, fontWeight: 700 }}>V</div>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, color: C.blue, lineHeight: 1 }}>Vero</div>
              <div style={{ fontSize: 10, color: C.muted, letterSpacing: '.7px', textTransform: 'uppercase', marginTop: 2 }}>AI Voice Agent Platform</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 2 }}>
            {NAV_SECTIONS.map(({ label, target }) => (
              <span key={target} className={`lp-nav-link${activeSection === target ? ' active' : ''}`} onClick={() => scrollTo(target)}>{label}</span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 9, alignItems: 'center', flexShrink: 0 }}>
            <Link to="/sessions">
              <button className="lp-btn-outline" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>Sign In</button>
            </Link>
            <button className="lp-btn-primary" onClick={() => setModalOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>Request Demo →</button>
          </div>
        </nav>

        {/* ── HERO ──────────────────────────────────────────────────────────── */}
        <section id="lp-hero" style={{ paddingTop: 64, background: 'linear-gradient(160deg, #eef3fc 0%, #f0f4ff 35%, #f8f5ff 65%, #ffffff 100%)', position: 'relative' }}>
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0, backgroundImage: `linear-gradient(rgba(28,85,187,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(28,85,187,.045) 1px,transparent 1px)`, backgroundSize: '52px 52px' }} />
          <div style={{ position: 'absolute', top: -80, right: '5%', width: 620, height: 620, borderRadius: '50%', pointerEvents: 'none', zIndex: 0, background: 'radial-gradient(ellipse,rgba(28,85,187,.08) 0%,transparent 70%)' }} />
          <div style={{ position: 'absolute', bottom: 60, left: -60, width: 420, height: 420, borderRadius: '50%', pointerEvents: 'none', zIndex: 0, background: 'radial-gradient(ellipse,rgba(124,58,237,.055) 0%,transparent 70%)' }} />
          <div style={{ position: 'relative', zIndex: 1, maxWidth: 1200, margin: '0 auto', padding: '72px 40px 80px', display: 'flex', alignItems: 'center', gap: 48 }}>
            {/* Left */}
            <div style={{ flex: 1, minWidth: 0, maxWidth: 580 }}>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 13px', border: '1px solid rgba(28,85,187,.2)', background: 'rgba(28,85,187,.045)', borderRadius: 24, fontSize: 12, color: C.muted, marginBottom: 24 }}>
                <span className="lp-live-dot" />Active voice sessions now · 3 concurrent interviews
              </div>
              <h1 style={{ fontSize: 'clamp(38px,5vw,60px)', fontWeight: 800, letterSpacing: '-.4px', color: C.text, marginBottom: 16, lineHeight: 1.06 }}>
                <span style={{ color: C.blue }}>Vero</span><br />AI That Takes<br />a Seat &amp; Leads
              </h1>
              <p style={{ fontSize: 14, fontWeight: 600, color: C.muted, marginBottom: 12 }}>Microsoft Teams · Phone Channel · Sarvam AI · Skill Packs</p>
              <p style={{ fontSize: 16, color: C.muted, lineHeight: 1.78, marginBottom: 32, maxWidth: 500 }}>
                An autonomous AI conversation agent that joins your Teams meetings or dials phone numbers, drives structured interviews, discovery calls, and coaching sessions — then delivers a scored report within 60 seconds of call end.
              </p>
              <div style={{ display: 'flex', marginBottom: 36 }}>
                {[{ n: '<4s', l: 'Response Latency' }, { n: '7', l: 'Skill Pack Roles' }, { n: '23', l: 'Languages Supported' }].map((s, i) => (
                  <div key={i} style={{ paddingRight: i < 2 ? 24 : 0, paddingLeft: i > 0 ? 24 : 0, borderLeft: i > 0 ? `1px solid ${C.border}` : 'none' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: C.text, lineHeight: 1 }}>{s.n}</div>
                    <div style={{ fontSize: 11, color: C.muted, marginTop: 3 }}>{s.l}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <button className="lp-btn-primary" onClick={() => setModalOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 30px', borderRadius: 12, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>Request Demo</button>
                <button className="lp-btn-outline" onClick={() => scrollTo('lp-skillpacks')} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 30px', borderRadius: 12, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>Explore Skill Packs</button>
              </div>
            </div>
            {/* Right — Voice Card */}
            <div style={{ flexShrink: 0, width: 460, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div className="lp-voice-card" style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 20, padding: 28, boxShadow: C.shadow, width: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: `linear-gradient(135deg,${C.blue},${C.blueLt})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 18, color: '#fff', flexShrink: 0 }}>V</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15 }}>Vero — Alex</div>
                    <div style={{ fontSize: 12, color: C.muted }}>Technical Interviewer · interviewer-v1</div>
                  </div>
                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.green, fontWeight: 600 }}>
                    <span className="lp-live-dot" /> Live
                  </div>
                </div>
                {/* Waveform bars */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 3, height: 28, marginBottom: 20 }}>
                  {WAVE_DELAYS.map((delay, i) => (
                    <div key={i} className="lp-wave-bar" style={{
                      height: waveActive ? WAVE_HEIGHTS[i] : 3,
                      animation: waveActive ? `lp-wave 0.8s ease-in-out ${delay}s infinite` : 'none',
                      transition: waveActive ? 'none' : 'height 0.3s ease',
                    }} />
                  ))}
                </div>
                <div style={{ fontSize: 13, color: C.text, lineHeight: 1.65, background: C.bluePale, borderRadius: 10, padding: '12px 14px', marginBottom: 16, borderLeft: `3px solid ${C.blue}` }}>
                  <span style={{ color: C.blue, fontWeight: 600 }}>Alex (Vero):</span> "That's a great starting point. Can you walk me through how you handled schema migrations at scale in your last role?"
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600, background: C.bluePale, color: C.blue, border: '1px solid #bfdbfe' }}>🎯 Communication: 4/5</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600, background: '#f0fdf4', color: '#065f46', border: '1px solid #bbf7d0' }}>✅ System Design: 3/5</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600, background: '#fffbeb', color: '#92400e', border: '1px solid #fde68a' }}>⏳ Depth: probing...</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.border}`, fontSize: 12 }}>
                  <span style={{ color: C.muted }}>Active skill:</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 6, background: '#f5f3ff', color: C.purple, fontSize: 11, fontWeight: 600, border: '1px solid #ddd6fe' }}>📋 interviewer-v1</span>
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: C.muted }}>Q3 of 8</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── TRUST BAR ─────────────────────────────────────────────────────── */}
        <div style={{ padding: '18px 0', background: '#fff', borderTop: `1px solid ${C.border}`, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 36, flexWrap: 'wrap' }}>
            {TRUST_ITEMS.map(({ color, label }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, color: C.muted, fontSize: 13, fontWeight: 500 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0, display: 'inline-block' }} />{label}
              </div>
            ))}
          </div>
        </div>

        {/* ── HOW IT WORKS ──────────────────────────────────────────────────── */}
        <section id="lp-how" style={{ padding: '96px 0', background: 'linear-gradient(180deg,#fff9ef 0%,#fffcf5 60%,#fff 100%)' }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px' }}>
            <div style={{ textAlign: 'center', marginBottom: 56 }}>
              <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1.4px', color: C.blue, marginBottom: 10 }}>How It Works</span>
              <h2 style={{ fontSize: 'clamp(28px,3.8vw,42px)', fontWeight: 700, color: C.text, marginBottom: 14 }}>End-to-End in 8 Stages</h2>
              <p style={{ fontSize: 16, color: C.muted, maxWidth: 620, margin: '0 auto', lineHeight: 1.75 }}>From loading a Skill Pack to a scored report in your inbox — fully autonomous, no human involvement during the call.</p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64, alignItems: 'center', maxWidth: 940, margin: '0 auto' }}>
              {/* Stacked step cards */}
              <div style={{ position: 'relative', height: 300 }}>
                {STEPS.map((step, i) => {
                  const diff = i - curStep
                  if (Math.abs(diff) > 2) return null
                  const isActive = diff === 0
                  return (
                    <div key={i} className="lp-step-card" onClick={() => setCurStep(i)} style={{
                      position: 'absolute', inset: 0, borderRadius: 20,
                      background: '#fff', border: `1px solid ${C.border}`,
                      boxShadow: isActive ? C.shadow : 'none',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                      padding: '36px 28px', cursor: 'pointer',
                      opacity: isActive ? 1 : Math.max(0, 0.4 - Math.abs(diff) * 0.15),
                      transform: isActive ? 'none' : `translate(${diff * 8}px,${Math.abs(diff) * 6}px)`,
                      zIndex: isActive ? 10 : 10 - Math.abs(diff),
                    }}>
                      <div style={{ width: 62, height: 62, borderRadius: 14, background: C.bluePale, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, marginBottom: 16 }}>{step.icon}</div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: C.blue, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>{step.num}</div>
                      <div style={{ fontSize: 17, fontWeight: 700, textAlign: 'center', color: C.text }}>{step.title}</div>
                    </div>
                  )
                })}
              </div>
              {/* Step text + nav */}
              <div style={{ display: 'flex', flexDirection: 'column', minHeight: 260 }}>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: 23, fontWeight: 700, marginBottom: 16, color: C.text }}>{STEPS[curStep].title}</h3>
                  <p style={{ fontSize: 15, color: C.muted, lineHeight: 1.8 }}>{STEPS[curStep].desc}</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 24 }}>
                  <button className="lp-s-btn" onClick={() => setCurStep(s => (s - 1 + STEPS.length) % STEPS.length)}>
                    <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M15 19l-7-7 7-7" /></svg>
                  </button>
                  <button className="lp-s-btn" onClick={() => setCurStep(s => (s + 1) % STEPS.length)}>
                    <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M9 5l7 7-7 7" /></svg>
                  </button>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {STEPS.map((_, i) => (
                      <div key={i} className={`lp-s-dot${i === curStep ? ' on' : ''}`} onClick={() => setCurStep(i)} />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── SKILL PACKS ───────────────────────────────────────────────────── */}
        <section id="lp-skillpacks" style={{ padding: '96px 0', background: 'linear-gradient(180deg,#efffef 0%,#f3fdf8 40%,#fff 100%)' }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px' }}>
            <div style={{ textAlign: 'center', marginBottom: 48 }}>
              <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1.4px', color: C.blue, marginBottom: 10 }}>Skill Packs</span>
              <h2 style={{ fontSize: 'clamp(28px,3.8vw,42px)', fontWeight: 700, color: C.text, marginBottom: 14 }}>One Agent, Every Role</h2>
              <p style={{ fontSize: 16, color: C.muted, maxWidth: 620, margin: '0 auto', lineHeight: 1.75 }}>Swap the YAML, Vero becomes a different expert. No code changes required — persona, questions, rubric, and report template all driven by config.</p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', background: '#fff', border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden', boxShadow: C.shadow }}>
              {SKILL_PACKS.map((sk, i) => (
                <div key={i} className="lp-skill-cell" style={{ padding: '32px 26px', borderRight: (i + 1) % 4 !== 0 ? `1px solid ${C.border}` : 'none', borderBottom: i < 4 ? `1px solid ${C.border}` : 'none', position: 'relative', cursor: 'pointer', transition: 'background .2s' }}>
                  <div className="lp-skill-bar" style={{ position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)', width: 3, height: 0, background: C.blue, borderRadius: '0 2px 2px 0', transition: 'height .25s' }} />
                  <span className="lp-skill-icon" style={{ fontSize: 20, marginBottom: 12, display: 'block', transition: 'transform .2s' }}>{sk.icon}</span>
                  <div className="lp-skill-name" style={{ fontSize: 14, fontWeight: 700, marginBottom: 4, transition: 'color .2s, transform .2s' }}>{sk.name}</div>
                  <div style={{ fontSize: 11, color: C.muted, marginBottom: 7, lineHeight: 1.5 }}>{sk.output}</div>
                  <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: C.bluePale, color: C.blue, border: '1px solid #bfdbfe' }}>{sk.tag}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── CHANNELS ──────────────────────────────────────────────────────── */}
        <section id="lp-channels" style={{ padding: '96px 0', background: 'linear-gradient(180deg,#f9f5ff 0%,#faf7ff 60%,#fff 100%)' }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px' }}>
            <div style={{ textAlign: 'center', marginBottom: 48 }}>
              <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1.4px', color: C.blue, marginBottom: 10 }}>Channels</span>
              <h2 style={{ fontSize: 'clamp(28px,3.8vw,42px)', fontWeight: 700, color: C.text, marginBottom: 14 }}>Teams or Phone — Your Call</h2>
              <p style={{ fontSize: 16, color: C.muted, maxWidth: 620, margin: '0 auto', lineHeight: 1.75 }}>Dual-channel architecture supports both Microsoft Teams and PSTN phone numbers. Same Skill Pack, same output report.</p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, maxWidth: 920, margin: '0 auto' }}>
              {CHANNELS.map((ch, i) => (
                <div key={i} className="lp-channel-card" style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 14, padding: 28, display: 'flex', gap: 18 }}>
                  <div style={{ width: 52, height: 52, borderRadius: 14, background: C.bluePale, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>{ch.icon}</div>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>{ch.title}</div>
                    <div style={{ fontSize: 13, color: C.muted, lineHeight: 1.65, marginBottom: 10 }}>{ch.desc}</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                      {ch.tags.map(tag => (
                        <span key={tag} style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: C.bluePale, color: C.blue, border: '1px solid #bfdbfe' }}>{tag}</span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── TECH STACK ────────────────────────────────────────────────────── */}
        <div style={{ padding: '52px 0', background: '#fff', borderTop: `1px solid ${C.border}` }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px' }}>
            <p style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1.2px', color: C.faint, marginBottom: 22, textAlign: 'center' }}>Powered by enterprise-grade open technology</p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
              {TECH.map(t => (
                <span key={t} className="lp-tech-tag" style={{ padding: '7px 16px', border: `1px solid ${C.border}`, borderRadius: 24, fontSize: 13, fontWeight: 500, color: C.muted, background: '#fff', cursor: 'default', transition: 'all .2s' }}>{t}</span>
              ))}
            </div>
          </div>
        </div>

        {/* ── CTA ───────────────────────────────────────────────────────────── */}
        <section style={{ padding: '96px 0', background: 'linear-gradient(135deg,#e8f0fe 0%,#edf3fe 60%,#f0f5ff 100%)' }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px' }}>
            <div style={{ border: '1px solid rgba(28,85,187,.15)', borderRadius: 24, padding: '80px 48px', textAlign: 'center', maxWidth: 760, margin: '0 auto', background: 'rgba(255,255,255,.5)' }}>
              <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1.4px', color: C.blue, marginBottom: 12 }}>Real conversations, intelligently driven</span>
              <h2 style={{ fontSize: 'clamp(26px,3.6vw,40px)', fontWeight: 700, marginBottom: 14 }}>Ready to Deploy Vero?</h2>
              <p style={{ fontSize: 16, color: C.muted, marginBottom: 32, maxWidth: 500, margin: '0 auto 32px', lineHeight: 1.7 }}>Cut time-to-shortlist from 2 weeks to 2 days. Run 20 parallel interviews with zero recruiter time. Scale structured conversations across every vertical.</p>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button className="lp-btn-primary" onClick={() => setModalOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 30px', borderRadius: 12, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>Request Demo</button>
                <button className="lp-btn-outline" onClick={() => scrollTo('lp-skillpacks')} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 30px', borderRadius: 12, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>View Skill Packs</button>
              </div>
            </div>
          </div>
        </section>

        {/* ── FOOTER ────────────────────────────────────────────────────────── */}
        <footer style={{ background: '#f4f7fb', borderTop: `1px solid ${C.border}`, padding: '60px 0 0' }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 40px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 48, marginBottom: 48 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: C.blue, marginBottom: 8 }}>Vero</div>
                <p style={{ fontSize: 13, color: C.muted, lineHeight: 1.7, maxWidth: 230, marginBottom: 14 }}>The AI agent that takes a seat in any conversation — interviewer, coach, consultant, or auditor.</p>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600, background: C.bluePale, color: C.blue, border: '1px solid #bfdbfe' }}>POC · v0 · March 2026</span>
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 12 }}>Platform</div>
                {['Skill Packs', 'Teams Channel', 'Phone Channel', 'Session History', 'Report Gallery'].map(l => <span key={l} className="lp-footer-link">{l}</span>)}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 12 }}>Use Cases</div>
                {['Technical Interviews', 'Sales Coaching', 'Discovery Calls', 'Compliance Audits', 'HR Onboarding'].map(l => <span key={l} className="lp-footer-link">{l}</span>)}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 12 }}>Technology</div>
                {['Sarvam AI', 'Recall.ai', 'LiveKit SIP', 'FastAPI Backend', 'Architecture Docs'].map(l => <span key={l} className="lp-footer-link">{l}</span>)}
              </div>
            </div>
            <div style={{ borderTop: `1px solid ${C.border}`, padding: '18px 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: C.muted }}>
              <span>© 2026 Vero — AI Voice Agent Platform. Built by Minfy Technologies.</span>
              <span>Powered by Sarvam AI · Recall.ai · LiveKit</span>
            </div>
          </div>
        </footer>

        {/* ── DEMO MODAL ────────────────────────────────────────────────────── */}
        {modalOpen && (
          <div onClick={e => e.target === e.currentTarget && setModalOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(10,20,40,.5)', backdropFilter: 'blur(8px)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: 22, padding: 44, width: '100%', maxWidth: 410, boxShadow: '0 32px 80px rgba(0,0,0,.22)', position: 'relative' }}>
              <button onClick={() => setModalOpen(false)} style={{ position: 'absolute', top: 14, right: 14, width: 30, height: 30, borderRadius: '50%', border: `1px solid ${C.border}`, background: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.muted, fontSize: 13, cursor: 'pointer' }}>✕</button>
              <div style={{ width: 40, height: 40, background: `linear-gradient(135deg,${C.blue},${C.blueLt})`, borderRadius: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 18, color: '#fff', marginBottom: 16 }}>V</div>
              <div style={{ fontSize: 21, fontWeight: 700, marginBottom: 4 }}>Request a Demo</div>
              <div style={{ fontSize: 13, color: C.muted, marginBottom: 24 }}>See Vero run a live interview or discovery call on your Teams tenant.</div>
              {[
                { label: 'Full Name', type: 'text', placeholder: 'Your name' },
                { label: 'Work Email', type: 'email', placeholder: 'you@company.com' },
                { label: 'Company', type: 'text', placeholder: 'Company name' },
              ].map(({ label, type, placeholder }) => (
                <div key={label} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 5 }}>{label}</label>
                  <input type={type} placeholder={placeholder} className="lp-input" />
                </div>
              ))}
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 5 }}>Use Case</label>
                <select className="lp-input">
                  <option>Technical Interviews</option>
                  <option>Sales Coaching</option>
                  <option>Discovery Calls</option>
                  <option>Compliance Audits</option>
                  <option>HR Onboarding</option>
                  <option>Other</option>
                </select>
              </div>
              <button className="lp-btn-primary" onClick={() => setModalOpen(false)} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px 20px', borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>Request Demo →</button>
              <p style={{ textAlign: 'center', fontSize: 11, color: C.muted, marginTop: 12 }}>We'll reach out within one business day to schedule a live session.</p>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
