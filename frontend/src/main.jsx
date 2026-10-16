import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrainCircuit, Terminal, Play, RotateCcw, CheckCircle2, CircleAlert, Clock3, Code2, Zap } from 'lucide-react';
import './style.css';

const API = 'http://localhost:8000';
const demoTask = 'Calculate the mean, median, and population standard deviation of these values: [12, 15, 18, 21, 24]. Print each metric with a clear label.';

function App() {
  const [task, setTask] = useState(demoTask);
  const [maxAttempts, setMaxAttempts] = useState(4);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(0);

  async function run() {
    setBusy(true); setError(''); setResult(null); setSelected(0);
    try {
      const response = await fetch(`${API}/api/run`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({task, max_attempts: Number(maxAttempts), timeout_seconds: 5})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Request failed');
      setResult(data);
    } catch (e) {
      setError(`${e.message}. Ensure FastAPI is running at ${API} and GROQ_API_KEY is configured.`);
    } finally { setBusy(false); }
  }

  const attempt = result?.attempts?.[selected];

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-icon"><BrainCircuit size={22}/></div><div><div className="brand-title">REFLEXION<span>.AI</span></div><div className="brand-sub">AUTONOMOUS CODE REPAIR LAB</div></div></div>
      <div className="status"><span className="status-dot"/> GROQ ENGINE <span className="status-sep">/</span> FASTAPI</div>
    </header>

    <main>
      <section className="hero">
        <div className="eyebrow"><Zap size={14}/> REASON · ACT · REFLECT</div>
        <h1>Code that learns<br/><span>from its mistakes.</span></h1>
        <p className="hero-copy">An iterative Python agent that generates code, executes it, reads real tracebacks, and repairs its approach until the task is complete.</p>
        <div className="pipeline">
          {['Generate','Execute','Reflect','Repair'].map((label,i)=><React.Fragment key={label}><div className="pipe-step"><span className="pipe-num">0{i+1}</span><span>{label}</span></div>{i<3&&<div className="pipe-line"/>}</React.Fragment>)}
        </div>
      </section>

      <section className="workspace">
        <div className="panel task-panel">
          <div className="panel-head"><div className="panel-label"><span className="tiny-icon"><Terminal size={15}/></span> TASK INPUT</div><span className="subtle-tag">NATURAL LANGUAGE</span></div>
          <label className="field-label" htmlFor="task">What should the agent solve?</label>
          <textarea id="task" value={task} onChange={e=>setTask(e.target.value)} placeholder="Describe a Python task..." rows="5" maxLength={4000}/>
          <div className="input-bottom"><span>{task.length}/4000 characters</span><button className="text-btn" onClick={()=>setTask(demoTask)}><RotateCcw size={13}/> Load demo task</button></div>
          <div className="controls">
            <div><label className="field-label" htmlFor="attempts">MAX ATTEMPTS</label><select id="attempts" value={maxAttempts} onChange={e=>setMaxAttempts(e.target.value)}>{[1,2,3,4,5,6].map(n=><option key={n} value={n}>{n} attempts</option>)}</select></div>
            <button className="run-btn" disabled={busy||task.trim().length<5} onClick={run}>{busy?<span className="spinner"/>:<Play size={16} fill="currentColor"/>}{busy?'Agent working…':'Run agent'}</button>
          </div>
          <div className="security-note"><CircleAlert size={15}/><span>Prototype execution only. Generated code is restricted by checks and a timeout, but this is not a hardened sandbox.</span></div>
          {error&&<div className="error-banner"><CircleAlert size={17}/><span>{error}</span></div>}
        </div>

        <div className="panel result-panel">
          <div className="panel-head"><div className="panel-label"><span className="tiny-icon"><BrainCircuit size={15}/></span> AGENT RUN</div>{result&&<span className={`result-pill ${result.success?'good':'bad'}`}>{result.success?'VERIFIED':'NOT VERIFIED'}</span>}</div>
          {!result&&!busy&&<div className="empty-state"><div className="empty-orb"><BrainCircuit size={28}/></div><h3>Ready to reason.</h3><p>Submit a task to watch each execution and reflection cycle unfold here.</p><div className="empty-chips"><span>Traceback-aware</span><span>Bounded retries</span><span>Attempt history</span></div></div>}
          {busy&&<div className="working-state"><div className="pulse-orb"><BrainCircuit size={30}/></div><h3>Agent loop in progress</h3><p>Generating code · executing · reflecting on output</p><div className="loading-bar"><span/></div><small>Model calls may take a few seconds.</small></div>}
          {result&&<div className="run-content">
            <div className="stats"><div><span>ATTEMPTS</span><strong>{result.attempts_used}<small> / {maxAttempts}</small></strong></div><div><span>FINAL STATE</span><strong className={result.success?'green':'amber'}>{result.success?'Complete':'Unverified'}</strong></div><div><span>TRACE LOGS</span><strong>{result.attempts.length}</strong></div></div>
            <div className="summary"><div className="summary-icon">{result.success?<CheckCircle2 size={18}/>:<CircleAlert size={18}/>}</div><div><strong>{result.success?'Task completed':'Task needs review'}</strong><p>{result.summary}</p></div></div>
            <div className="attempt-list"><div className="section-caption">EXECUTION TIMELINE</div>{result.attempts.map((a,i)=><button key={a.number} className={`attempt-row ${selected===i?'active':''}`} onClick={()=>setSelected(i)}><span className={`attempt-icon ${a.success?'passed':'failed'}`}>{a.success?<CheckCircle2 size={15}/>:<CircleAlert size={15}/>}</span><span className="attempt-name">Attempt {a.number}<small>{a.success?'Process exited successfully':'Execution or validation failed'}</small></span><span className="attempt-time"><Clock3 size={12}/>{a.duration_ms}ms</span></button>)}</div>
            {attempt&&<div className="detail-box">
              <div className="detail-head"><div><Code2 size={15}/> ATTEMPT {attempt.number} DETAILS</div><span className={attempt.success?'green':'amber'}>{attempt.exit_code===0?'EXIT 0':`EXIT ${attempt.exit_code}`}</span></div>
              <div className="code-label">GENERATED PYTHON</div><pre className="code-block"><code>{attempt.code}</code></pre>
              <div className="code-label">STANDARD OUTPUT</div><pre className="output-block">{attempt.stdout||'(no output)'}</pre>
              {attempt.stderr&&<><div className="code-label error-label">STDERR / TRACEBACK</div><pre className="stderr-block">{attempt.stderr}</pre></>}
              {attempt.reflection&&<div className="reflection"><BrainCircuit size={15}/><div><strong>REFLECTION</strong><p>{attempt.reflection}</p></div></div>}
            </div>}
            {result.final_output&&<div className="final-output"><div className="code-label">LATEST OUTPUT</div><pre>{result.final_output}</pre></div>}
          </div>}
        </div>
      </section>
      <footer><span>REFLEXION.AI <span className="footer-dot">•</span> EDUCATIONAL PROTOTYPE</span><span>BOUNDED LOOP <b>●</b> TRACEBACK FEEDBACK <b>●</b> OUTPUT VERIFICATION</span></footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App/>);
