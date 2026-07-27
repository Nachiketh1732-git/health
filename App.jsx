import { useCallback, useEffect, useState } from 'react';
import ReferenceBand from './components/ReferenceBand.jsx';
import Trend from './components/Trend.jsx';
import DataControls from './components/DataControls.jsx';
import CheckIn from './components/CheckIn.jsx';
import { watchUser, login, logout, LOCAL_MODE } from './lib/firebase.js';
import * as api from './lib/api.js';

const STATUS_WORD = {
  steady: 'Steady', watch: 'Worth watching', flag: 'Outside your range', learning: 'Learning',
};

export default function App() {
  const [user, setUser] = useState(undefined);
  const [insights, setInsights] = useState(null);
  const [readings, setReadings] = useState([]);
  const [consent, setConsent] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => watchUser(setUser), []);

  const refresh = useCallback(async (u) => {
    if (!u) return;
    setError('');
    try {
      const c = await api.getConsent(u);
      setConsent(c);
      if (c?.scopes?.store_metrics) {
        const [i, r] = await Promise.all([api.getInsights(u), api.getReadings(u)]);
        setInsights(i);
        setReadings(r.readings);
      } else {
        setInsights(null);
        setReadings([]);
      }
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { if (user) refresh(user); }, [user, refresh]);

  const saveConsent = async (scopes) => {
    await api.saveConsent(user, scopes);
    await refresh(user);
  };

  const submitReadings = async (rows) => {
    await api.postReadings(user, rows);
    await refresh(user);
  };

  const wipe = async () => {
    await api.deleteAccount(user);
    setInsights(null); setReadings([]); setConsent(null);
    await refresh(user);
  };

  if (user === undefined) return <div className="shell"><p className="empty">Loading…</p></div>;

  if (!user) {
    return (
      <div className="shell">
        <div className="masthead">
          <div>
            <div className="eyebrow">Personal baseline analytics</div>
            <h1>Your numbers, against your own normal</h1>
          </div>
        </div>
        <div className="card">
          <p style={{ marginTop: 0, maxWidth: '58ch' }}>
            This dashboard compares each day's readings to the range you personally
            tend to sit in — not to a population average. Sign in to start.
          </p>
          <button onClick={login}>Sign in with Google</button>
        </div>
      </div>
    );
  }

  const r = insights?.readiness;
  const today = insights?.date
    ? new Date(insights.date).toLocaleDateString(undefined,
        { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase()
    : '';

  return (
    <div className="shell">
      <div className="masthead">
        <div>
          <div className="eyebrow">
            {(user.displayName ?? 'You')}{today && ` · ${today}`}
            {LOCAL_MODE && ' · LOCAL MODE'}
          </div>
          <h1>Your numbers, against your own normal</h1>
        </div>
        {!LOCAL_MODE && <button className="ghost" onClick={logout}>Sign out</button>}
      </div>

      {error && (
        <div className="card" style={{ marginBottom: 20, borderColor: 'var(--flag)' }}>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      {!consent?.scopes?.store_metrics && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h2>Before anything is stored</h2>
          <p style={{ maxWidth: '58ch' }}>
            Nothing is saved until you say so. Choose what this app may do with your
            readings below — you can change or revoke any of it later, and deleting
            removes everything for good.
          </p>
        </div>
      )}

      {insights && !insights.empty && (
        <>
          <div className="hero">
            <div className="eyebrow">Readiness</div>
            <div className="hero-figure">
              <span className={`hero-score is-${r.status}`}>{r.score ?? '—'}</span>
              <span className={`tag tag-${r.status}`}>{STATUS_WORD[r.status]}</span>
            </div>
            <p className="hero-note">{r.note}</p>
          </div>

          <div className="grid" style={{ marginBottom: 20 }}>
            <div className="card">
              <h2>Today against your range</h2>
              <div style={{ marginTop: 6 }}>
                {insights.bands.map((b) => <ReferenceBand key={b.metric} band={b} />)}
              </div>
            </div>

            <div className="stack">
              <div className="card">
                <h2>What changed</h2>
                <p className="narrative">{insights.summary.text}</p>
                <div className="source-note">
                  {insights.summary.source === 'gemini'
                    ? 'Phrased by Gemini from computed signals'
                    : 'Generated from computed signals'}
                </div>
              </div>

              <div className="card">
                <h2>Patterns worth noting</h2>
                {insights.signals.length === 0
                  ? <p className="empty" style={{ marginTop: 10 }}>
                      No multi-day patterns standing out right now.
                    </p>
                  : insights.signals.map((s) => (
                      <div className={`signal signal-${s.severity}`} key={s.id}>
                        <strong>{s.title}</strong>
                        <span>{s.detail}</span>
                      </div>
                    ))}
              </div>

              <div className="card">
                <h2>Resting heart rate, 30 days</h2>
                <Trend readings={readings} metric="resting_hr" label="Resting heart rate" unit=" bpm" />
              </div>
            </div>
          </div>
        </>
      )}

      {insights?.empty && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h2>Nothing here yet</h2>
          <p style={{ maxWidth: '54ch' }}>{insights.message}</p>
        </div>
      )}

      <div className="grid">
        <CheckIn onSubmit={submitReadings} />
        <DataControls consent={consent} onSave={saveConsent} onDelete={wipe} />
      </div>

      <p className="disclaimer">
        This is a wellness tracker, not a medical device. It describes how your own
        readings compare to your own history and does not diagnose, treat, or rule out
        any condition. If something here concerns you, or if you feel unwell, speak to
        a qualified clinician.
      </p>
    </div>
  );
}
