import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, STAGES } from "../api.js";
import { Alert, Spinner, fmtDate, fmtDateTime } from "../components/ui.jsx";
import ChangePasswordModal from "../components/ChangePasswordModal.jsx";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [pwOpen, setPwOpen] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => { api("/api/dashboard").then(setData).catch((e) => setError(e.message)); }, []);

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Spinner label="Loading dashboard…" />;

  const max = Math.max(1, ...Object.values(data.by_stage));
  const empty = data.total_applications === 0;

  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>Job-hunt dashboard</h1>
        <div className="row">
          <button className="btn" onClick={() => { setNotice(""); setPwOpen(true); }}>Change password</button>
          <Link className="btn primary" to="/match">Run an AI match</Link>
        </div>
      </div>

      <Alert kind="success" onClose={() => setNotice("")}>{notice}</Alert>
      {pwOpen && (
        <ChangePasswordModal
          onClose={() => setPwOpen(false)}
          onDone={() => { setPwOpen(false); setNotice("Password updated."); }}
        />
      )}

      {empty && (
        <div className="card empty">
          <h2>Let's get your search going</h2>
          <p className="muted">Add your resume, paste a job description to get a fit score, then save it to your pipeline.</p>
          <div className="row"><Link className="btn" to="/resume">Add resume</Link><Link className="btn" to="/pipeline">Add an application</Link></div>
        </div>
      )}

      <div className="kpis">
        <div className="kpi card">
          <span className="kpi-label">Total applications</span>
          <span className="kpi-value">{data.total_applications}</span>
          <span className="muted small">{data.applications_sent} sent</span>
        </div>
        <div className="kpi card">
          <span className="kpi-label">Interviews this week</span>
          <span className="kpi-value">{data.interviews_this_week}</span>
          <span className="muted small">{fmtDate(data.week_start)} – {fmtDate(data.week_end)}</span>
        </div>
        <div className="kpi card">
          <span className="kpi-label">Response rate</span>
          <span className="kpi-value">{data.response_rate == null ? "—" : `${data.response_rate}%`}</span>
          <span className="muted small">{data.applications_with_response} of {data.applications_sent} sent got a reply</span>
        </div>
      </div>

      <div className="grid-2">
        <section className="card">
          <h2>Applications by stage</h2>
          <ul className="bars">
            {STAGES.map((s) => (
              <li key={s.key}>
                <span className="bar-label">{s.label}</span>
                <span className="bar-track"><span className={`bar-fill stage-${s.key.toLowerCase()}`} style={{ width: `${(data.by_stage[s.key] / max) * 100}%` }} /></span>
                <span className="bar-value">{data.by_stage[s.key]}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>Upcoming interviews</h2>
          {data.upcoming_interviews.length === 0 ? (
            <p className="muted">No upcoming interviews. Add one from an application card on the <Link to="/pipeline">pipeline</Link>.</p>
          ) : (
            <ul className="list">
              {data.upcoming_interviews.map((i) => (
                <li key={i.id}>
                  <div><strong>{i.company}</strong> <span className="muted">· {i.role}</span></div>
                  <div className="small">{fmtDateTime(i.scheduled_at)}{i.round && <span className="chip">{i.round}</span>}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
