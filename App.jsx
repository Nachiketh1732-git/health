import { useCallback, useEffect, useState } from 'react';
import ReferenceBand from './components/ReferenceBand.jsx';
import Trend from './components/Trend.jsx';
import DataControls from './components/DataControls.jsx';
import CheckIn from './components/CheckIn.jsx';
import AuthScreen from './components/AuthScreen.jsx';
import * as api from './lib/api.js';

const STATUS_WORD = {
  steady: 'Steady', watch: 'Worth watching', flag: 'Outside your range', learning: 'Learning',
};

export default function App() {
  const [phase, setPhase] = useState('waking');   // waking | anon | ready
  const [profile, setProfile] = useState(null);
  const [insights, setInsights] = useState(null);
  const [readings, setReadings] = useState([]);
  const [error, setError] = useState('');

  const loadDashboard = useCallback(async () => {
    setError('');
    const p = await api.me();
    setProfile(p);
    if (p.consent?.scopes?.store_metrics) {
      const [i, r] = await Promise.all([api.getInsights(), api.getReadings()]);
      setInsights(i);
      setReadings(r.readings);
    } else {
      setInsights(null);
      setReadings([]);
    }
    setPhase('ready');
  }, []);

  // On load: wake the sleeping instance first, then restore any session.
  useEffect(() => {
    (async () => {
      const awake = await api.wake();
      if (!awake) {
        setError('The API is taking longer than usual to start. Reload in a moment.');
        setPhase('anon');
        return;
      }
      if (!api.getToken()) { setPhase('anon'); return; }
      try {
        await loadDashboard();
      } catch {
        api.clearToken();
        setPhase('anon');
      }
    })();
  }, [loadDashboard]);

  const guard = (fn) => async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      setError(e.message);
      if (e.message.includes('Sign in')) { setPhase('anon'); setProfile(null); }
    }
  };

  const saveConsent = guard(async (scopes) => {
    await api.setConsent(scopes);
    await loadDashboard();
  });

  const submitReadings = async (rows) => {
    await api.postReadings(rows);
    await loadDashboard();
  };

  const wipe = guard(async () => {
    await api.deleteMe();
    api.clearToken();
    setProfile(null); setInsights(null); setReadings([]);
    setPhase('anon');
  });

  const signOut = () => {
    api.clearToken();
    setProfile(null); setInsights(null); setReadings([]);
    setPhase('anon');
  };

  if (phase === 'waking') {
    return (
      <div className="shell">
        <div className="auth-wrap">
          <div className="waking">
            Waking the server. Free instances sleep after 15 minutes, so this
            first load takes up to a minute.
          </div>
        </div>
      </div>
    );
  }

  if (phase === 'anon') {
    return <AuthScreen onAuthed={loadDashboard} />;
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
            {profile?.display_name || 'You'}{today && ` · ${today}`}
          </div>
          <h1>Your numbers, against your own normal</h1>
        </div>
        <button className="ghost" onClick={signOut}>Sign out</button>
      </div>

      {error && (
        <div className="card" style={{ marginBottom: 20, borderColor: 'var(--flag)' }}>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      {!profile?.consent?.scopes?.store_metrics && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h2>Before anything is stored</h2>
          <p style={{ maxWidth: '58ch' }}>
            Nothing is saved until you say so. Choose what this app may do with
            your readings below. You can change or revoke any of it later, and
            deleting removes everything for good.
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
                    : insights.summary.source === 'disabled'
                      ? 'Written insights are off'
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
                <Trend readings={readings} metric="resting_hr"
                       label="Resting heart rate" unit=" bpm" />
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
        <DataControls consent={profile?.consent} onSave={saveConsent} onDelete={wipe} />
      </div>

      <p className="disclaimer">
        This is a wellness tracker, not a medical device. It describes how your
        own readings compare to your own history and does not diagnose, treat,
        or rule out any condition. If something here concerns you, or if you
        feel unwell, speak to a qualified clinician.
      </p>
    </div>
  );
}
